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

import sqlite3
from pathlib import Path
from typing import Optional

# 让本模块无论被谁 import 都能找到同目录的依赖
import sys
_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

from search_vectors import search as _semantic_search  # noqa: E402

ROOT = _THIS_DIR.parents[1]
UNIFIED_DB = ROOT / "统合模块" / "SQLite数据库" / "personal_system.sqlite"


def search_semantic(
    query: str,
    top_k: int = 5,
    source: Optional[str] = None,
) -> list[dict]:
    """语义检索:自然语言召回用户历史事件。

    query: 自然语言(如"PPT 排版怎么做")
    top_k: 返回条数
    source: 过滤数据源("Google"/"GPT"/"Agent"),None=全源
    返回: list[dict],按相似度降序,字段:
        event_id, source, category_v2, event_type, service,
        event_time, month, title, content, score
    """
    if not query or not query.strip():
        return []
    return _semantic_search(query, top_k=top_k, source=source)


def query_events(
    source: Optional[str] = None,
    month: Optional[str] = None,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    """精确查询:按结构化条件过滤原始 sqlite 库。

    所有参数都是可选的 AND 过滤:
    source:   "Google"/"GPT"/"Agent"
    month:    "2025-03" 或 "2025"(前缀匹配)
    category: category_v2 子串匹配(如"编程")
    keyword:  title + content_rich + content 的子串匹配
    limit:    最多返回条数(默认 50,上限 200)
    返回: list[dict],含 event_id/source/event_time/service/category_v2/title/content_rich
    """
    limit = max(1, min(int(limit), 200))
    con = sqlite3.connect(UNIFIED_DB)
    con.row_factory = sqlite3.Row
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
    params.append(limit)
    rows = [dict(r) for r in con.execute(sql, params)]
    con.close()
    return rows


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

  # 精确查询(结构化过滤)
  python unified_search.py query --source GPT --month 2025-03
  python unified_search.py query --category 编程 --keyword 报错 --limit 10

  # 单条详情
  python unified_search.py detail <event_id>

  # 统计概览
  python unified_search.py stats

  # 向量库聚类/去重(管道加工)
  python unified_search.py cluster --source Agent --threshold 0.92
  python unified_search.py cluster --threshold 0.88 --min-cluster-size 3 --json

  # JSON 输出(便于其他程序消费)—— --json 跟在子命令后
  python unified_search.py semantic "PPT" --json
  python unified_search.py stats --json
  python unified_search.py cluster --json --limit 500    # 调试用小样本
        """,
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("semantic", help="语义检索(自然语言)")
    ps.add_argument("query")
    ps.add_argument("--top-k", type=int, default=5)
    ps.add_argument("--source", default=None)
    ps.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pq = sub.add_parser("query", help="精确查询(结构化过滤)")
    pq.add_argument("--source", default=None)
    pq.add_argument("--month", default=None, help="如 2025-03 或 2025")
    pq.add_argument("--category", default=None, help="category_v2 子串")
    pq.add_argument("--keyword", default=None, help="title+content 子串")
    pq.add_argument("--limit", type=int, default=20)
    pq.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pd = sub.add_parser("detail", help="单条事件详情")
    pd.add_argument("event_id")
    pd.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

    pst = sub.add_parser("stats", help="数据库+向量库统计")
    pst.add_argument("--json", action="store_true", help="输出 JSON(默认人类可读)")

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
        data = search_semantic(args.query, top_k=args.top_k, source=args.source)
    elif args.cmd == "query":
        data = query_events(
            source=args.source, month=args.month,
            category=args.category, keyword=args.keyword, limit=args.limit,
        )
    elif args.cmd == "detail":
        data = get_event_detail(args.event_id)
        if data is None:
            print(f"未找到 event_id={args.event_id}")
            return
    elif args.cmd == "stats":
        data = stats()
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
            print(f"\n#{i} [score={r['score']}] [{r['source']}] {(r.get('title') or '(无标题)')[:50]}")
            print(f"   时间: {r.get('event_time','')}  分类: {r.get('category_v2','')}")
            c = (r.get("content") or "")[:200]
            print(f"   内容: {c}{'…' if len(r.get('content',''))>200 else ''}")
        print(f"\n共 {len(data)} 条")
    elif args.cmd == "query":
        if not data:
            print("无匹配结果")
            return
        for r in data:
            print(f"[{r['source']}] {r['event_time']} | {(r.get('title') or '')[:40]} | {r.get('category_v2','')}")
        print(f"\n共 {len(data)} 条(上限 {args.limit})")
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
