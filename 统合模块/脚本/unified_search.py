"""统一检索层 —— 所有接入方式(CLI/MCP/Agent/RAG平台)的公共后端。

把两类能力合一:
1. 语义检索(search_semantic):自然语言 → 向量库 → top-K 真实事件
2. 精确查询(query_events):按源/时间/分类/关键词过滤 sqlite 原始库

设计原则:
- 纯函数,无副作用,任何上层都能调(CLI/HTTP/MCP/SDK)
- 不直接打印,返回结构化 list[dict],由调用方决定怎么展示
- 路径自适应(从本文件位置推算项目根),不依赖 cwd
- 复用现有 search_vectors + chroma_client + local_embed,不重复造轮子

两类检索互补:
- 语义检索:适合"我大概记得做过类似的事"(模糊召回)
- 精确查询:适合"列出 2025 年 3 月所有 Agent 事件"(结构化过滤)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Optional

# 让本模块无论被谁 import 都能找到同目录的依赖
import sys
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from search_vectors import search as _semantic_search, search_all as _semantic_search_all  # noqa: E402

ROOT = _THIS_DIR.parents[1]
UNIFIED_DB = ROOT / "统合模块" / "SQLite数据库" / "personal_system.sqlite"


def search_semantic(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
    dedup: bool = False,
    include_turns: bool = True,
) -> list[dict]:
    """语义检索:自然语言召回用户历史事件。

    Wave 7 起默认跨 collection 检索:personal_events(单条事件) +
    conversation_turns(turn 叙述,含因果链)。适合"用户做过什么/怎么做的"类查询。

    query: 自然语言(如"PPT 排版怎么做")
    top_k: 返回条数
    source: 过滤数据源("Google"/"GPT"/"Agent"),None=全源
    dedup:  True=按合并层折叠重复命中(L1 真重复/L2 同主题只留代表),
            返回结果里多一个 merged_count 字段表示该代表背后折叠了几条。
            折叠后实际条数可能少于 top_k。
            注意:dedup 只作用于 personal_events(conversation_turns 不参与合并层折叠)。
    include_turns: True=同时搜 conversation_turns turn 叙述(Wave 7 默认);
                   False=只搜 personal_events(旧行为)。collection 不存在时自动降级。
    返回: list[dict],按相似度降序,字段:
        event_id, source, category_v2, event_type, service,
        event_time, month, title, content, score[, merged_count]
        turn 叙述额外带: session_id, turn_id, turn_no, main_topic
    """
    if not query or not query.strip():
        return []
    # dedup 模式多召回一些,折叠后仍有足够结果
    fetch_k = top_k * 3 if dedup else top_k
    # Wave 7: 跨 collection 检索(include_turns=True 时合并 turn 叙述)
    if include_turns:
        results = _semantic_search_all(query, top_k=fetch_k, source=source)
    else:
        results = _semantic_search(query, top_k=fetch_k, source=source)
    if not dedup or not results:
        return results[:top_k]
    if not _merge_layer_ready():
        return results[:top_k]

    # 按合并层折叠:同簇只留首个(分数最高)命中,附 merged_count
    kept_ids, dup_map = _dedup_event_ids([r["event_id"] for r in results])
    rep_first_idx: dict[str, int] = {}
    for i, r in enumerate(results):
        rep = dup_map.get(r["event_id"], r["event_id"])
        if rep not in rep_first_idx:
            rep_first_idx[rep] = i

    # 统计每个代表折叠了多少条命中
    con = sqlite3.connect(UNIFIED_DB)
    rep_counts: dict[str, int] = {}
    for rep in rep_first_idx:
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM merge_members WHERE cluster_id IN "
                "(SELECT cluster_id FROM merge_members WHERE event_id=?)",
                (rep,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        # 独立事件(不在任何簇)代表它自己,计 1
        rep_counts[rep] = n if n > 0 else 1
    con.close()

    out = []
    for rep, idx in sorted(rep_first_idx.items(), key=lambda x: x[1]):
        r = dict(results[idx])
        r["merged_count"] = rep_counts.get(rep, 1)
        out.append(r)
        if len(out) >= top_k:
            break
    return out


def query_events(
    source: Optional[str] = None,
    month: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
    dedup: bool = False,
) -> list[dict]:
    """精确查询:按结构化条件过滤原始 sqlite 库。

    所有参数都是可选的 AND 过滤:
    source:   "Google"/"GPT"/"Agent"
    month:    "2025-03" 或 "2025"(前缀匹配)
    category: category_v2 子串匹配(如"编程")
    keyword:  title + content_rich + content 的子串匹配
    limit:    最多返回条数(默认 50,上限 200)
    dedup:    True=按合并层折叠(L1/L2 同簇只留代表,代表保留首次命中),
              结果含 merged_count 字段。折叠后条数可能少于 limit。
    返回: list[dict],含 event_id/source/event_time/service/category_v2/title/content_rich
    """
    limit = max(1, min(int(limit), 200))
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    # dedup 模式:多拉再折叠。内层 fetch_limit 放大,折叠后裁到 limit
    fetch_limit = limit * 4 if dedup else limit
    sql = (
        "SELECT ue.event_id, ue.source, ue.service, ue.event_time, ue.month, "
        "ue.title, (r.content_rich IS NOT NULL) AS has_rich, "
        "COALESCE(r.content_rich, ue.content) AS content_rich, "
        "c.category_v2 "
        "FROM unified_events ue "
        "LEFT JOIN unified_events_rich r ON r.event_id = ue.event_id "
        "LEFT JOIN event_categories_v2 c ON c.event_id = ue.event_id "
        "WHERE 1=1"
    )
    params: list = []
    if source:
        sql += " AND ue.source = ?"
        params.append(source)
    if month:
        sql += " AND substr(ue.month, 1, ?) = ?"
        params.extend([len(month), month])
    if category:
        sql += " AND c.category_v2 LIKE ?"
        params.append(f"%{category}%")
    if keyword:
        sql += " AND (ue.title LIKE ? OR COALESCE(r.content_rich, ue.content) LIKE ?)"
        kw = f"%{keyword}%"
        params.extend([kw, kw])
    sql += " ORDER BY ue.event_time DESC LIMIT ?"
    params.append(fetch_limit)
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()

    if not dedup or not rows or not _merge_layer_ready():
        return rows

    kept_ids, dup_map = _dedup_event_ids([r["event_id"] for r in rows])
    # 保留首次出现的代表行,附 merged_count(该代表所属簇的总成员数)
    con = sqlite3.connect(UNIFIED_DB)
    seen_rep: set[str] = set()
    out: list[dict] = []
    for r in rows:
        rep = dup_map.get(r["event_id"], r["event_id"])
        if rep in seen_rep:
            continue
        seen_rep.add(rep)
        r2 = dict(r)
        try:
            n = con.execute(
                "SELECT COUNT(*) FROM merge_members WHERE cluster_id IN "
                "(SELECT cluster_id FROM merge_members WHERE event_id=?)",
                (rep,),
            ).fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        r2["merged_count"] = n if n > 0 else 1  # 独立事件代表自身,计 1
        out.append(r2)
        if len(out) >= limit:
            break
    con.close()
    return out


def get_event_detail(event_id: str) -> Optional[dict]:
    """按 event_id 取单条事件全字段(含增强内容)。给"点开看详情"用。"""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT ue.*, r.content_rich, c.category_v2 "
        "FROM unified_events ue "
        "LEFT JOIN unified_events_rich r ON r.event_id = ue.event_id "
        "LEFT JOIN event_categories_v2 c ON c.event_id = ue.event_id "
        "WHERE ue.event_id = ?",
        (event_id,),
    ).fetchone()
    con.close()
    return dict(row) if row else None


def stats() -> dict:
    """返回数据库+向量库的统计概览(给 AI 快速建立认知用)。"""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    out: dict = {
        "total_events": con.execute("SELECT COUNT(*) FROM unified_events").fetchone()[0],
        "by_source": {
            r[0]: r[1]
            for r in con.execute(
                "SELECT source, COUNT(*) FROM unified_events GROUP BY source ORDER BY 2 DESC"
            )
        },
        "active_months": con.execute(
            "SELECT COUNT(DISTINCT substr(month,1,7)) FROM unified_events WHERE length(month)>=7"
        ).fetchone()[0],
    }
    con.close()
    # 向量库统计(失败不影响主流程)
    try:
        from chroma_client import ChromaClient
        client = ChromaClient()
        coll = client.get_or_create_collection("personal_events")
        out["vector_count"] = coll.count()
        out["vector_available"] = True
    except Exception as e:
        out["vector_available"] = False
        out["vector_error"] = str(e)[:120]
    return out


def list_categories(source: Optional[str] = None) -> list[dict]:
    """返回 category_v2 分布，可按 source 过滤。"""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    sql = (
        "SELECT c.category_v2, COUNT(*) AS n "
        "FROM event_categories_v2 c "
        "JOIN unified_events ue ON ue.event_id = c.event_id "
        "WHERE c.category_v2 IS NOT NULL AND c.category_v2 != ''"
    )
    params: list = []
    if source:
        sql += " AND ue.source = ?"
        params.append(source)
    sql += " GROUP BY c.category_v2 ORDER BY n DESC"
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return rows


# === 记忆层(长期记忆对象 + 图谱关系)=====================================

def _memory_layer_ready() -> bool:
    """记忆层是否已构建。"""
    con = sqlite3.connect(UNIFIED_DB)
    try:
        n = con.execute("SELECT COUNT(1) FROM memory_items").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    con.close()
    return n > 0


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {"raw": raw}


def _memory_row_to_dict(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["metadata"] = _parse_metadata(data.get("metadata"))
    return data


def _find_memory_ids_by_subject(con: sqlite3.Connection, subject: str) -> list[str]:
    """按 subject 精确优先、再模糊匹配记忆对象。"""
    subject = (subject or "").strip()
    if not subject:
        return []
    rows = con.execute(
        "SELECT memory_id FROM memory_items WHERE lower(subject)=lower(?) "
        "ORDER BY evidence_count DESC, confidence DESC",
        (subject,),
    ).fetchall()
    if rows:
        return [r[0] for r in rows]
    rows = con.execute(
        "SELECT memory_id FROM memory_items WHERE lower(subject) LIKE lower(?) "
        "ORDER BY evidence_count DESC, confidence DESC LIMIT 20",
        (f"%{subject}%",),
    ).fetchall()
    return [r[0] for r in rows]


def _get_memory_by_id(con: sqlite3.Connection, memory_id: str) -> Optional[dict]:
    row = con.execute(
        "SELECT memory_id, memory_type, memory_subtype, subject, description, "
        "confidence, evidence_count, metadata, created_at "
        "FROM memory_items WHERE memory_id=?",
        (memory_id,),
    ).fetchone()
    return _memory_row_to_dict(row) if row else None


def _get_memory_evidence_summary(
    con: sqlite3.Connection,
    memory_id: str,
    limit: int = 5,
) -> list[dict]:
    rows = con.execute(
        "SELECT ml.target_id, ue.source, ue.event_time, ue.title, ml.relation "
        "FROM memory_links ml "
        "JOIN unified_events ue ON ue.event_id = ml.target_id "
        "WHERE ml.memory_id=? AND ml.target_type='event' "
        "ORDER BY ue.event_time DESC, ml.id DESC LIMIT ?",
        (memory_id, limit),
    ).fetchall()
    return [
        {
            "target_id": r["target_id"],
            "source": r["source"],
            "event_time": r["event_time"],
            "title": r["title"],
            "relation": r["relation"],
        }
        for r in rows
    ]


def get_memory_profile(memory_type: Optional[str] = None, limit: int = 200) -> dict:
    """返回长期记忆概览,可按 memory_type 过滤。

    memory_type: tooling / preference / capability / fact / project / habit
    limit: 最多返回多少条明细,默认 200。
    """
    if not _memory_layer_ready():
        return {
            "ok": False,
            "available": False,
            "hint": "记忆层未构建。运行: python 统合模块/脚本/run_pipeline.py --from 5 --skip 10",
            "count": 0,
            "total": 0,
            "by_type": {},
            "items": [],
        }
    limit = max(1, min(int(limit), 500))
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    params: list = []
    where = "WHERE 1=1"
    if memory_type:
        where += " AND memory_type=?"
        params.append(memory_type)

    by_type = {
        r["memory_type"]: r["n"]
        for r in con.execute(
            "SELECT memory_type, COUNT(1) AS n FROM memory_items "
            "GROUP BY memory_type ORDER BY n DESC"
        )
    }
    total = con.execute(
        f"SELECT COUNT(1) FROM memory_items {where}",
        params,
    ).fetchone()[0]
    rows = [
        _memory_row_to_dict(r)
        for r in con.execute(
            "SELECT memory_id, memory_type, memory_subtype, subject, description, "
            "confidence, evidence_count, metadata, created_at "
            f"FROM memory_items {where} "
            "ORDER BY memory_type, evidence_count DESC, confidence DESC, subject "
            "LIMIT ?",
            params + [limit],
        )
    ]
    con.close()
    return {
        "ok": True,
        "available": True,
        "count": len(rows),
        "total": total,
        "by_type": by_type,
        "filter": {"memory_type": memory_type, "limit": limit},
        "items": rows,
    }


def get_memory_relations(subject: str) -> dict:
    """返回某个 subject 匹配记忆的所有入边/出边关系。"""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    ids = _find_memory_ids_by_subject(con, subject)
    if not ids:
        con.close()
        return {"found": False, "subject": subject, "matches": [], "relations": []}

    placeholders = ",".join("?" * len(ids))
    rows = con.execute(
        "SELECT mr.relation, mr.strength, "
        "src.memory_id AS from_memory_id, src.memory_type AS from_type, "
        "src.memory_subtype AS from_subtype, src.subject AS from_subject, "
        "src.description AS from_description, "
        "dst.memory_id AS to_memory_id, dst.memory_type AS to_type, "
        "dst.memory_subtype AS to_subtype, dst.subject AS to_subject, "
        "dst.description AS to_description "
        "FROM memory_relations mr "
        "JOIN memory_items src ON src.memory_id = mr.from_memory_id "
        "JOIN memory_items dst ON dst.memory_id = mr.to_memory_id "
        f"WHERE mr.from_memory_id IN ({placeholders}) OR mr.to_memory_id IN ({placeholders}) "
        "ORDER BY mr.strength DESC, mr.relation",
        ids + ids,
    ).fetchall()
    matches = [_get_memory_by_id(con, mid) for mid in ids]
    con.close()
    return {
        "found": True,
        "subject": subject,
        "matches": [m for m in matches if m],
        "relations": [dict(r) for r in rows],
    }


def get_memory_by_subject(subject: str) -> Optional[dict]:
    """按主体查记忆详情,并附带证据数量和图谱关系。"""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    ids = _find_memory_ids_by_subject(con, subject)
    if not ids:
        con.close()
        return None
    primary = _get_memory_by_id(con, ids[0])
    evidence = [
        dict(r)
        for r in con.execute(
            "SELECT target_type, target_id, relation FROM memory_links "
            "WHERE memory_id=? ORDER BY id LIMIT 20",
            (ids[0],),
        )
    ]
    evidence_summary = _get_memory_evidence_summary(con, ids[0], limit=5)
    con.close()
    rel = get_memory_relations(subject)
    return {
        "ok": True,
        "count": len(rel.get("matches", [])),
        "memory": primary,
        "items": rel.get("matches", []),
        "matches": rel.get("matches", []),
        "relations": rel.get("relations", []),
        "evidence": evidence,
        "evidence_summary": evidence_summary,
    }


def get_memory_neighbors(subject: str, hops: int = 2) -> dict:
    """按图谱关系返回 subject 的 N 跳邻居。"""
    hops = max(1, min(int(hops), 4))
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    start_ids = _find_memory_ids_by_subject(con, subject)
    if not start_ids:
        con.close()
        return {
            "ok": False,
            "found": False,
            "subject": subject,
            "hops": hops,
            "count": 0,
            "levels": [],
        }

    visited = set(start_ids)
    frontier = set(start_ids)
    levels: list[dict] = []
    for level in range(1, hops + 1):
        if not frontier:
            break
        placeholders = ",".join("?" * len(frontier))
        rows = con.execute(
            "SELECT mr.relation, mr.strength, mr.from_memory_id, mr.to_memory_id, "
            "src.subject AS from_subject, src.memory_type AS from_type, "
            "dst.subject AS to_subject, dst.memory_type AS to_type "
            "FROM memory_relations mr "
            "JOIN memory_items src ON src.memory_id = mr.from_memory_id "
            "JOIN memory_items dst ON dst.memory_id = mr.to_memory_id "
            f"WHERE mr.from_memory_id IN ({placeholders}) OR mr.to_memory_id IN ({placeholders})",
            list(frontier) + list(frontier),
        ).fetchall()
        next_ids: set[str] = set()
        edges = []
        for r in rows:
            other = r["to_memory_id"] if r["from_memory_id"] in frontier else r["from_memory_id"]
            if other in visited:
                continue
            next_ids.add(other)
            edges.append(dict(r))
        nodes = [_get_memory_by_id(con, mid) for mid in sorted(next_ids)]
        levels.append({
            "hop": level,
            "nodes": [n for n in nodes if n],
            "relations": edges,
        })
        visited |= next_ids
        frontier = next_ids
    starts = [_get_memory_by_id(con, mid) for mid in start_ids]
    con.close()
    count = sum(len(level.get("nodes", [])) for level in levels)
    return {
        "ok": True,
        "found": True,
        "subject": subject,
        "hops": hops,
        "count": count,
        "starts": [s for s in starts if s],
        "levels": levels,
    }


# === 合并层(去重视图)====================================================

def _merge_layer_ready() -> bool:
    """合并层是否已构建(merge_clusters 表存在且非空)。"""
    con = sqlite3.connect(UNIFIED_DB)
    try:
        n = con.execute("SELECT COUNT(*) FROM merge_clusters").fetchone()[0]
    except sqlite3.OperationalError:
        n = 0
    con.close()
    return n > 0


def _dedup_event_ids(event_ids: list[str]) -> tuple[list[str], dict[str, str]]:
    """按合并层折叠一批 event_id。

    返回 (kept_ids, dup_map):
      kept_ids: 去重后保留的代表 id 列表(保持输入顺序)
      dup_map:  {被折叠的成员id → 代表id}(仅含实际被折叠的;代表/独立点不入表)

    规则:若 event_id 是某簇的成员,用该簇代表点替换它;
          代表点或非合并表成员保持原样。多个成员属同一簇只留一个代表。
    """
    if not event_ids:
        return [], {}
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(event_ids))
    # 每个 event_id → 其所属簇的代表(若有)
    rows = con.execute(
        f"SELECT mm.event_id AS eid, mc.representative_id AS rep_id "
        f"FROM merge_members mm JOIN merge_clusters mc "
        f"ON mc.cluster_id = mm.cluster_id "
        f"WHERE mm.event_id IN ({placeholders})",
        event_ids,
    ).fetchall()
    con.close()
    eid_to_rep = {r["eid"]: r["rep_id"] for r in rows}

    kept: list[str] = []
    seen_reps: set[str] = set()
    dup_map: dict[str, str] = {}
    for eid in event_ids:
        rep = eid_to_rep.get(eid, eid)  # 不在合并表 → 自身即代表
        if rep in seen_reps:
            dup_map[eid] = rep
            continue
        seen_reps.add(rep)
        kept.append(eid if eid == rep else rep)
        if eid != rep:
            dup_map[eid] = rep
    return kept, dup_map


def merge_stats() -> dict:
    """返回合并层构建报告(merge_build_meta + 簇分布)。

    若合并层未构建,返回 {"available": False, "hint": ...}。
    """
    if not _merge_layer_ready():
        return {
            "available": False,
            "hint": "合并层未构建。运行: python 统合模块/脚本/build_merge_layer.py",
        }
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    meta = {r["key"]: r["value"] for r in con.execute(
        "SELECT key, value FROM merge_build_meta"
    )}
    by_level = {
        r["level"]: r["n"] for r in con.execute(
            "SELECT level, COUNT(*) AS n FROM merge_clusters GROUP BY level"
        )
    }
    top_l1 = [dict(r) for r in con.execute(
        "SELECT mc.cluster_id, mc.member_count, ue.title "
        "FROM merge_clusters mc JOIN unified_events ue "
        "ON ue.event_id = mc.representative_id "
        "WHERE mc.level='L1_duplicate' "
        "ORDER BY mc.member_count DESC LIMIT 5"
    )]
    top_l2 = [dict(r) for r in con.execute(
        "SELECT mc.cluster_id, mc.member_count, substr(mc.summary,1,60) AS summary "
        "FROM merge_clusters mc WHERE mc.level='L2_topic' "
        "ORDER BY mc.member_count DESC LIMIT 5"
    )]
    con.close()

    def num(k):
        try:
            return int(float(meta.get(k, 0)))
        except (ValueError, TypeError):
            return meta.get(k)

    return {
        "available": True,
        "n_input": num("n_input"),
        "l1_clusters": by_level.get("L1_duplicate", 0),
        "l1_events": num("l1_events"),
        "l2_clusters": by_level.get("L2_topic", 0),
        "l2_events": num("l2_events"),
        "structural_clusters": num("structural_clusters"),
        "structural_events": num("structural_events"),
        "effective_events": num("effective_events"),
        "compression": float(meta.get("compression", 0)),
        "thresholds": {
            "l1_cos": float(meta.get("threshold_l1_cos", 0)),
            "l1_jac": float(meta.get("threshold_l1_jac", 0)),
            "l1_sem_jac": float(meta.get("threshold_l1_sem_jac", 0)),
            "l1_distinct": float(meta.get("threshold_l1_distinct", 0)),
            "l2_cos": float(meta.get("threshold_l2_cos", 0)),
        },
        "top_l1_clusters": top_l1,
        "top_l2_clusters": top_l2,
    }


# === 聚类 / 去重(对向量库二次加工)======================================

def cluster(
    source: Optional[str] = None,
    threshold: float = 0.92,
    min_cluster_size: int = 2,
    limit: Optional[int] = None,
) -> dict:
    """对向量库做相似度聚类,把高度相似的事件归成簇。

    本质是"向量库的二次加工":从 chroma 拉出全部 embedding,算两两余弦相似度,
    相似度 >= threshold 的连成一张图,连通分量即一个簇。

    source:           过滤数据源(None=全库)
    threshold:        相似度阈值(0-1,越大越严格;0.92 经验上能抓"几乎重复")
    min_cluster_size: 只保留 size >= N 的簇(size=1 的孤立点单独统计,不展开)
    limit:            最多处理多少条(默认全部,调试时可设小值)

    返回 dict:
        n_input:        输入事件数
        n_kept:         保留(代表)事件数 = 簇数 + 孤立点数
        n_merged:       被合并掉的事件数 = n_input - n_kept
        n_clusters:     簇数(size>=min_cluster_size)
        n_singletons:   孤立点数(自成一类)
        compression:    压缩率 = n_merged / n_input
        threshold/min_cluster_size: 回显参数
        clusters:       [{id, size, representative_id, representative_title,
                         member_ids: [...], mean_similarity}, ...](按 size 降序)

    依赖:numpy(余弦相似度矩阵)。7700 条全量约 230MB 内存,可接受。
    """
    import numpy as np
    from chroma_client import ChromaClient

    client = ChromaClient()
    coll = client.get_or_create_collection("personal_events")

    # 分批拉全部 embedding + 元数据(chroma 单次 get 有上限,分批稳妥)
    BATCH = 2000
    ids: list[str] = []
    embs: list[list[float]] = []
    titles: dict[str, str] = {}
    offset = 0
    where = {"source": source} if source else None
    while True:
        batch = coll.get(
            where=where, limit=BATCH, offset=offset,
            include=["embeddings", "documents", "metadatas"],
        )
        b_ids = batch.get("ids", [])
        if not b_ids:
            break
        ids.extend(b_ids)
        embs.extend(batch.get("embeddings", []))
        for i, mid in enumerate(b_ids):
            meta = (batch.get("metadatas") or [None] * len(b_ids))[i] or {}
            titles[mid] = meta.get("title") or (batch.get("documents") or [""])[i][:60]
        offset += len(b_ids)
        if limit and len(ids) >= limit:
            ids = ids[:limit]
            embs = embs[:limit]
            break

    n = len(ids)
    if n == 0:
        return {
            "n_input": 0, "n_kept": 0, "n_merged": 0,
            "n_clusters": 0, "n_singletons": 0, "compression": 0.0,
            "threshold": threshold, "min_cluster_size": min_cluster_size,
            "clusters": [],
        }

    # 余弦相似度矩阵(embedding 已是 bge-m3 归一化的,但保险起见再归一)
    mat = np.asarray(embs, dtype=np.float32)
    norms = np.linalg.norm(mat, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    mat = mat / norms
    sim = mat @ mat.T  # (n, n) 余弦相似度

    # 连通分量:相似度 >= threshold 的点互相连通 → 同一簇
    adj = sim >= threshold
    visited = [False] * n
    groups: list[list[int]] = []
    for i in range(n):
        if visited[i]:
            continue
        # BFS 找连通分量
        stack = [i]
        visited[i] = True
        comp = []
        while stack:
            cur = stack.pop()
            comp.append(cur)
            neighbors = np.nonzero(adj[cur])[0]
            for nb in neighbors:
                if not visited[nb]:
                    visited[nb] = True
                    stack.append(int(nb))
        groups.append(comp)

    # 拆成 clusters(>=min) 和 singletons
    clusters_raw = [g for g in groups if len(g) >= min_cluster_size]
    singletons = [g for g in groups if len(g) < min_cluster_size]

    out_clusters = []
    for ci, comp in enumerate(
        sorted(clusters_raw, key=len, reverse=True)
    ):
        sub = sim[np.ix_(comp, comp)]
        mean_sim = float((sub.sum() - len(comp)) / (len(comp) * (len(comp) - 1)))
        # 代表点选簇内平均相似度最高的(最"居中")
        centrality = (sub.sum(axis=1) - 1) / (len(comp) - 1)
        rep_idx = int(np.argmax(centrality))
        rep_id = ids[comp[rep_idx]]
        out_clusters.append({
            "id": ci,
            "size": len(comp),
            "representative_id": rep_id,
            "representative_title": titles.get(rep_id, "")[:60],
            "mean_similarity": round(mean_sim, 4),
            "member_ids": [ids[j] for j in comp],
        })

    n_kept = len(clusters_raw) + len(singletons)
    return {
        "n_input": n,
        "n_kept": n_kept,
        "n_merged": n - n_kept,
        "n_clusters": len(clusters_raw),
        "n_singletons": len(singletons),
        "compression": round((n - n_kept) / n, 4),
        "threshold": threshold,
        "min_cluster_size": min_cluster_size,
        "clusters": out_clusters,
    }


# === CLI 入口 ===

def _cli() -> None:
    import argparse
    import json

    p = argparse.ArgumentParser(
        description="统一检索层 CLI:语义检索 + 精确查询",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 语义检索(模糊召回)
  python unified_search.py semantic "PPT 排版怎么做" --top-k 3
  python unified_search.py semantic "数据库调试" --source Agent

  # 语义检索 + 去重(合并层折叠重复命中)
  python unified_search.py semantic "PPT" --top-k 8 --dedup

  # 精确查询(结构化过滤)
  python unified_search.py query --source GPT --month 2025-03
  python unified_search.py query --category 编程 --keyword 报错 --limit 10
  python unified_search.py query --source Agent --dedup --limit 30

  # 单条详情
  python unified_search.py detail <event_id>

  # 统计概览
  python unified_search.py stats
  python unified_search.py merge-stats        # 合并层压缩报告

  # 长期记忆对象
  python unified_search.py memory
  python unified_search.py memory --type tooling
  python unified_search.py memory --subject Codex
  python unified_search.py memory --subject Codex --neighbors 2

  # 向量库聚类/去重(管道加工,即时计算,不依赖合并层)
  python unified_search.py cluster --source Agent --threshold 0.92
  python unified_search.py cluster --threshold 0.88 --min-cluster-size 3 --json

  # JSON 输出(便于其他程序消费)—— --json 跟在子命令后
  python unified_search.py semantic "PPT" --json
  python unified_search.py stats --json
  python unified_search.py merge-stats --json
  python unified_search.py cluster --json --limit 500    # 调试用小样本
        """,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("semantic", help="语义检索(自然语言)")
    ps.add_argument("query")
    ps.add_argument("--top-k", type=int, default=5)
    ps.add_argument("--source", default=None)
    ps.add_argument("--dedup", action="store_true",
                    help="按合并层折叠重复命中(L1/L2 同簇只留代表,附 merged_count)")
    ps.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pq = sub.add_parser("query", help="精确查询(结构化过滤)")
    pq.add_argument("--source", default=None)
    pq.add_argument("--month", default=None, help="如 2025-03 或 2025")
    pq.add_argument("--category", default=None, help="category_v2 子串")
    pq.add_argument("--keyword", default=None, help="title+content 子串")
    pq.add_argument("--limit", type=int, default=20)
    pq.add_argument("--dedup", action="store_true",
                    help="按合并层折叠(L1/L2 同簇只留代表,附 merged_count)")
    pq.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pd = sub.add_parser("detail", help="单条事件详情")
    pd.add_argument("event_id")
    pd.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pst = sub.add_parser("stats", help="数据库+向量库统计")
    pst.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pms = sub.add_parser("merge-stats", help="合并层压缩报告(L1/L2 去重情况)")
    pms.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pm = sub.add_parser("memory", help="长期记忆对象查询")
    pm.add_argument("--type", dest="memory_type", default=None,
                    help="过滤记忆类型: tooling/preference/capability/fact/project/habit")
    pm.add_argument("--subject", default=None, help="按主体查详情,如 Codex")
    pm.add_argument("--neighbors", type=int, default=0, help="同时返回 N 跳邻居(1-4)")
    pm.add_argument("--limit", type=int, default=50, help="概览模式返回上限")
    pm.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pc = sub.add_parser(
        "cluster", help="向量库相似度聚类/去重(管道加工)"
    )
    pc.add_argument("--source", default=None, help="过滤数据源,不传=全库")
    pc.add_argument(
        "--threshold", type=float, default=0.92,
        help="相似度阈值(0-1,越大越严格,默认 0.92 抓几乎重复)",
    )
    pc.add_argument(
        "--min-cluster-size", type=int, default=2,
        help="只保留 size>=N 的簇(默认 2;孤立点单列不展开)",
    )
    pc.add_argument(
        "--limit", type=int, default=None,
        help="最多处理多少条(默认全部;调试可设小值)",
    )
    pc.add_argument(
        "--members", action="store_true",
        help="人类可读模式下展示每个簇的成员 id(默认只展示代表+数量)",
    )
    pc.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    args = p.parse_args()

    if args.cmd == "semantic":
        data = search_semantic(args.query, top_k=args.top_k, source=args.source, dedup=args.dedup)
    elif args.cmd == "query":
        data = query_events(
            source=args.source, month=args.month,
            category=args.category, keyword=args.keyword, limit=args.limit,
            dedup=args.dedup,
        )
    elif args.cmd == "detail":
        data = get_event_detail(args.event_id)
        if data is None:
            print(f"未找到 event_id={args.event_id}")
            return
    elif args.cmd == "stats":
        data = stats()
    elif args.cmd == "merge-stats":
        data = merge_stats()
    elif args.cmd == "memory":
        if args.subject:
            detail = get_memory_by_subject(args.subject)
            if detail is None:
                print(f"未找到 memory subject={args.subject}")
                return
            if args.neighbors:
                detail["neighbors"] = get_memory_neighbors(args.subject, args.neighbors)
            data = detail
        else:
            data = get_memory_profile(memory_type=args.memory_type, limit=args.limit)
    elif args.cmd == "cluster":
        data = cluster(
            source=args.source, threshold=args.threshold,
            min_cluster_size=args.min_cluster_size, limit=args.limit,
        )

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    # 人类可读输出
    if args.cmd == "semantic":
        if not data:
            print("无匹配结果")
            return
        for i, r in enumerate(data, 1):
            mc = r.get("merged_count")
            tail = f"  (折叠 {mc} 条)" if mc and mc > 1 else ""
            print(f"\n#{i} [score={r['score']}] [{r['source']}] {(r.get('title') or '(无标题)')[:50]}{tail}")
            print(f"   时间: {r.get('event_time','')}  分类: {r.get('category_v2','')}")
            c = (r.get("content") or "")[:200]
            print(f"   内容: {c}{'…' if len(r.get('content',''))>200 else ''}")
        print(f"\n共 {len(data)} 条" + ("(已去重)" if args.dedup else ""))
    elif args.cmd == "query":
        if not data:
            print("无匹配结果")
            return
        for r in data:
            mc = r.get("merged_count")
            tail = f" ×{mc}" if mc and mc > 1 else ""
            print(f"[{r['source']}] {r['event_time']} | {(r.get('title') or '')[:40]} | {r.get('category_v2','')}{tail}")
        print(f"\n共 {len(data)} 条(上限 {args.limit})" + ("(已去重)" if args.dedup else ""))
    elif args.cmd == "detail":
        for k, v in data.items():
            val = str(v) if v is not None else ""
            if len(val) > 300:
                val = val[:300] + "…"
            print(f"{k}: {val}")
    elif args.cmd == "stats":
        print(f"总事件: {data['total_events']:,}")
        print(f"活跃月份: {data['active_months']}")
        print("按源分布:")
        for s, n in data["by_source"].items():
            print(f"  {s}: {n:,}")
        if data.get("vector_available"):
            print(f"向量库: {data['vector_count']:,} 条")
        else:
            print(f"向量库: 不可用({data.get('vector_error','')})")
    elif args.cmd == "merge-stats":
        if not data.get("available"):
            print(data.get("hint", "合并层未构建"))
            return
        print(f"输入事件: {data['n_input']:,}  →  等效事件: {data['effective_events']:,}"
              f"  (压缩 {data['compression']:.1%})")
        print(f"L1 真重复: {data['l1_clusters']} 簇 / {data['l1_events']} 条")
        print(f"L2 同主题: {data['l2_clusters']} 簇 / {data['l2_events']} 条")
        print(f"L3 结构保护: {data['structural_clusters']} 簇 / {data['structural_events']} 条")
        th = data["thresholds"]
        print(f"阈值: L1={th['l1_cos']}/J{th['l1_jac']}/SJ{th['l1_sem_jac']}/DR{th['l1_distinct']} L2={th['l2_cos']}")
        if data.get("top_l1_clusters"):
            print("\nL1 Top 簇:")
            for c in data["top_l1_clusters"]:
                print(f"  size={c['member_count']} '{(c['title'] or '')[:45]}'")
        if data.get("top_l2_clusters"):
            print("\nL2 Top 簇:")
            for c in data["top_l2_clusters"]:
                print(f"  size={c['member_count']} {c['summary']}")
    elif args.cmd == "memory":
        if args.subject:
            memory = data["memory"]
            print(f"[{memory['memory_type']}/{memory['memory_subtype']}] {memory['subject']}")
            print(f"置信度: {memory.get('confidence')}  证据数: {memory.get('evidence_count')}")
            print(f"描述: {memory.get('description')}")
            if data.get("relations"):
                print("\n关系:")
                for r in data["relations"][:20]:
                    print(f"  {r['from_subject']} --{r['relation']}({r['strength']})--> {r['to_subject']}")
            if data.get("evidence_summary"):
                print("\n证据摘要:")
                for row in data["evidence_summary"][:5]:
                    print(
                        f"  {row.get('source','?')} {str(row.get('event_time',''))[:19]} "
                        f"{str(row.get('title') or '(无标题)')[:60]}"
                    )
            if data.get("neighbors"):
                print("\n邻居:")
                for level in data["neighbors"].get("levels", []):
                    names = ", ".join(f"{n['subject']}[{n['memory_type']}]" for n in level.get("nodes", []))
                    print(f"  {level['hop']}跳: {names or '(无)'}")
        else:
            if not data.get("available"):
                print(data.get("hint", "记忆层未构建"))
                return
            print(f"记忆总数: {data['total']}")
            print("按类型:")
            for t, n in data["by_type"].items():
                print(f"  {t}: {n}")
            print("\n明细:")
            for item in data["items"]:
                print(f"[{item['memory_type']}/{item['memory_subtype']}] {item['subject']} "
                      f"(证据 {item['evidence_count']}, 置信 {item['confidence']})")
                print(f"  {item['description'][:160]}")
    elif args.cmd == "cluster":
        print(f"输入事件: {data['n_input']:,}")
        print(f"保留(代表): {data['n_kept']:,}  合并掉: {data['n_merged']:,}"
              f"  压缩率: {data['compression']:.1%}")
        print(f"簇数: {data['n_clusters']}  孤立点: {data['n_singletons']}"
              f"  (阈值={data['threshold']}, 最小簇={data['min_cluster_size']})")
        if data["clusters"]:
            print(f"\nTop 簇(按 size 降序):")
            for c in data["clusters"]:
                print(f"  #{c['id']} size={c['size']} mean_sim={c['mean_similarity']}"
                      f"  代表: {(c['representative_title'] or '(无标题)')[:50]}")
                if args.members:
                    for mid in c["member_ids"]:
                        print(f"      - {mid}")
        if not data["clusters"]:
            print("\n(无达到 min-cluster-size 的簇,试试降低 --threshold)")


if __name__ == "__main__":
    _cli()
