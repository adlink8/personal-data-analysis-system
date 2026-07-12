"""统一检索层 —— 所有接入方式(CLI/MCP/Agent/RAG平台)的公共后端。

能力:
1. 语义检索(search_knowledge_units): knowledge-first + layered/legacy fallback
   读 active knowledge index；layered=dialogue→Google events；legacy=全量 personal_events
2. 知识状态(get_knowledge_status): active collection / unit_count / fallback_policy / 版本行
3. 精确查询(query_events):按源/时间/分类/关键词过滤 sqlite 原始库
4. 记忆 /data 契约: 分页、导出、聚合、时间线、质量报告

设计原则:
- 纯函数,无副作用,任何上层都能调(CLI/HTTP/MCP/SDK)
- 不直接打印,返回结构化 list[dict]/dict,由调用方决定怎么展示
- 路径自适应(从本文件位置推算项目根),不依赖 cwd
- 复用 search_vectors + chroma_client + local_embed

CLI 入口: python integration/scripts/unified_search.py
  semantic | knowledge | query | detail | stats | memory | ...
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import csv
import io
from pathlib import Path
from typing import Any, Optional

# 让本模块无论被谁 import 都能找到同目录的依赖
import sys
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

from vector.search_vectors import search as _semantic_search, search_all as _semantic_search_all  # noqa: E402

ROOT = _THIS_DIR.parents[1]
UNIFIED_DB = ROOT / "integration" / "db" / "personal_system.sqlite"
DEFAULT_MEMORY_GRAPH_LIMIT = 100
MAX_MEMORY_GRAPH_LIMIT = 200
DEFAULT_RELATION_REVIEW_LIMIT = 50
MAX_RELATION_REVIEW_LIMIT = 200
RELATION_REVIEW_STATUSES = {"review", "accepted", "rejected"}
DEFAULT_DATA_LIMIT = 100
MAX_DATA_LIMIT = 500
MAX_EXPORT_LIMIT = 5000

DEFAULT_EVENT_FIELDS = [
    "event_id",
    "source",
    "event_time",
    "title",
    "service",
    "category_v2",
]
EVENT_FIELD_SQL = {
    "event_id": "ue.event_id",
    "source": "ue.source",
    "source_table": "ue.source_table",
    "source_id": "ue.source_id",
    "event_type": "ue.event_type",
    "service": "ue.service",
    "event_time": "ue.event_time",
    "month": "ue.month",
    "title": "ue.title",
    "category": "ue.category",
    "category_v2": "c.category_v2",
    "url": "ue.url",
    "domain": "ue.domain",
    "file_name": "ue.file_name",
    "session_id": "ue.session_id",
    "weight": "ue.weight",
    "content": "ue.content",
    "content_rich": "r.content_rich",
    "has_rich": "(r.content_rich IS NOT NULL)",
}
AGGREGATE_GROUP_SQL = {
    "source": "ue.source",
    "service": "ue.service",
    "category_v2": "c.category_v2",
    "category": "c.category_v2",
    "event_type": "ue.event_type",
    "month": "substr(ue.event_time, 1, 7)",
    "day": "substr(ue.event_time, 1, 10)",
    "year": "substr(ue.event_time, 1, 4)",
}


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
        event_time, month, title, content, score[, merged_count],
        collection, retrieval_unit, rank_reason
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


# --- Knowledge unit hybrid retrieval (Phase 14 Wave 4 / Phase 15 Wave 2) ---

# 混合策略：知识层贡献结构化语义结果；raw 层可配置:
#   legacy  — KU 后补全量 personal_events（旧行为）
#   layered — KU → canonical message 片段/词检索(dialogue) → conversation_turns
#             → personal_events(Google) → 可选 legacy_pad
# Phase 15 W4: message 级 dialogue 补洞（frozen gold snippet R@8=1.0 on canonical）。
_KU_SLOTS = 1
_RAW_SLOTS_DEFAULT = 4
_KU_PORT = 8001

FALLBACK_POLICIES = ("legacy", "layered")
DEFAULT_FALLBACK_POLICY = "layered"
CONVERSATION_TURNS_COLLECTION = "conversation_turns"
CANONICAL_MESSAGES_COLLECTION = "canonical_messages"
_NON_DIALOGUE_PREFERRED_SOURCE = "Google"


def _resolve_fallback_policy(fallback_policy: str | None = None) -> str:
    """Resolve hybrid fallback policy from arg or env PERSONAL_DATA_FALLBACK_POLICY."""
    if fallback_policy is None:
        raw = os.environ.get("PERSONAL_DATA_FALLBACK_POLICY", DEFAULT_FALLBACK_POLICY)
    else:
        raw = fallback_policy
    policy = (raw or DEFAULT_FALLBACK_POLICY).strip().lower()
    if policy not in FALLBACK_POLICIES:
        return DEFAULT_FALLBACK_POLICY
    return policy


def _resolve_allow_legacy_pad(allow_legacy_pad: bool | None = None) -> bool:
    """Whether layered mode may pad with non-Google personal_events when still short.

    Default True (transition safety). Env: PERSONAL_DATA_ALLOW_LEGACY_PAD=0|1|true|false.
    """
    if allow_legacy_pad is not None:
        return bool(allow_legacy_pad)
    env = os.environ.get("PERSONAL_DATA_ALLOW_LEGACY_PAD")
    if env is None or not str(env).strip():
        return True
    return str(env).strip().lower() in ("1", "true", "yes", "on")


def _raw_event_item(
    ev: dict,
    *,
    retrieval_unit: str,
    collection: str,
    rank_reason: str,
) -> dict:
    """Normalize a vector search hit into the hybrid result schema."""
    title = ev.get("title") or ev.get("main_topic") or ""
    return {
        "unit_id": ev.get("event_id", ""),
        "subject": str(title)[:80],
        "answer": (ev.get("content") or "")[:300],
        "score": ev.get("score", 0),
        "lifecycle": "current",
        "confidence": 0,
        "source_message_ref": "",
        "collection": collection,
        "retrieval_unit": retrieval_unit,
        "rank_reason": rank_reason,
        "event_id": ev.get("event_id", ""),
        "source": ev.get("source", ""),
        "event_time": ev.get("event_time", ""),
    }


def _search_personal_events_filtered(
    query: str,
    top_k: int,
    source: Optional[str],
) -> list[dict]:
    """Query personal_events; prefer server-side where, else client-side source filter."""
    if top_k <= 0:
        return []
    try:
        return _semantic_search(query, top_k=top_k, source=source)
    except Exception:
        pass
    # where may be unsupported / broken — fetch wider and filter client-side
    try:
        events = _semantic_search(query, top_k=max(top_k * 3, top_k), source=None)
    except Exception:
        return []
    if not source:
        return events[:top_k]
    filtered = [e for e in events if (e.get("source") or "") == source]
    return filtered[:top_k] if filtered else []


def _like_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _query_tokens(query: str, max_toks: int = 4) -> list[str]:
    """Extract distinctive CJK/latin tokens for AND-style LIKE search."""
    toks = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z_][A-Za-z0-9_\-]{3,}", query or "")
    # longer first (more distinctive for code / paths)
    ordered = sorted(set(toks), key=len, reverse=True)
    return ordered[:max_toks]


def _search_dialogue_canonical_messages(
    query: str,
    top_k: int = 5,
    db_path: Path | None = None,
) -> list[dict]:
    """Message-level dialogue fallback on canonical_messages (read-only).

    Strategy (Phase 15 W4):
    1) For long pastes: sliding snippet LIKE (handles code-literal gold)
    2) Else: multi-token AND LIKE on distinctive terms

    Returns hybrid-schema items with unit_id = canonical_message_id (cm|…).
    """
    if top_k <= 0 or not (query or "").strip():
        return []
    try:
        from core.project_paths import AGENT_CONVERSATIONS_DB  # noqa: E402
    except Exception:
        AGENT_CONVERSATIONS_DB = ROOT / "Agent" / "structured" / "db" / "agent_conversations.sqlite"
    path = Path(db_path) if db_path else AGENT_CONVERSATIONS_DB
    if not path.exists():
        return []

    q = query.strip()
    rows: list[tuple] = []
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
        except Exception:
            pass
        # Prefer non-system messages when column exists
        try:
            cols = {r[1] for r in con.execute("PRAGMA table_info(canonical_messages)")}
        except Exception:
            cols = set()
        if "canonical_message_id" not in cols or "content" not in cols:
            con.close()
            return []

        base_where = "1=1"
        if "is_system" in cols:
            base_where += " AND COALESCE(is_system,0)=0"

        if len(q) >= 40:
            for start in (0, 20, 50, 100, min(200, max(0, len(q) - 40))):
                snip = q[start : start + 40]
                if len(snip) < 20:
                    continue
                esc = _like_escape(snip)
                sql = (
                    "SELECT canonical_message_id, role, substr(content,1,300), "
                    "COALESCE(timestamp,''), COALESCE(source,'') "
                    f"FROM canonical_messages WHERE {base_where} "
                    "AND content LIKE ? ESCAPE '\\' LIMIT ?"
                )
                try:
                    found = con.execute(sql, (f"%{esc}%", top_k * 2)).fetchall()
                except Exception:
                    found = []
                if found:
                    rows = found
                    break

        if not rows:
            toks = _query_tokens(q, max_toks=4)
            if toks:
                sql = (
                    "SELECT canonical_message_id, role, substr(content,1,300), "
                    "COALESCE(timestamp,''), COALESCE(source,'') "
                    f"FROM canonical_messages WHERE {base_where}"
                )
                params: list[Any] = []
                for t in toks:
                    sql += " AND content LIKE ? ESCAPE '\\'"
                    params.append(f"%{_like_escape(t)}%")
                sql += " LIMIT ?"
                params.append(top_k * 2)
                try:
                    rows = con.execute(sql, params).fetchall()
                except Exception:
                    rows = []
        con.close()
    except Exception:
        return []

    out: list[dict] = []
    seen: set[str] = set()
    for mid, role, content, ts, src in rows:
        mid = str(mid or "")
        if not mid or mid in seen:
            continue
        seen.add(mid)
        # Prefer higher score for earlier ranks; user messages slight boost
        base = 0.92 - 0.02 * len(out)
        if (role or "") == "user":
            base = min(0.99, base + 0.03)
        out.append(
            {
                "unit_id": mid,
                "subject": f"dialogue:{(role or 'msg')}"[:80],
                "answer": (content or "")[:300],
                "score": round(base, 4),
                "lifecycle": "current",
                "confidence": 0,
                "source_message_ref": mid,
                "collection": CANONICAL_MESSAGES_COLLECTION,
                "retrieval_unit": "dialogue",
                "rank_reason": "dialogue_fallback canonical_messages",
                "event_id": mid,
                "source": src or "Agent",
                "event_time": ts or "",
                "role": role or "",
            }
        )
        if len(out) >= top_k:
            break
    return out


def _read_knowledge_active_collection() -> str:
    """读 active knowledge index pointer。"""
    from core.project_paths import DB_DIR  # noqa: E402
    pointer = DB_DIR / "knowledge_index_active.txt"
    if pointer.exists():
        name = pointer.read_text(encoding="utf-8").strip()
        return name if name else ""
    return ""


def get_google_structure_status(db_path: Path | None = None) -> dict:
    """Phase 16: Google light structure status (normalized_events + light assertions)."""
    path = Path(db_path) if db_path else (ROOT / "Google" / "structured" / "db" / "google_data.sqlite")
    out: dict[str, Any] = {
        "available": path.exists(),
        "db_path": str(path),
        "activities": None,
        "normalized_events": None,
        "light_assertions": None,
        "assertions_by_type": {},
        "event_id_prefix": "g|",
        "note": "aggregate signals only; not dialogue knowledge_units",
    }
    if not path.exists():
        return out
    try:
        con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "activities" in tables:
            out["activities"] = con.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
        if "normalized_events" in tables:
            out["normalized_events"] = con.execute(
                "SELECT COUNT(*) FROM normalized_events"
            ).fetchone()[0]
        if "google_light_assertions" in tables:
            out["light_assertions"] = con.execute(
                "SELECT COUNT(*) FROM google_light_assertions WHERE status='current'"
            ).fetchone()[0]
            out["assertions_by_type"] = dict(
                con.execute(
                    "SELECT assertion_type, COUNT(*) FROM google_light_assertions "
                    "WHERE status='current' GROUP BY 1"
                ).fetchall()
            )
        con.close()
    except Exception as e:
        out["error"] = str(e)[:200]
    return out


def get_knowledge_status(*, probe_chroma: bool = True) -> dict:
    """知识索引只读状态（CLI / REST / MCP 共用）。

    返回 active collection、pointer、版本行、fallback_policy/ssot 与（可选）Chroma 实际条数。
    不暴露 promote/rollback；运维脚本仍走 knowledge/* 入口。
    """
    from core.project_paths import DB_DIR  # noqa: E402

    pointer = DB_DIR / "knowledge_index_active.txt"
    active = _read_knowledge_active_collection()
    policy = _resolve_fallback_policy(None)
    if policy == "layered":
        route_policy = "knowledge-first + layered fallback (dialogue→non_dialogue_raw)"
    else:
        route_policy = "knowledge-first + raw fallback"
    out: dict[str, Any] = {
        "available": bool(active),
        "active_collection": active or None,
        "pointer_path": str(pointer),
        "pointer_exists": pointer.exists(),
        "search_backend": "search_knowledge_units",
        "route_policy": route_policy,
        # Phase 15: 三层 SSOT 与 fallback 策略（见 integration/docs/retrieval-ssot.md）
        # fallback_policy: legacy = 全量 personal_events 补洞；layered = KU→dialogue→non_dialogue
        "ssot": {
            "dialogue": "agentsview_canonical",
            "knowledge": "canonical_knowledge_units",
            "non_dialogue_raw": "personal_events",
            "google_structure": "google_data.normalized_events+light_assertions",
        },
        "fallback_policy": policy,
        "allow_legacy_pad": _resolve_allow_legacy_pad(None),
        "semantic_routes": {
            "cli": "unified_search.py semantic",
            "rest": "POST /search/semantic",
            "mcp": "search_semantic",
        },
        "unit_count": None,
        "db_unit_count": None,
        "version": {},
        "chroma_available": False,
        "google_structure": get_google_structure_status(),
    }

    if active and UNIFIED_DB.exists():
        try:
            con = sqlite3.connect(f"file:{UNIFIED_DB.as_posix()}?mode=ro", uri=True)
            row = con.execute(
                "SELECT version_id, build_id, collection_name, unit_count, status, "
                "created_at, activated_at, checksum "
                "FROM knowledge_index_versions WHERE collection_name=? "
                "ORDER BY created_at DESC LIMIT 1",
                (active,),
            ).fetchone()
            if row:
                out["version"] = {
                    "version_id": row[0],
                    "build_id": row[1],
                    "collection_name": row[2],
                    "unit_count": row[3],
                    "status": row[4],
                    "created_at": row[5],
                    "activated_at": row[6],
                    "checksum": (row[7] or "")[:16] + ("…" if row[7] and len(row[7]) > 16 else ""),
                }
                out["db_unit_count"] = row[3]
                if out["unit_count"] is None:
                    out["unit_count"] = row[3]
            # canonical current count (may span multiple runs for merged index)
            try:
                cur = con.execute(
                    "SELECT COUNT(*) FROM canonical_knowledge_units WHERE status='current'"
                ).fetchone()
                out["canonical_current_count"] = cur[0] if cur else None
            except sqlite3.Error:
                out["canonical_current_count"] = None
            con.close()
        except Exception as e:
            out["db_error"] = str(e)[:120]

    if probe_chroma and active:
        try:
            from chroma_client import ChromaClient  # noqa: E402

            client = ChromaClient(port=_KU_PORT)
            coll = client.get_or_create_collection(active)
            count = coll.count()
            out["unit_count"] = count
            out["chroma_available"] = True
            out["chroma_port"] = _KU_PORT
        except Exception as e:
            out["chroma_error"] = str(e)[:120]

    return out


def search_knowledge_units(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
    include_evidence: bool = False,
    collection_override: Optional[str] = None,
    fallback_policy: str | None = None,
    allow_legacy_pad: bool | None = None,
) -> dict:
    """知识单元混合检索 backend。

    knowledge-first + fallback：先查 active knowledge unit collection（结构化 Q&A），
    再按 fallback_policy 补洞:
      - legacy:  全量 personal_events（旧行为）
      - layered: conversation_turns(dialogue) → personal_events(Google) → 可选 legacy_pad

    返回 route/versions/results，CLI/REST/MCP 共用此唯一 backend。

    query: 自然语言查询
    top_k: 返回条数（默认 5，有界 [1,20]）
    source: 过滤 raw 事件数据源（不影响知识层；layered 下 non_dialogue 默认 Google）
    include_evidence: True=附带 evidence quote（默认只给 refs）
    collection_override: 指定 knowledge collection（canary 用，不改变 active pointer）
    fallback_policy: "legacy" | "layered"；None=读 env PERSONAL_DATA_FALLBACK_POLICY，默认 layered
    allow_legacy_pad: layered 仍不足时是否用非 Google personal_events 填充；默认 True

    返回: {
        "route": "knowledge" | "fallback_raw" | "abstain",
        "reason": str (fallback/abstain 时),
        "fallback_policy": "legacy" | "layered",
        "results": [{"rank","unit_id","subject","answer","score","lifecycle",
                      "confidence","source_message_ref","collection","retrieval_unit"}, ...],
        "versions": {"index_version","build_id","canonical_build_id","unit_count","status"},
    }
    """
    top_k = max(1, min(20, top_k))
    policy = _resolve_fallback_policy(fallback_policy)
    pad_allowed = _resolve_allow_legacy_pad(allow_legacy_pad)
    if not query or not query.strip():
        return {
            "route": "abstain",
            "reason": "empty query",
            "results": [],
            "versions": {},
            "fallback_policy": policy,
        }

    # 延迟 import 避免影响无向量库的环境
    try:
        from chroma_client import ChromaClient, ChromaError  # noqa: E402
        import local_embed  # noqa: E402
    except Exception as e:
        return {
            "route": "fallback_raw",
            "reason": f"vector infra unavailable: {e}",
            "results": [],
            "versions": {},
            "fallback_policy": policy,
        }

    route = "knowledge"
    versions: dict = {}

    # 解析 knowledge collection
    ku_collection = collection_override or _read_knowledge_active_collection()

    # embedding（一次 embed，两路复用）
    embedding = local_embed.embed(query)
    if embedding is None:
        return {
            "route": "fallback_raw",
            "reason": "embedding failed",
            "results": [],
            "versions": {},
            "fallback_policy": policy,
        }

    client = ChromaClient(port=_KU_PORT)

    # --- Phase 1: 知识层检索（top-KU_SLOTS） ---
    ku_results: list[dict] = []
    if ku_collection:
        try:
            cols = client.list_collections()
            col_names = {c if isinstance(c, str) else c.get("name", "") for c in cols}
            if ku_collection in col_names:
                ku_coll = client.get_or_create_collection(ku_collection)
                ku_fetch = max(top_k, _KU_SLOTS)
                kr = ku_coll.query(
                    query_embeddings=[embedding], n_results=ku_fetch,
                    include=["metadatas", "documents", "distances"],
                )
                ku_ids = kr.get("ids", [[]])[0] if kr.get("ids") else []
                ku_docs = kr.get("documents", [[]])[0] if kr.get("documents") else []
                ku_dists = kr.get("distances", [[]])[0] if kr.get("distances") else []
                ku_metas = kr.get("metadatas", [[]])[0] if kr.get("metadatas") else []
                for uid, doc, dist, meta in zip(ku_ids, ku_docs, ku_dists, ku_metas):
                    lc = meta.get("lifecycle", "current") if isinstance(meta, dict) else "current"
                    if lc not in ("current",):
                        continue
                    item = {
                        "unit_id": uid,
                        "subject": meta.get("subject", "") if isinstance(meta, dict) else "",
                        "answer": doc[:300] if doc else "",
                        "score": round(1 - dist, 4) if isinstance(dist, (int, float)) else 0,
                        "lifecycle": lc,
                        "confidence": meta.get("confidence", 0) if isinstance(meta, dict) else 0,
                        "source_message_ref": meta.get("source_message_ref", "") if isinstance(meta, dict) else "",
                        "collection": ku_collection,
                        "retrieval_unit": "knowledge_unit",
                        "rank_reason": "knowledge unit semantic match",
                    }
                    if include_evidence:
                        item["evidence_quote"] = ""
                    ku_results.append(item)
                    if len(ku_results) >= _KU_SLOTS:
                        break

                # 读版本信息
                import sqlite3 as _sql  # noqa: E402
                from core.project_paths import UNIFIED_DB as _UDB  # noqa: E402
                try:
                    con = _sql.connect(f"file:{_UDB.as_posix()}?mode=ro", uri=True)
                    row = con.execute(
                        "SELECT version_id, build_id, canonical_build_id, unit_count, status "
                        "FROM knowledge_index_versions WHERE collection_name=? ORDER BY created_at DESC LIMIT 1",
                        (ku_collection,),
                    ).fetchone()
                    if row:
                        versions = {
                            "index_version": row[0], "build_id": row[1],
                            "canonical_build_id": row[2], "unit_count": row[3], "status": row[4],
                        }
                    con.close()
                except Exception:
                    pass
            else:
                route = "fallback_raw"
        except ChromaError:
            route = "fallback_raw"
    else:
        route = "fallback_raw"

    seen_ids: set[str] = {
        str(x.get("unit_id") or "") for x in ku_results if x.get("unit_id")
    }
    fallback_results: list[dict] = []

    def _remaining() -> int:
        return top_k - len(ku_results) - len(fallback_results)

    def _append_unique(item: dict) -> bool:
        uid = str(item.get("unit_id") or item.get("event_id") or "")
        if uid and uid in seen_ids:
            return False
        if uid:
            seen_ids.add(uid)
        fallback_results.append(item)
        return True

    if policy == "legacy":
        # --- Legacy Phase 2: raw personal_events 检索（补剩余 slot，全源） ---
        raw_target = _remaining()
        if raw_target > 0:
            try:
                raw_fetch = raw_target + 4
                raw_events = _semantic_search(query, top_k=raw_fetch, source=source)
                for ev in raw_events:
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="raw event semantic match",
                    )
                    if _append_unique(item) and len(fallback_results) >= raw_target:
                        break
                if len(fallback_results) > raw_target:
                    del fallback_results[raw_target:]
            except Exception:
                pass
    else:
        # --- Layered Phase 2a: message-level dialogue (canonical_messages) ---
        need = _remaining()
        if need > 0:
            try:
                msg_hits = _search_dialogue_canonical_messages(query, top_k=need + 4)
                for item in msg_hits:
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass

        # --- Layered Phase 2b: dialogue_fallback via conversation_turns ---
        need = _remaining()
        if need > 0:
            try:
                from vector.search_vectors import search_conversation_turns as _search_turns  # noqa: E402

                turns = _search_turns(query, top_k=need + 4, source=source)
                for ev in turns:
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="dialogue",
                        collection=CONVERSATION_TURNS_COLLECTION,
                        rank_reason="dialogue_fallback conversation_turns",
                    )
                    item["collection"] = CONVERSATION_TURNS_COLLECTION
                    item["retrieval_unit"] = "dialogue"
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                # collection missing / chroma error — soft skip
                pass

        # --- Layered Phase 3: non_dialogue_raw (prefer Google personal_events) ---
        need = _remaining()
        if need > 0:
            raw_source = source if source else _NON_DIALOGUE_PREFERRED_SOURCE
            try:
                raw_events = _search_personal_events_filtered(
                    query, top_k=need + 4, source=raw_source,
                )
                for ev in raw_events:
                    if not source and (ev.get("source") or "") != _NON_DIALOGUE_PREFERRED_SOURCE:
                        continue
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="non_dialogue_raw personal_events",
                    )
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass

        # --- Layered Phase 4: optional legacy pad (non-Google personal_events) ---
        need = _remaining()
        if need > 0 and pad_allowed:
            try:
                pad_events = _search_personal_events_filtered(
                    query, top_k=need + 8, source=source,
                )
                for ev in pad_events:
                    src = ev.get("source") or ""
                    if not source and src == _NON_DIALOGUE_PREFERRED_SOURCE:
                        continue
                    item = _raw_event_item(
                        ev,
                        retrieval_unit="event",
                        collection="personal_events",
                        rank_reason="legacy_pad",
                    )
                    _append_unique(item)
                    if _remaining() <= 0:
                        break
            except Exception:
                pass

    # --- 合并 + 排名 ---
    merged = ku_results + fallback_results
    if not merged:
        return {
            "route": "abstain",
            "reason": "no results from either source",
            "results": [],
            "versions": versions,
            "fallback_policy": policy,
        }

    # 去 raw fallback 的 reason（有结果就标 knowledge route）
    if route == "fallback_raw" and ku_results:
        route = "knowledge"

    # 编号
    for i, item in enumerate(merged, 1):
        item["rank"] = i

    return {
        "route": route,
        "results": merged[:top_k],
        "versions": versions,
        "collection": ku_collection or "personal_events",
        "fallback_policy": policy,
    }



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
    """返回数据库+向量库+知识索引的统计概览(给 AI 快速建立认知用)。"""
    out: dict = {
        "total_events": 0,
        "by_source": {},
        "active_months": 0,
    }
    if UNIFIED_DB.exists():
        con = sqlite3.connect(UNIFIED_DB)
        con.row_factory = sqlite3.Row
        out["total_events"] = con.execute("SELECT COUNT(*) FROM unified_events").fetchone()[0]
        out["by_source"] = {
            r[0]: r[1]
            for r in con.execute(
                "SELECT source, COUNT(*) FROM unified_events GROUP BY source ORDER BY 2 DESC"
            )
        }
        out["active_months"] = con.execute(
            "SELECT COUNT(DISTINCT substr(month,1,7)) FROM unified_events WHERE length(month)>=7"
        ).fetchone()[0]
        con.close()
    # 向量库统计(失败不影响主流程)
    try:
        from chroma_client import ChromaClient
        client = ChromaClient()
        coll = client.get_or_create_collection("personal_events")
        out["vector_count"] = coll.count()
        out["vector_available"] = True
        # Wave 7: conversation_turns 独立 collection 统计
        try:
            turns_coll = client.get_or_create_collection("conversation_turns")
            out["conversation_turns_count"] = turns_coll.count()
            out["conversation_turns_available"] = True
        except Exception:
            out["conversation_turns_available"] = False
    except Exception as e:
        out["vector_available"] = False
        out["vector_error"] = str(e)[:120]
    # Phase 14: knowledge index（CLI/REST/MCP 语义检索共用）
    out["knowledge"] = get_knowledge_status(probe_chroma=True)
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


# === 数据访问 contract(list/export/aggregate/timeline)====================

def _bounded_int(value: Any, default: int, lower: int, upper: int) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        n = default
    return max(lower, min(n, upper))


def _split_csv(value: str | list[str] | tuple[str, ...] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        raw = []
        for item in value:
            raw.extend(str(item).split(","))
    else:
        raw = str(value).split(",")
    return [part.strip() for part in raw if part and part.strip()]


def _normalize_event_fields(fields: str | list[str] | None) -> list[str]:
    out = _split_csv(fields) or list(DEFAULT_EVENT_FIELDS)
    unknown = [field for field in out if field not in EVENT_FIELD_SQL]
    if unknown:
        raise ValueError(f"unknown event fields: {', '.join(unknown)}")
    # Preserve request order while removing duplicates.
    return list(dict.fromkeys(out))


def _event_from_clause() -> str:
    return (
        "FROM unified_events ue "
        "LEFT JOIN unified_events_rich r ON r.event_id = ue.event_id "
        "LEFT JOIN event_categories_v2 c ON c.event_id = ue.event_id "
    )


def _event_filter_sql(
    source: Optional[str] = None,
    service: Optional[str] = None,
    category: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    keyword: Optional[str] = None,
) -> tuple[str, list[Any], dict]:
    where = ["1=1"]
    params: list[Any] = []
    filters = {
        "source": source,
        "service": service,
        "category": category,
        "time_from": time_from,
        "time_to": time_to,
        "keyword": keyword,
    }
    if source:
        where.append("ue.source = ?")
        params.append(source)
    if service:
        where.append("ue.service = ?")
        params.append(service)
    if category:
        where.append("c.category_v2 LIKE ?")
        params.append(f"%{category}%")
    if time_from:
        where.append("ue.event_time >= ?")
        params.append(time_from)
    if time_to:
        where.append("ue.event_time <= ?")
        params.append(time_to)
    if keyword:
        where.append("(ue.title LIKE ? OR ue.content LIKE ? OR COALESCE(r.content_rich, '') LIKE ?)")
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    return " WHERE " + " AND ".join(where), params, filters


def list_events_contract(
    source: Optional[str] = None,
    service: Optional[str] = None,
    category: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    keyword: Optional[str] = None,
    fields: str | list[str] | None = None,
    limit: int = DEFAULT_DATA_LIMIT,
    offset: int = 0,
    order: str = "desc",
) -> dict:
    """List unified events with bounded pagination and explicit field selection."""
    limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
    offset = _bounded_int(offset, 0, 0, 10**9)
    order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
    selected_fields = _normalize_event_fields(fields)
    select_sql = ", ".join(
        f"{EVENT_FIELD_SQL[field]} AS {field}" for field in selected_fields
    )
    where_sql, params, filters = _event_filter_sql(
        source=source,
        service=service,
        category=category,
        time_from=time_from,
        time_to=time_to,
        keyword=keyword,
    )

    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        total = con.execute(
            "SELECT COUNT(DISTINCT ue.event_id) " + _event_from_clause() + where_sql,
            params,
        ).fetchone()[0]
        rows = [
            dict(row)
            for row in con.execute(
                "SELECT " + select_sql + " " + _event_from_clause() + where_sql
                + f" ORDER BY ue.event_time {order_sql}, ue.event_id {order_sql} LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
        ]
    finally:
        con.close()

    return {
        "ok": True,
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "fields": selected_fields,
        "filters": filters,
        "items": rows,
        "truncated": offset + len(rows) < total,
    }


def get_event_by_id_contract(event_id: str, fields: str | list[str] | None = None) -> dict:
    """Return one event by id using the same field policy as list_events_contract."""
    selected_fields = _normalize_event_fields(fields)
    select_sql = ", ".join(
        f"{EVENT_FIELD_SQL[field]} AS {field}" for field in selected_fields
    )
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT " + select_sql + " " + _event_from_clause() + "WHERE ue.event_id = ?",
            (event_id,),
        ).fetchone()
    finally:
        con.close()
    return {
        "ok": row is not None,
        "found": row is not None,
        "event_id": event_id,
        "fields": selected_fields,
        "item": dict(row) if row else None,
    }


def export_events_contract(
    export_format: str = "jsonl",
    source: Optional[str] = None,
    service: Optional[str] = None,
    category: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    keyword: Optional[str] = None,
    fields: str | list[str] | None = None,
    limit: int = MAX_EXPORT_LIMIT,
    offset: int = 0,
    order: str = "desc",
) -> dict:
    """Export a bounded event query as json/jsonl/csv inside a contract object."""
    export_format = (export_format or "jsonl").strip().lower()
    if export_format not in {"json", "jsonl", "csv"}:
        raise ValueError("export format must be one of: json, jsonl, csv")
    limit = _bounded_int(limit, MAX_EXPORT_LIMIT, 1, MAX_EXPORT_LIMIT)
    data = list_events_contract(
        source=source,
        service=service,
        category=category,
        time_from=time_from,
        time_to=time_to,
        keyword=keyword,
        fields=fields,
        limit=min(limit, MAX_DATA_LIMIT),
        offset=offset,
        order=order,
    )
    # list_events_contract intentionally caps at MAX_DATA_LIMIT; export has a
    # larger hard cap, so rerun the same query when the caller asked for more.
    if limit > MAX_DATA_LIMIT:
        selected_fields = _normalize_event_fields(fields)
        select_sql = ", ".join(
            f"{EVENT_FIELD_SQL[field]} AS {field}" for field in selected_fields
        )
        where_sql, params, _ = _event_filter_sql(
            source=source,
            service=service,
            category=category,
            time_from=time_from,
            time_to=time_to,
            keyword=keyword,
        )
        order_sql = "ASC" if str(order).lower() == "asc" else "DESC"
        offset_i = _bounded_int(offset, 0, 0, 10**9)
        con = sqlite3.connect(UNIFIED_DB)
        con.row_factory = sqlite3.Row
        try:
            rows = [
                dict(row)
                for row in con.execute(
                    "SELECT " + select_sql + " " + _event_from_clause() + where_sql
                    + f" ORDER BY ue.event_time {order_sql}, ue.event_id {order_sql} LIMIT ? OFFSET ?",
                    params + [limit, offset_i],
                )
            ]
        finally:
            con.close()
        data["items"] = rows
        data["count"] = len(rows)
        data["limit"] = limit
        data["truncated"] = offset_i + len(rows) < data["total"]

    rows = data["items"]
    if export_format == "json":
        content: str | list[dict] = rows
    elif export_format == "jsonl":
        content = "\n".join(json.dumps(row, ensure_ascii=False, default=str) for row in rows)
    else:
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=data["fields"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
        content = buf.getvalue()

    return {
        "ok": True,
        "format": export_format,
        "count": len(rows),
        "total": data["total"],
        "limit": data["limit"],
        "offset": data["offset"],
        "fields": data["fields"],
        "filters": data["filters"],
        "content": content,
        "truncated": data["truncated"],
        "hard_cap": MAX_EXPORT_LIMIT,
    }


def export_all_contract(**kwargs) -> dict:
    """Compatibility wrapper for callers that want an explicit export-all name."""
    return export_events_contract(**kwargs)


def export_query_contract(**kwargs) -> dict:
    """Compatibility wrapper for callers that want an explicit filtered export name."""
    return export_events_contract(**kwargs)


def aggregate_contract(
    group_by: str = "source",
    source: Optional[str] = None,
    service: Optional[str] = None,
    category: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = DEFAULT_DATA_LIMIT,
) -> dict:
    """Aggregate events by one or more supported dimensions."""
    groups = _split_csv(group_by) or ["source"]
    if groups == ["memory_type"]:
        limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
        con = sqlite3.connect(UNIFIED_DB)
        con.row_factory = sqlite3.Row
        try:
            rows = [
                dict(row)
                for row in con.execute(
                    "SELECT memory_type, COUNT(1) AS count FROM memory_items "
                    "GROUP BY memory_type ORDER BY count DESC LIMIT ?",
                    (limit,),
                )
            ]
        finally:
            con.close()
        return {
            "ok": True,
            "group_by": groups,
            "count": len(rows),
            "limit": limit,
            "filters": {},
            "items": rows,
        }
    if groups == ["relation_type"]:
        limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
        con = sqlite3.connect(UNIFIED_DB)
        con.row_factory = sqlite3.Row
        try:
            rule_rows = [
                dict(row)
                for row in con.execute(
                    "SELECT relation AS relation_type, COUNT(1) AS count, 'rule' AS edge_source "
                    "FROM memory_relations GROUP BY relation ORDER BY count DESC LIMIT ?",
                    (limit,),
                )
            ]
            llm_rows = []
            if _table_exists(con, "memory_relation_judgments"):
                llm_rows = [
                    dict(row)
                    for row in con.execute(
                        "SELECT relation_type, COUNT(1) AS count, 'llm_judgment' AS edge_source "
                        "FROM memory_relation_judgments GROUP BY relation_type ORDER BY count DESC LIMIT ?",
                        (limit,),
                    )
                ]
            rows = (rule_rows + llm_rows)[:limit]
        finally:
            con.close()
        return {
            "ok": True,
            "group_by": groups,
            "count": len(rows),
            "limit": limit,
            "filters": {},
            "items": rows,
        }
    unknown = [name for name in groups if name not in AGGREGATE_GROUP_SQL]
    if unknown:
        raise ValueError(f"unknown group_by: {', '.join(unknown)}")
    limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
    select_parts = [
        f"{AGGREGATE_GROUP_SQL[name]} AS {name}" for name in groups
    ]
    group_exprs = [AGGREGATE_GROUP_SQL[name] for name in groups]
    where_sql, params, filters = _event_filter_sql(
        source=source,
        service=service,
        category=category,
        time_from=time_from,
        time_to=time_to,
        keyword=keyword,
    )
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in con.execute(
                "SELECT " + ", ".join(select_parts) + ", COUNT(DISTINCT ue.event_id) AS count "
                + _event_from_clause()
                + where_sql
                + " GROUP BY " + ", ".join(group_exprs)
                + " ORDER BY count DESC LIMIT ?",
                params + [limit],
            )
        ]
    finally:
        con.close()
    return {
        "ok": True,
        "group_by": groups,
        "count": len(rows),
        "limit": limit,
        "filters": filters,
        "items": rows,
    }


def timeline_contract(
    interval: str = "month",
    source: Optional[str] = None,
    service: Optional[str] = None,
    category: Optional[str] = None,
    time_from: Optional[str] = None,
    time_to: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = DEFAULT_DATA_LIMIT,
) -> dict:
    """Return event counts over time. interval: day/month/year."""
    interval = (interval or "month").strip().lower()
    if interval not in {"day", "month", "year"}:
        raise ValueError("interval must be one of: day, month, year")
    bucket_sql = {
        "day": "substr(ue.event_time, 1, 10)",
        "month": "substr(ue.event_time, 1, 7)",
        "year": "substr(ue.event_time, 1, 4)",
    }[interval]
    limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
    where_sql, params, filters = _event_filter_sql(
        source=source,
        service=service,
        category=category,
        time_from=time_from,
        time_to=time_to,
        keyword=keyword,
    )
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        rows = [
            dict(row)
            for row in con.execute(
                f"SELECT {bucket_sql} AS bucket, COUNT(DISTINCT ue.event_id) AS count "
                + _event_from_clause()
                + where_sql
                + " GROUP BY bucket ORDER BY bucket ASC LIMIT ?",
                params + [limit],
            )
        ]
    finally:
        con.close()
    return {
        "ok": True,
        "interval": interval,
        "count": len(rows),
        "limit": limit,
        "filters": filters,
        "items": rows,
    }


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


def _table_exists(con: sqlite3.Connection, table_name: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,),
    ).fetchone()
    return row is not None


def _parse_metadata(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {"raw": raw}


def _parse_json_list(raw: str | None) -> list:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return [raw]
    return data if isinstance(data, list) else [data]


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


def list_memories_contract(
    memory_type: Optional[str] = None,
    memory_subtype: Optional[str] = None,
    subject: Optional[str] = None,
    limit: int = DEFAULT_DATA_LIMIT,
    offset: int = 0,
) -> dict:
    """List memory_items with bounded pagination."""
    limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
    offset = _bounded_int(offset, 0, 0, 10**9)
    if not _memory_layer_ready():
        return {
            "ok": True,
            "available": False,
            "count": 0,
            "total": 0,
            "limit": limit,
            "offset": offset,
            "filters": {
                "memory_type": memory_type,
                "memory_subtype": memory_subtype,
                "subject": subject,
            },
            "items": [],
            "truncated": False,
        }
    where = ["1=1"]
    params: list[Any] = []
    if memory_type:
        where.append("memory_type = ?")
        params.append(memory_type)
    if memory_subtype:
        where.append("memory_subtype = ?")
        params.append(memory_subtype)
    if subject:
        where.append("subject LIKE ?")
        params.append(f"%{subject}%")
    where_sql = " WHERE " + " AND ".join(where)
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        total = con.execute(
            "SELECT COUNT(1) FROM memory_items" + where_sql,
            params,
        ).fetchone()[0]
        rows = [
            _memory_row_to_dict(row)
            for row in con.execute(
                "SELECT memory_id, memory_type, memory_subtype, subject, description, "
                "confidence, evidence_count, metadata, created_at "
                "FROM memory_items"
                + where_sql
                + " ORDER BY evidence_count DESC, confidence DESC, subject LIMIT ? OFFSET ?",
                params + [limit, offset],
            )
        ]
    finally:
        con.close()
    return {
        "ok": True,
        "available": True,
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "memory_type": memory_type,
            "memory_subtype": memory_subtype,
            "subject": subject,
        },
        "items": rows,
        "truncated": offset + len(rows) < total,
    }


def get_memory_by_id_contract(memory_id: str) -> dict:
    """Return one memory item by memory_id."""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        item = _get_memory_by_id(con, memory_id)
        evidence = []
        if item:
            evidence = [
                dict(row)
                for row in con.execute(
                    "SELECT target_type, target_id, relation FROM memory_links "
                    "WHERE memory_id=? ORDER BY id LIMIT 20",
                    (memory_id,),
                )
            ]
    finally:
        con.close()
    return {
        "ok": item is not None,
        "found": item is not None,
        "memory_id": memory_id,
        "item": item,
        "evidence": evidence,
    }


def list_relations_contract(
    relation: Optional[str] = None,
    from_memory_id: Optional[str] = None,
    to_memory_id: Optional[str] = None,
    subject: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = DEFAULT_DATA_LIMIT,
    offset: int = 0,
) -> dict:
    """List persisted memory relations, optionally filtered to LLM judgment status."""
    limit = _bounded_int(limit, DEFAULT_DATA_LIMIT, 1, MAX_DATA_LIMIT)
    offset = _bounded_int(offset, 0, 0, 10**9)
    status = status.strip().lower() if status else None
    if status == "all":
        status = None
    if status and status not in RELATION_REVIEW_STATUSES:
        raise ValueError("status must be one of: review, accepted, rejected")
    where = ["1=1"]
    params: list[Any] = []
    relation_column = "j.relation_type" if status else "mr.relation"
    from_column = "j.source_memory_id" if status else "mr.from_memory_id"
    to_column = "j.target_memory_id" if status else "mr.to_memory_id"
    if relation:
        where.append(f"{relation_column} = ?")
        params.append(relation)
    if from_memory_id:
        where.append(f"{from_column} = ?")
        params.append(from_memory_id)
    if to_memory_id:
        where.append(f"{to_column} = ?")
        params.append(to_memory_id)
    if subject:
        where.append("(src.subject LIKE ? OR dst.subject LIKE ?)")
        kw = f"%{subject}%"
        params.extend([kw, kw])
    if status:
        where.append("j.gate_status = ?")
        params.append(status)
    where_sql = " WHERE " + " AND ".join(where)
    if status:
        table_name = "memory_relation_judgments"
        base_sql = (
            "FROM memory_relation_judgments j "
            "LEFT JOIN memory_items src ON src.memory_id = j.source_memory_id "
            "LEFT JOIN memory_items dst ON dst.memory_id = j.target_memory_id "
        )
        select_sql = (
            "SELECT j.candidate_id AS id, j.candidate_id, j.package_id, "
            "j.source_memory_id AS from_memory_id, j.target_memory_id AS to_memory_id, "
            "j.relation_type AS relation, j.confidence AS strength, j.gate_status AS status, "
            "'llm_judgment' AS edge_source, j.model, j.prompt_version, j.llm_status, j.created_at, "
            "src.subject AS from_subject, src.memory_type AS from_type, "
            "src.memory_subtype AS from_subtype, dst.subject AS to_subject, "
            "dst.memory_type AS to_type, dst.memory_subtype AS to_subtype "
        )
        order_sql = " ORDER BY j.confidence DESC, j.candidate_id LIMIT ? OFFSET ?"
    else:
        table_name = "memory_relations"
        base_sql = (
            "FROM memory_relations mr "
            "JOIN memory_items src ON src.memory_id = mr.from_memory_id "
            "JOIN memory_items dst ON dst.memory_id = mr.to_memory_id "
        )
        select_sql = (
            "SELECT mr.id, mr.from_memory_id, mr.to_memory_id, mr.relation, mr.strength, "
            "src.subject AS from_subject, src.memory_type AS from_type, "
            "src.memory_subtype AS from_subtype, dst.subject AS to_subject, "
            "dst.memory_type AS to_type, dst.memory_subtype AS to_subtype, "
            "'rule' AS edge_source, NULL AS status "
        )
        order_sql = " ORDER BY mr.strength DESC, mr.id LIMIT ? OFFSET ?"
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        if not _table_exists(con, table_name):
            total = 0
            rows = []
        else:
            total = con.execute(
                "SELECT COUNT(1) " + base_sql + where_sql,
                params,
            ).fetchone()[0]
            rows = [
                dict(row)
                for row in con.execute(
                    select_sql + base_sql + where_sql + order_sql,
                    params + [limit, offset],
                )
            ]
    finally:
        con.close()
    return {
        "ok": True,
        "count": len(rows),
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {
            "relation": relation,
            "from_memory_id": from_memory_id,
            "to_memory_id": to_memory_id,
            "subject": subject,
            "status": status,
        },
        "items": rows,
        "truncated": offset + len(rows) < total,
    }


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
            "hint": "记忆层未构建。运行: python integration/scripts/run_pipeline.py --from 5 --skip 10",
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


def data_quality_report_contract() -> dict:
    """Return a compact read-only quality report for the public data contracts."""
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    tables = [
        "unified_events",
        "unified_events_rich",
        "event_categories_v2",
        "memory_items",
        "memory_links",
        "memory_relations",
    ]
    warnings: list[str] = []
    try:
        table_info: dict[str, dict] = {}
        for name in tables:
            exists = _table_exists(con, name)
            count = con.execute(f"SELECT COUNT(1) FROM {name}").fetchone()[0] if exists else 0
            table_info[name] = {"exists": exists, "count": count}
            if not exists:
                warnings.append(f"missing table: {name}")

        events: dict[str, Any] = {"available": table_info["unified_events"]["exists"]}
        if events["available"]:
            events.update({
                "total": table_info["unified_events"]["count"],
                "missing": {
                    "event_id": con.execute(
                        "SELECT COUNT(1) FROM unified_events WHERE event_id IS NULL OR event_id=''"
                    ).fetchone()[0],
                    "source": con.execute(
                        "SELECT COUNT(1) FROM unified_events WHERE source IS NULL OR source=''"
                    ).fetchone()[0],
                    "event_time": con.execute(
                        "SELECT COUNT(1) FROM unified_events WHERE event_time IS NULL OR event_time=''"
                    ).fetchone()[0],
                    "title": con.execute(
                        "SELECT COUNT(1) FROM unified_events WHERE title IS NULL OR title=''"
                    ).fetchone()[0],
                },
                "duplicate_event_ids": con.execute(
                    "SELECT COUNT(1) FROM ("
                    "SELECT event_id FROM unified_events WHERE event_id IS NOT NULL AND event_id!='' "
                    "GROUP BY event_id HAVING COUNT(1) > 1)"
                ).fetchone()[0],
                "event_time_range": dict(con.execute(
                    "SELECT MIN(event_time) AS min, MAX(event_time) AS max FROM unified_events"
                ).fetchone()),
                "by_source": {
                    row["source"]: row["count"]
                    for row in con.execute(
                        "SELECT COALESCE(source, '') AS source, COUNT(1) AS count "
                        "FROM unified_events GROUP BY source ORDER BY count DESC"
                    )
                },
            })

        categories: dict[str, Any] = {"available": table_info["event_categories_v2"]["exists"]}
        if categories["available"]:
            categories.update({
                "total": table_info["event_categories_v2"]["count"],
                "missing_category_v2": con.execute(
                    "SELECT COUNT(1) FROM event_categories_v2 "
                    "WHERE category_v2 IS NULL OR category_v2=''"
                ).fetchone()[0],
            })
            if events.get("available"):
                categories["events_without_category_v2"] = con.execute(
                    "SELECT COUNT(1) FROM unified_events ue "
                    "LEFT JOIN event_categories_v2 c ON c.event_id = ue.event_id "
                    "WHERE c.event_id IS NULL OR c.category_v2 IS NULL OR c.category_v2=''"
                ).fetchone()[0]

        memories: dict[str, Any] = {"available": table_info["memory_items"]["exists"]}
        if memories["available"]:
            memories.update({
                "total": table_info["memory_items"]["count"],
                "missing_subject": con.execute(
                    "SELECT COUNT(1) FROM memory_items WHERE subject IS NULL OR subject=''"
                ).fetchone()[0],
                "by_type": {
                    row["memory_type"]: row["count"]
                    for row in con.execute(
                        "SELECT COALESCE(memory_type, '') AS memory_type, COUNT(1) AS count "
                        "FROM memory_items GROUP BY memory_type ORDER BY count DESC"
                    )
                },
            })

        relations: dict[str, Any] = {"available": table_info["memory_relations"]["exists"]}
        if relations["available"]:
            relations.update({
                "total": table_info["memory_relations"]["count"],
                "by_relation": {
                    row["relation"]: row["count"]
                    for row in con.execute(
                        "SELECT COALESCE(relation, '') AS relation, COUNT(1) AS count "
                        "FROM memory_relations GROUP BY relation ORDER BY count DESC"
                    )
                },
            })
            if memories.get("available"):
                relations["dangling_relations"] = con.execute(
                    "SELECT COUNT(1) FROM memory_relations mr "
                    "LEFT JOIN memory_items src ON src.memory_id = mr.from_memory_id "
                    "LEFT JOIN memory_items dst ON dst.memory_id = mr.to_memory_id "
                    "WHERE src.memory_id IS NULL OR dst.memory_id IS NULL"
                ).fetchone()[0]

        if events.get("missing"):
            for key, value in events["missing"].items():
                if value:
                    warnings.append(f"unified_events missing {key}: {value}")
        if events.get("duplicate_event_ids"):
            warnings.append(f"duplicate event_id groups: {events['duplicate_event_ids']}")
        if relations.get("dangling_relations"):
            warnings.append(f"dangling memory relations: {relations['dangling_relations']}")

        return {
            "ok": True,
            "database": str(UNIFIED_DB),
            "tables": table_info,
            "events": events,
            "categories": categories,
            "memories": memories,
            "relations": relations,
            "warnings": warnings,
        }
    finally:
        con.close()


def _bounded_memory_graph_ids(G: Any, subject: Optional[str], hops: int) -> tuple[set[str], str | None]:
    """Return node ids for whole graph or a subject-scoped weak-neighbor slice."""
    if not subject:
        return set(G.nodes), None
    import query_graph

    start = query_graph.find_node_by_subject(G, subject)
    if start is None:
        return set(), None
    selected = {start}
    frontier = {start}
    undirected = G.to_undirected()
    for _ in range(hops):
        next_level: set[str] = set()
        for node_id in frontier:
            next_level.update(undirected.neighbors(node_id))
        next_level -= selected
        selected |= next_level
        frontier = next_level
        if not frontier:
            break
    return selected, start


def _memory_node_contract(memory_id: str, data: dict) -> dict:
    description = data.get("description") or ""
    return {
        "id": memory_id,
        "memory_id": memory_id,
        "subject": data.get("subject") or "",
        "memory_type": data.get("memory_type") or "",
        "memory_subtype": data.get("memory_subtype") or "",
        "description": description,
        "description_summary": description[:240],
    }


def _memory_edge_contract(source_id: str, target_id: str, key: Any, data: dict) -> dict:
    edge_source = data.get("edge_source") or "rule"
    out = {
        "id": f"{source_id}->{target_id}:{key}",
        "source": source_id,
        "target": target_id,
        "from_memory_id": source_id,
        "to_memory_id": target_id,
        "relation": data.get("relation") or "",
        "strength": float(data.get("strength") or 0.0),
        "edge_source": edge_source,
    }
    if edge_source == "llm_judgment":
        out.update({
            "gate_status": data.get("gate_status"),
            "confidence": float(data.get("confidence") or 0.0),
            "candidate_id": data.get("candidate_id"),
            "reason": data.get("reason") or "",
        })
    return out


def get_memory_graph_contract(
    subject: Optional[str] = None,
    hops: int = 1,
    include_llm: bool = False,
    limit: int = DEFAULT_MEMORY_GRAPH_LIMIT,
) -> dict:
    """Return bounded JSON graph data for Apps SDK widgets.

    This is read-only and reuses query_graph.load_graph instead of parsing generated HTML.
    """
    limit = max(1, min(int(limit), MAX_MEMORY_GRAPH_LIMIT))
    hops = max(0, min(int(hops), 4))
    con = sqlite3.connect(UNIFIED_DB)
    try:
        import query_graph

        G, _, warnings = query_graph.load_graph(con, include_llm_relations=include_llm)
        selected_ids, start_id = _bounded_memory_graph_ids(G, subject, hops)
        # Sort neighbors alphabetically, but always keep seed node first
        # so subject-scoped queries always include the queried subject
        if start_id and start_id in selected_ids:
            non_seed = sorted(
                selected_ids - {start_id},
                key=lambda node_id: (
                    str(G.nodes[node_id].get("memory_type") or ""),
                    str(G.nodes[node_id].get("subject") or ""),
                    str(node_id),
                ),
            )
            scoped_nodes = [start_id] + non_seed
        else:
            scoped_nodes = sorted(
                selected_ids,
                key=lambda node_id: (
                    str(G.nodes[node_id].get("memory_type") or ""),
                    str(G.nodes[node_id].get("subject") or ""),
                    str(node_id),
                ),
            )
        node_limit = min(limit, len(scoped_nodes))
        kept_nodes = set(scoped_nodes[:node_limit])
        edge_rows = [
            (u, v, k, data)
            for u, v, k, data in G.edges(keys=True, data=True)
            if u in selected_ids and v in selected_ids
        ]
        edge_rows.sort(key=lambda item: (
            str(item[3].get("edge_source") or "rule"),
            str(item[3].get("relation") or ""),
            str(item[0]),
            str(item[1]),
            str(item[2]),
        ))
        kept_edge_rows = [
            (u, v, k, data)
            for u, v, k, data in edge_rows
            if u in kept_nodes and v in kept_nodes
        ]
        edge_limit = min(limit, len(kept_edge_rows))
        nodes = [
            _memory_node_contract(node_id, G.nodes[node_id])
            for node_id in scoped_nodes[:node_limit]
        ]
        edges = [
            _memory_edge_contract(u, v, k, data)
            for u, v, k, data in kept_edge_rows[:edge_limit]
        ]
        total_nodes = len(scoped_nodes)
        total_edges = len(edge_rows)
        return {
            "ok": True,
            "scope": {
                "subject": subject,
                "hops": hops,
                "include_llm": include_llm,
                "limit": limit,
                "start_memory_id": start_id,
                "found": bool(selected_ids) if subject else True,
            },
            "counts": {
                "total_nodes": total_nodes,
                "total_edges": total_edges,
                "returned_nodes": len(nodes),
                "returned_edges": len(edges),
                "rule_edges": sum(1 for _, _, _, data in edge_rows if data.get("edge_source") != "llm_judgment"),
                "llm_judgment_edges": sum(1 for _, _, _, data in edge_rows if data.get("edge_source") == "llm_judgment"),
            },
            "nodes": nodes,
            "edges": edges,
            "truncated": len(nodes) < total_nodes or len(edges) < total_edges,
            "warnings": warnings,
        }
    finally:
        con.close()


def get_memory_relation_review_contract(
    limit: int = DEFAULT_RELATION_REVIEW_LIMIT,
    status: Optional[str] = None,
) -> dict:
    """Return read-only LLM relation candidates joined with judgments."""
    limit = max(1, min(int(limit), MAX_RELATION_REVIEW_LIMIT))
    if status:
        status = status.strip().lower()
        if status not in RELATION_REVIEW_STATUSES:
            raise ValueError("status must be one of: review, accepted, rejected")
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
    try:
        import query_graph

        missing = [
            name
            for name in ("memory_relation_candidates", "memory_relation_judgments")
            if not query_graph.table_exists(con, name)
        ]
        if missing:
            return {
                "ok": True,
                "count": 0,
                "items": [],
                "truncated": False,
                "missing_tables": missing,
            }

        where = ""
        params: list[Any] = []
        if status:
            where = "WHERE j.gate_status = ?"
            params.append(status)
        total = con.execute(
            "SELECT COUNT(1) FROM memory_relation_judgments j " + where,
            params,
        ).fetchone()[0]
        rows = con.execute(
            """
            SELECT
                c.candidate_id,
                c.package_id,
                c.source_memory_id,
                c.target_memory_id,
                c.relation_type AS candidate_relation_type,
                c.confidence AS candidate_confidence,
                c.candidate_reason,
                c.evidence_refs_json AS candidate_evidence_refs_json,
                c.source_refs_json AS candidate_source_refs_json,
                c.allowed_refs_json,
                c.risk_flags_json AS candidate_risk_flags_json,
                c.llm_status AS candidate_llm_status,
                c.model AS candidate_model,
                c.prompt_version AS candidate_prompt_version,
                c.created_at AS candidate_created_at,
                j.relation_type,
                j.confidence,
                j.evidence_refs_json,
                j.source_refs_json,
                j.risk_flags_json,
                j.gate_status,
                j.gate_reasons_json,
                j.model,
                j.prompt_version,
                j.llm_status,
                j.created_at,
                src.subject AS source_subject,
                src.memory_type AS source_type,
                src.memory_subtype AS source_subtype,
                src.description AS source_description,
                dst.subject AS target_subject,
                dst.memory_type AS target_type,
                dst.memory_subtype AS target_subtype,
                dst.description AS target_description
            FROM memory_relation_judgments j
            JOIN memory_relation_candidates c ON c.candidate_id = j.candidate_id
            LEFT JOIN memory_items src ON src.memory_id = c.source_memory_id
            LEFT JOIN memory_items dst ON dst.memory_id = c.target_memory_id
            {where}
            ORDER BY j.gate_status, j.confidence DESC, c.candidate_id
            LIMIT ?
            """.format(where=where),
            params + [limit],
        ).fetchall()
    finally:
        con.close()

    items = []
    for row in rows:
        data = dict(row)
        items.append({
            "candidate_id": data["candidate_id"],
            "package_id": data["package_id"],
            "source_memory_id": data["source_memory_id"],
            "target_memory_id": data["target_memory_id"],
            "source_subject": data.get("source_subject"),
            "target_subject": data.get("target_subject"),
            "source_memory": {
                "memory_id": data["source_memory_id"],
                "subject": data.get("source_subject"),
                "memory_type": data.get("source_type"),
                "memory_subtype": data.get("source_subtype"),
                "description": data.get("source_description"),
            },
            "target_memory": {
                "memory_id": data["target_memory_id"],
                "subject": data.get("target_subject"),
                "memory_type": data.get("target_type"),
                "memory_subtype": data.get("target_subtype"),
                "description": data.get("target_description"),
            },
            "relation_type": data["relation_type"],
            "candidate_relation_type": data["candidate_relation_type"],
            "confidence": float(data["confidence"]),
            "candidate_confidence": float(data["candidate_confidence"]),
            "gate_status": data["gate_status"],
            "reason": data["candidate_reason"],
            "candidate_reason": data["candidate_reason"],
            "gate_reasons": _parse_json_list(data.get("gate_reasons_json")),
            "evidence_refs": _parse_json_list(data.get("evidence_refs_json")),
            "source_refs": _parse_json_list(data.get("source_refs_json")),
            "allowed_refs": _parse_json_list(data.get("allowed_refs_json")),
            "risk_flags": _parse_json_list(data.get("risk_flags_json")),
            "model": data["model"],
            "prompt_version": data["prompt_version"],
            "llm_status": data["llm_status"],
            "created_at": data["created_at"],
        })
    return {
        "ok": True,
        "count": len(items),
        "items": items,
        "truncated": len(items) < total,
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
            "hint": "合并层未构建。运行: python integration/scripts/build_merge_layer.py",
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
        description="统一检索层 CLI: 知识混合语义检索 + 精确查询 + 记忆/知识状态",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 语义检索(knowledge-first + layered/legacy fallback；读 active knowledge index)
  python unified_search.py semantic "PPT 排版怎么做" --top-k 3
  python unified_search.py semantic "数据库调试" --source Agent

  # 知识索引状态(active collection / unit_count)
  python unified_search.py knowledge
  python unified_search.py knowledge --json

  # 语义检索 + 去重(合并层折叠重复命中；仅影响 raw 侧展示)
  python unified_search.py semantic "PPT" --top-k 8 --dedup

  # 精确查询(结构化过滤)
  python unified_search.py query --source GPT --month 2025-03
  python unified_search.py query --category 编程 --keyword 报错 --limit 10
  python unified_search.py query --source Agent --dedup --limit 30

  # 单条详情
  python unified_search.py detail <event_id>

  # 统计概览(含 knowledge 块)
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
  python unified_search.py knowledge --json
  python unified_search.py stats --json
  python unified_search.py merge-stats --json
  python unified_search.py cluster --json --limit 500    # 调试用小样本
        """,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("semantic", help="语义检索(knowledge-first + layered/legacy fallback)")
    ps.add_argument("query")
    ps.add_argument("--top-k", type=int, default=5)
    ps.add_argument("--source", default=None)
    ps.add_argument(
        "--fallback-policy",
        choices=["legacy", "layered"],
        default=None,
        help="Hybrid fallback: legacy=KU+personal_events; layered=KU→dialogue→Google. "
             "Default: env PERSONAL_DATA_FALLBACK_POLICY or layered",
    )
    ps.add_argument("--dedup", action="store_true",
                    help="按合并层折叠重复命中(L1/L2 同簇只留代表,附 merged_count)")
    ps.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pk = sub.add_parser("knowledge", help="知识索引状态(active pointer / unit_count)")
    pk.add_argument(
        "--no-chroma",
        action="store_true",
        help="不探测 Chroma，仅读 pointer + SQLite 版本行",
    )
    pk.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

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

    pst = sub.add_parser("stats", help="数据库+向量库+知识索引统计")
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
        ku_result = search_knowledge_units(
            args.query,
            top_k=args.top_k,
            source=args.source,
            fallback_policy=getattr(args, "fallback_policy", None),
        )
        data = ku_result.get("results", [])
        # 在 json 模式下输出 route/versions + results
        if args.json:
            print(json.dumps(ku_result, ensure_ascii=False, indent=2, default=str))
            return
    elif args.cmd == "knowledge":
        data = get_knowledge_status(probe_chroma=not args.no_chroma)
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
        route = ku_result.get("route", "")
        versions = ku_result.get("versions") or {}
        print(f"检索路由: {route or '(n/a)'}  fallback_policy={ku_result.get('fallback_policy', '')}")
        if versions:
            print(
                f"知识索引: {versions.get('index_version') or versions.get('collection') or ''} "
                f"build={versions.get('build_id', '')} units={versions.get('unit_count', '')}"
            )
        if not data:
            print("无匹配结果")
            return
        for i, r in enumerate(data, 1):
            mc = r.get("merged_count")
            tail = f"  (折叠 {mc} 条)" if mc and mc > 1 else ""
            # 兼容 knowledge_unit 和 event 两种结果格式
            unit = r.get("retrieval_unit", "")
            subj = r.get("subject", r.get("title", ""))
            content = r.get("answer", r.get("content", ""))
            src = r.get("source", r.get("collection", ""))
            print(f"\n#{i} [score={r.get('score',0)}] [{src}] {(subj or '(无标题)')[:50]}{tail}")
            print(
                f"   来源库: {r.get('collection','')}  单元: {unit}  原因: {r.get('rank_reason','')}"
            )
            if r.get("event_time"):
                print(f"   时间: {r['event_time']}  分类: {r.get('category_v2','')}")
            c = (content or "")[:200]
            print(f"   内容: {c}{'…' if len(content or '')>200 else ''}")
        print(f"\n共 {len(data)} 条")
    elif args.cmd == "knowledge":
        print(f"知识索引 available: {data.get('available')}")
        print(f"active collection: {data.get('active_collection') or '(none)'}")
        print(f"unit_count: {data.get('unit_count')}")
        print(f"canonical_current: {data.get('canonical_current_count')}")
        print(f"route_policy: {data.get('route_policy')}")
        print(f"fallback_policy: {data.get('fallback_policy')}")
        ssot = data.get("ssot") or {}
        if ssot:
            print(
                f"ssot: dialogue={ssot.get('dialogue')} knowledge={ssot.get('knowledge')} "
                f"non_dialogue_raw={ssot.get('non_dialogue_raw')}"
            )
        gs = data.get("google_structure") or {}
        if gs:
            print(
                f"google_structure: activities={gs.get('activities')} "
                f"normalized={gs.get('normalized_events')} "
                f"assertions={gs.get('light_assertions')} "
                f"by_type={gs.get('assertions_by_type')}"
            )
        print(f"chroma: {'ok' if data.get('chroma_available') else data.get('chroma_error', 'n/a')}")
        ver = data.get("version") or {}
        if ver:
            print(
                f"version: status={ver.get('status')} build={ver.get('build_id')} "
                f"db_units={ver.get('unit_count')} activated={ver.get('activated_at')}"
            )
        routes = data.get("semantic_routes") or {}
        if routes:
            print("semantic routes:")
            for k, v in routes.items():
                print(f"  {k}: {v}")
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
        for s, n in data.get("by_source", {}).items():
            print(f"  {s}: {n:,}")
        if data.get("vector_available"):
            print(f"向量库: {data['vector_count']:,} 条 (personal_events)")
            if data.get("conversation_turns_available"):
                print(f"turn 叙述: {data['conversation_turns_count']:,} 条 (conversation_turns)")
        else:
            print(f"向量库: 不可用({data.get('vector_error','')})")
        ku = data.get("knowledge") or {}
        if ku:
            print(
                f"知识索引: {'available' if ku.get('available') else 'unavailable'} "
                f"collection={ku.get('active_collection') or '(none)'} "
                f"units={ku.get('unit_count')} "
                f"policy={ku.get('route_policy')}"
            )
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
