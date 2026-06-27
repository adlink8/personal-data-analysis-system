"""向量检索脚本(给 AI 用)。

从 chroma personal_events collection 做语义检索,返回与查询最相关的事件。
这是"喂给 AI"的核心接口 —— AI 想知道用户历史时,调 search() 召回真实事件。

两种用法:
1. 命令行:python search_vectors.py "PPT 排版怎么做" [--source Agent] [--top-k 5]
2. 模块:from search_vectors import search; results = search("查询")

检索流程:
  查询文本 -> 本地 bge-small-zh-v1.5 向量化 -> chroma cosine 检索 -> 返回 top-K 事件
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

# 用本地 GPU embedding(替代 ollama),接口兼容
import local_embed as ollama_embed
from chroma_client import ChromaClient, ChromaError


COLLECTION_NAME = "personal_events"
CONVERSATION_COLLECTION = "conversation_turns"  # Wave 7 新增:turn 叙述(含因果链)
DEFAULT_TOP_K = 5


def search(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source: Optional[str] = None,
    client: Optional[ChromaClient] = None,
) -> list[dict]:
    """语义检索用户历史事件(personal_events collection)。

    参数:
        query: 自然语言查询(如 "PPT 排版怎么做"、"上次怎么调试数据库的")
        top_k: 返回的最相关事件数
        source: 可选,过滤数据源("Google"/"GPT"/"Agent"),None 则全源检索
        client: 可复用的 ChromaClient(避免重复连接)

    返回: list[dict],按相关度降序,每条含:
        - event_id, source, category_v2, event_time, month, service, title
        - content: 原始内容(chroma 存的 document)
        - score: 相似度分数(chroma distance 转成 0-1 相似度)
    """
    if not query or not query.strip():
        return []

    # 查询向量化
    query_vec = ollama_embed.embed(query)

    # 连 chroma
    if client is None:
        client = ChromaClient()
    coll = client.get_or_create_collection(COLLECTION_NAME)

    # 构造过滤
    where = {"source": source} if source else None

    # 检索
    raw = coll.query(
        query_embeddings=[query_vec],
        n_results=top_k,
        where=where,
        include=["metadatas", "documents", "distances"],
    )

    # 解析结果(chroma 返回的是嵌套列表,每查询一组)
    if not raw.get("ids") or not raw["ids"][0]:
        return []

    results = []
    ids = raw["ids"][0]
    distances = raw.get("distances", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]

    for i, eid in enumerate(ids):
        dist = distances[i] if i < len(distances) else 1.0
        meta = metadatas[i] if i < len(metadatas) else {}
        doc = documents[i] if i < len(documents) else ""
        # chroma cosine distance: 0=完全相同, 2=完全相反
        # 转成相似度: similarity = 1 - distance/2 (范围 0~1)
        similarity = max(0.0, 1.0 - dist / 2.0)
        results.append(
            {
                "event_id": eid,
                "source": meta.get("source", ""),
                "category_v2": meta.get("category_v2", ""),
                "event_type": meta.get("event_type", ""),
                "service": meta.get("service", ""),
                "event_time": meta.get("event_time", ""),
                "month": meta.get("month", ""),
                "title": meta.get("title", ""),
                "content": doc,
                "score": round(similarity, 4),
            }
        )
    return results


def search_conversation_turns(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source: Optional[str] = None,
    client: Optional[ChromaClient] = None,
) -> list[dict]:
    """检索 turn 叙述(conversation_turns collection,Wave 7 新增)。

    与 search() 的区别:检索单元是 turn 级叙述(含 user+assistant+tool 因果链),
    不是单条 message。适合"用户做过什么/怎么做的"类查询。

    collection 不存在或为空时返回 [](向后兼容,不影响主流程)。

    返回: list[dict],每条含:
        - event_id: "{session_id}#{turn_id}"(可回溯)
        - source, event_type(固定 conversation_turn)
        - session_id, turn_id, turn_no, main_topic
        - content: turn 叙述
        - score: 相似度
    """
    if not query or not query.strip():
        return []
    query_vec = ollama_embed.embed(query)
    if client is None:
        client = ChromaClient()
    try:
        coll = client.get_or_create_collection(CONVERSATION_COLLECTION)
    except ChromaError:
        return []

    where = {"source": source} if source else None
    try:
        raw = coll.query(
            query_embeddings=[query_vec],
            n_results=top_k,
            where=where,
            include=["metadatas", "documents", "distances"],
        )
    except ChromaError:
        return []

    if not raw.get("ids") or not raw["ids"][0]:
        return []

    results = []
    ids = raw["ids"][0]
    distances = raw.get("distances", [[]])[0]
    documents = raw.get("documents", [[]])[0]
    metadatas = raw.get("metadatas", [[]])[0]

    for i, eid in enumerate(ids):
        dist = distances[i] if i < len(distances) else 1.0
        meta = metadatas[i] if i < len(metadatas) else {}
        doc = documents[i] if i < len(documents) else ""
        similarity = max(0.0, 1.0 - dist / 2.0)
        results.append({
            "event_id": eid,
            "source": meta.get("source", ""),
            "event_type": meta.get("event_type", "conversation_turn"),
            "session_id": meta.get("session_id", ""),
            "turn_id": meta.get("turn_id", ""),
            "turn_no": meta.get("turn_no", 0),
            "main_topic": meta.get("main_topic", ""),
            "title": meta.get("main_topic", ""),  # 统一字段,便于上层展示
            "category_v2": "对话叙述",  # 标记来源类型,便于区分
            "service": meta.get("source", ""),
            "event_time": "",
            "month": "",
            "content": doc,
            "score": round(similarity, 4),
        })
    return results


def search_all(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    source: Optional[str] = None,
    include_turns: bool = True,
) -> list[dict]:
    """跨 collection 合并检索(personal_events + conversation_turns)。

    Wave 7 主线检索入口:同时搜单条事件和 turn 叙述,按相似度统一排序。
    适合上层(unified_search/MCP/Agent)一站式召回。

    include_turns: True=同时搜 conversation_turns;False=只搜 personal_events
                  (collection 不存在时自动降级为只搜 personal_events)
    """
    if not query or not query.strip():
        return []
    client = ChromaClient()

    # 1. 搜 personal_events(单条事件)
    results = search(query, top_k=top_k, source=source, client=client)

    # 2. 搜 conversation_turns(turn 叙述,失败降级)
    if include_turns:
        try:
            turns = search_conversation_turns(
                query, top_k=top_k, source=source, client=client)
            results.extend(turns)
        except (ChromaError, Exception):
            pass  # collection 不存在或服务问题,降级为只返回 personal_events

    # 3. 统一按 score 降序,裁到 top_k
    results.sort(key=lambda r: r.get("score", 0), reverse=True)
    return results[:top_k]


def format_result(r: dict, show_content: int = 200) -> str:
    """格式化单条结果用于打印。show_content 控制内容显示长度。"""
    lines = [
        f"[{r['score']:.3f}] [{r['source']}] {r['title'] or '(无标题)'}",
        f"    时间: {r['event_time']} | 分类: {r['category_v2']} | 服务: {r['service']}",
    ]
    if r["content"]:
        content = r["content"][:show_content]
        if len(r["content"]) > show_content:
            content += "…"
        lines.append(f"    内容: {content}")
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="语义检索用户历史事件")
    parser.add_argument("query", help="自然语言查询")
    parser.add_argument("--source", default=None, help="过滤数据源(Google/GPT/Agent)")
    parser.add_argument("--top-k", type=int, default=DEFAULT_TOP_K, help="返回条数")
    parser.add_argument("--content-len", type=int, default=200, help="内容显示长度")
    args = parser.parse_args()

    print(f"检索: \"{args.query}\"" + (f" (source={args.source})" if args.source else ""))
    print(f"  top_k={args.top_k}")
    print("-" * 60)

    results = search(args.query, top_k=args.top_k, source=args.source)
    if not results:
        print("无匹配结果(可能向量库未构建,或查询无相关内容)")
        return

    for i, r in enumerate(results, 1):
        print(f"\n#{i}")
        print(format_result(r, show_content=args.content_len))

    print("\n" + "-" * 60)
    print(f"共 {len(results)} 条结果")


if __name__ == "__main__":
    main()
