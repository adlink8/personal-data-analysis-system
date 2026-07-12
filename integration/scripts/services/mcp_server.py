"""个人数据系统 MCP Server —— 把向量库 + 数据库 + 知识索引暴露为 MCP tools。

让任何支持 MCP 的 AI 客户端(Claude Desktop / Cursor / ZCode / Continue 等)
能直接检索用户的历史数据与知识单元,无需手写集成代码。

暴露 18 个 tools(共享同一统合库与检索语义):

  1. search_semantic  knowledge-first + raw fallback 混合语义检索(对齐 REST/CLI)
  2. query_events     按源/时间/分类/关键词精确过滤 sqlite(结构化查询)
  3. get_event_detail 按 event_id 取单条全字段(点开看详情)
  4. stats            数据库 + 向量库 + 知识索引统计概览
  5. knowledge_status active 知识索引状态(collection / unit_count)
  6. list_categories  列出所有 category_v2 分布(帮 AI 知道有哪些维度可过滤)
  7. get_memory_profile 长期记忆概览(tooling/preference/capability/fact/project/habit)
  8. get_memory_by_subject 按主体查询单条记忆 + 图谱关系
  9-18. data_*       对齐 REST /data/* 的分页、导出、聚合、时间线、ID 查询和质量检查

启动方式(stdio 传输,MCP 标准协议):

    python mcp_server.py

客户端配置(Claude Desktop / Cursor / ZCode 等),把下面这段加进 MCP 配置:

    {
      "mcpServers": {
        "personal-data": {
          "command": "python",
          "args": ["C:/Users/li/Desktop/数据分析/integration/scripts/mcp_server.py"]
        }
      }
    }

设计原则:
- Data tools 复用 unified_search.py 的 /data/* contract,直接读取本地 SQLite
- 语义检索调用常驻的本地 REST API,复用已加载的嵌入模型与 Chroma
- 所有 tool 返回结构化文本(AI 友好),内部异常被捕获转成错误提示
- MCP 本身使用 stdio;语义检索只访问 127.0.0.1 本地回环地址
- 每次调用记录简要日志到 stderr(不影响 stdio 协议)
"""

from __future__ import annotations

import os
import json
import sys
import traceback
from pathlib import Path
from urllib.request import Request, urlopen

# Local MCP tools call loopback REST services. In proxy-enabled shells,
# urllib may otherwise route 127.0.0.1 through HTTP_PROXY and return 502.
for _key in ("NO_PROXY", "no_proxy"):
    existing = os.environ.get(_key)
    if existing:
        missing = [host for host in ("127.0.0.1", "localhost") if host not in existing]
        if missing:
            os.environ[_key] = existing + "," + ",".join(missing)
    else:
        os.environ[_key] = "127.0.0.1,localhost"

# 让本模块能找到同目录依赖(unified_search / search_vectors / ...)
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

import mcp.types as types  # noqa: E402
from mcp.server import Server  # noqa: E402
from mcp.server.lowlevel.server import NotificationOptions  # noqa: E402
from mcp.server.models import InitializationOptions  # noqa: E402
from mcp.server.stdio import stdio_server  # noqa: E402

# MCP server 是按客户端启动的短生命周期进程。默认用 CPU 生成查询向量，
# 避免与常驻 REST API 的 GPU 模型发生 CUDA 初始化竞争。
os.environ.setdefault("PERSONAL_DATA_EMBED_DEVICE", "cpu")
import unified_search as backend  # noqa: E402

SEMANTIC_API_URL = os.environ.get(
    "PERSONAL_DATA_SEMANTIC_API",
    "http://127.0.0.1:8000/search/semantic",
)


def _search_semantic_via_api(query: str, top_k: int, source: str | None) -> dict:
    """通过常驻 REST API 调用语义检索，返回 knowledge-first 混合结果。"""
    payload = {"query": query, "top_k": top_k, "source": source}
    request = Request(
        SEMANTIC_API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=120) as response:
        body = json.loads(response.read().decode("utf-8"))
    if not body.get("ok"):
        raise RuntimeError(body.get("error") or "REST API 语义检索失败")
    return body.get("data") or {"route": "abstain", "results": []}


# === Tool 定义 ============================================================
# 每个工具的 schema 用 JSON Schema 描述,MCP 客户端据此渲染调用 UI。

TOOLS = [
    types.Tool(
        name="search_semantic",
        description=(
            "语义检索(knowledge-first + raw fallback)。"
            "先查 active 知识单元索引(结构化 Q&A),再回落 personal_events 原始事件。"
            "适合'我大概记得做过类似的事'这类模糊查询。"
            "返回 route、versions 与结果列表;结果可能是 knowledge_unit 或 event。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "自然语言查询,如 'PPT 排版怎么做'、'上次怎么调试数据库的'",
                },
                "top_k": {
                    "type": "integer",
                    "description": "返回条数(默认 5)",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 20,
                },
                "source": {
                    "type": "string",
                    "description": "过滤 raw 事件数据源:Google / GPT / Agent。不传则全源(不影响知识层)",
                    "enum": ["Google", "GPT", "Agent"],
                },
            },
            "required": ["query"],
        },
    ),
    types.Tool(
        name="query_events",
        description=(
            "精确查询事件(按结构化条件过滤 sqlite)。"
            "适合'列出 2025 年 3 月所有 Agent 事件'这类结构化过滤。"
            "所有参数都是可选的 AND 过滤。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "数据源:Google / GPT / Agent",
                    "enum": ["Google", "GPT", "Agent"],
                },
                "month": {
                    "type": "string",
                    "description": "月份前缀,如 '2025-03' 或 '2025'",
                },
                "category": {
                    "type": "string",
                    "description": "category_v2 子串匹配,如 '编程'、'调试'",
                },
                "keyword": {
                    "type": "string",
                    "description": "title + content_rich 子串匹配",
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回条数(默认 50,上限 200)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
        },
    ),
    types.Tool(
        name="get_event_detail",
        description=(
            "按 event_id 取单条事件全字段(含增强内容 content_rich)。"
            "用于'点开看详情'。通常先用 search_semantic / query_events 拿到 event_id,"
            "再用本工具读完整内容。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {
                    "type": "string",
                    "description": "事件 ID(search_semantic / query_events 返回的 event_id 字段)",
                },
            },
            "required": ["event_id"],
        },
    ),
    types.Tool(
        name="stats",
        description=(
            "数据库 + 向量库 + 知识索引的统计概览。建议 AI 在回答前先调一次,"
            "了解数据总量、按源分布、向量库可用性与 active 知识 collection,建立全局认知。"
        ),
        inputSchema={"type": "object", "properties": {}},
    ),
    types.Tool(
        name="knowledge_status",
        description=(
            "知识单元索引只读状态: active collection 名、unit_count、canonical_current、"
            "route_policy、以及 CLI/REST/MCP 语义入口对应关系。"
            "对齐 GET /knowledge。不执行 promote/rollback。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "probe_chroma": {
                    "type": "boolean",
                    "description": "是否探测 Chroma 实际条数(默认 true)",
                    "default": True,
                },
            },
        },
    ),
    types.Tool(
        name="list_categories",
        description=(
            "列出所有 category_v2 分类及其事件数(降序)。"
            "帮 AI 知道有哪些分类维度可用于 query_events 的 category 过滤。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "可选,只看某个数据源的分类",
                    "enum": ["Google", "GPT", "Agent"],
                },
            },
        },
    ),
    types.Tool(
        name="get_memory_profile",
        description=(
            "获取用户长期记忆概览。"
            "适合在回答前了解用户的工具偏好、能力、项目、事实、习惯和内容偏好。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "memory_type": {
                    "type": "string",
                    "description": "可选过滤: tooling / preference / capability / fact / project / habit",
                    "enum": ["tooling", "preference", "capability", "fact", "project", "habit"],
                },
                "limit": {
                    "type": "integer",
                    "description": "最多返回多少条明细(默认 50)",
                    "default": 50,
                    "minimum": 1,
                    "maximum": 200,
                },
            },
        },
    ),
    types.Tool(
        name="get_memory_by_subject",
        description=(
            "按主体查询长期记忆详情和图谱关系,如 Codex、Python、GSD项目管理。"
            "可选返回 N 跳邻居,用于理解相关工具/能力/项目之间的关系。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "记忆主体,如 Codex",
                },
                "neighbors": {
                    "type": "integer",
                    "description": "可选:返回 N 跳邻居(0=不返回,默认 0)",
                    "default": 0,
                    "minimum": 0,
                    "maximum": 4,
                },
            },
            "required": ["subject"],
        },
    ),
    types.Tool(
        name="data_list_events",
        description="Data.list_events: 对齐 GET /data/events,分页浏览事件,支持来源/服务/分类/时间/关键词/字段/order。",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                "service": {"type": "string"},
                "category": {"type": "string"},
                "category_v2": {"type": "string", "description": "category 的 REST 别名"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "keyword": {"type": "string"},
                "fields": {"type": "string", "description": "逗号分隔字段;默认不返回 content/content_rich"},
                "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
            },
        },
    ),
    types.Tool(
        name="data_list_memories",
        description="Data.list_memories: 对齐 GET /data/memories,分页浏览长期记忆。",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "memory_type": {"type": "string"},
                "memory_subtype": {"type": "string"},
                "subject_like": {"type": "string"},
            },
        },
    ),
    types.Tool(
        name="data_list_relations",
        description="Data.list_relations: 对齐 GET /data/relations,分页浏览规则关系;传 status 时浏览 LLM judgment 关系。",
        inputSchema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "relation_type": {"type": "string"},
                "subject": {"type": "string"},
                "from_memory_id": {"type": "string"},
                "to_memory_id": {"type": "string"},
                "status": {"type": "string", "enum": ["review", "accepted", "rejected", "all"], "default": "all"},
            },
        },
    ),
    types.Tool(
        name="data_aggregate",
        description="Data.aggregate: 对齐 GET /data/aggregate,按 month/source/service/category/memory_type/relation_type 计数。",
        inputSchema={
            "type": "object",
            "properties": {
                "group_by": {
                    "type": "string",
                    "default": "source",
                    "description": "Single group field. Kept for backward compatibility.",
                },
                "group_by_fields": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "enum": ["month", "source", "service", "category", "memory_type", "relation_type"],
                    },
                    "description": "Preferred multi-field grouping, for example ['source', 'service']. Overrides group_by when provided.",
                },
                "metric": {"type": "string", "enum": ["count"], "default": "count"},
                "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                "service": {"type": "string"},
                "category": {"type": "string"},
                "category_v2": {"type": "string"},
                "keyword": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
            },
        },
    ),
    types.Tool(
        name="data_timeline",
        description="Data.timeline: 对齐 GET /data/timeline,按 day/month/year 返回时间线;subject 会映射为关键词过滤。",
        inputSchema={
            "type": "object",
            "properties": {
                "subject": {"type": "string"},
                "bucket": {"type": "string", "enum": ["day", "month", "year"], "default": "month"},
                "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                "service": {"type": "string"},
                "category": {"type": "string"},
                "category_v2": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "limit": {"type": "integer", "default": 100, "minimum": 1, "maximum": 500},
            },
        },
    ),
    types.Tool(
        name="data_export_all",
        description="Data.export_all: 对齐 GET /data/export,有界导出事件切片为 JSONL/CSV/JSON。",
        inputSchema={
            "type": "object",
            "properties": {
                "format": {"type": "string", "enum": ["jsonl", "csv", "json"], "default": "jsonl"},
                "limit": {"type": "integer", "default": 500, "minimum": 1, "maximum": 5000},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                "service": {"type": "string"},
                "category": {"type": "string"},
                "category_v2": {"type": "string"},
                "keyword": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "fields": {"type": "string"},
                "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
            },
        },
    ),
    types.Tool(
        name="data_export_query",
        description="Data.export_query: 对齐 GET /data/export?query=,按关键词和过滤条件有界导出。",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "format": {"type": "string", "enum": ["jsonl", "csv", "json"], "default": "jsonl"},
                "limit": {"type": "integer", "default": 500, "minimum": 1, "maximum": 5000},
                "offset": {"type": "integer", "default": 0, "minimum": 0},
                "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                "service": {"type": "string"},
                "category": {"type": "string"},
                "category_v2": {"type": "string"},
                "keyword": {"type": "string"},
                "start_time": {"type": "string"},
                "end_time": {"type": "string"},
                "fields": {"type": "string"},
                "order": {"type": "string", "enum": ["desc", "asc"], "default": "desc"},
            },
        },
    ),
    types.Tool(
        name="data_get_event_by_id",
        description="Data.get_event_by_id: 对齐 GET /data/event/<event_id>,按精确 event_id 读取事件。",
        inputSchema={
            "type": "object",
            "properties": {
                "event_id": {"type": "string"},
                "fields": {"type": "string"},
            },
            "required": ["event_id"],
        },
    ),
    types.Tool(
        name="data_get_memory_by_id",
        description="Data.get_memory_by_id: 对齐 GET /data/memory/<memory_id>,按精确 memory_id 读取长期记忆。",
        inputSchema={
            "type": "object",
            "properties": {
                "memory_id": {"type": "string"},
            },
            "required": ["memory_id"],
        },
    ),
    types.Tool(
        name="data_quality_report",
        description="Data.data_quality_report: 对齐 GET /data/quality,返回重复、缺失字段、断链、LLM judgment 状态等只读质量报告。",
        inputSchema={"type": "object", "properties": {}},
    ),
]


# === Tool 实现 ============================================================

def _format_semantic(ku_result: dict) -> str:
    """把混合检索结果格式化成 AI 友好的文本。

    ku_result: {"route": str, "results": list[dict], "versions": dict}
    """
    results = ku_result.get("results", [])
    route = ku_result.get("route", "")
    versions = ku_result.get("versions") or {}
    if not results:
        return (
            f"无匹配结果(route={route or 'n/a'})。"
            "可能知识索引未 promote、向量库未构建,或查询无相关内容。"
        )
    lines = [
        f"检索路由: {route}  共召回 {len(results)} 条(knowledge-first + raw fallback):",
    ]
    if versions:
        lines.append(
            f"知识索引版本: {versions.get('index_version') or versions.get('collection') or ''} "
            f"build={versions.get('build_id', '')} units={versions.get('unit_count', '')}"
        )
    lines.append("")
    for i, r in enumerate(results, 1):
        unit = r.get("retrieval_unit", "")
        subj = r.get("subject", r.get("title", ""))
        src = r.get("source", r.get("collection", ""))
        lines.append(
            f"#{i} [score={r.get('score', '?')}] [{src}] "
            f"{(subj or '(无标题)')[:60]}"
        )
        if unit:
            lines.append(f"   retrieval_unit: {unit}")
        if r.get("event_id"):
            lines.append(f"   event_id: {r['event_id']}")
        if r.get("unit_id"):
            lines.append(f"   unit_id: {r['unit_id']}")
        if r.get("event_time"):
            lines.append(
                f"   时间: {r.get('event_time', '')} | 分类: {r.get('category_v2', '')} | "
                f"服务: {r.get('service', '')}"
            )
        content = (r.get("answer") or r.get("content") or "")[:400]
        if len(r.get("answer") or r.get("content") or "") > 400:
            content += "…"
        lines.append(f"   内容: {content}")
        lines.append("")
    return "\n".join(lines)


def _format_query(results: list[dict]) -> str:
    """把精确查询结果格式化。"""
    if not results:
        return "无匹配结果。"
    lines = [f"共 {len(results)} 条(按时间倒序):", ""]
    for r in results:
        lines.append(
            f"[{r.get('source', '?')}] {r.get('event_time', '')} | "
            f"{(r.get('title') or '(无标题)')[:50]} | {r.get('category_v2', '')}"
        )
        lines.append(f"   event_id: {r.get('event_id', '')}")
    return "\n".join(lines)


def _format_detail(data: dict) -> str:
    """把单条详情格式化(全字段)。"""
    lines = []
    for k, v in data.items():
        val = "" if v is None else str(v)
        lines.append(f"{k}: {val}")
    return "\n".join(lines)


def _format_stats(data: dict) -> str:
    lines = [
        f"总事件数: {data.get('total_events', 0):,}",
        f"活跃月份: {data.get('active_months', 0)}",
        "按源分布:",
    ]
    for s, n in data.get("by_source", {}).items():
        lines.append(f"  {s}: {n:,}")
    if data.get("vector_available"):
        lines.append(f"向量库: {data.get('vector_count', 0):,} 条(可语义检索)")
    else:
        lines.append(f"向量库: 不可用({data.get('vector_error', '')})")
    ku = data.get("knowledge") or {}
    if ku:
        lines.append(
            f"知识索引: available={ku.get('available')} "
            f"collection={ku.get('active_collection') or '(none)'} "
            f"units={ku.get('unit_count')} "
            f"policy={ku.get('route_policy')}"
        )
    return "\n".join(lines)


def _format_knowledge_status(data: dict) -> str:
    lines = [
        f"available: {data.get('available')}",
        f"active_collection: {data.get('active_collection') or '(none)'}",
        f"unit_count: {data.get('unit_count')}",
        f"db_unit_count: {data.get('db_unit_count')}",
        f"canonical_current_count: {data.get('canonical_current_count')}",
        f"route_policy: {data.get('route_policy')}",
        f"fallback_policy: {data.get('fallback_policy')}",
        f"ssot: {data.get('ssot')}",
        f"chroma_available: {data.get('chroma_available')}",
    ]
    if data.get("chroma_error"):
        lines.append(f"chroma_error: {data.get('chroma_error')}")
    ver = data.get("version") or {}
    if ver:
        lines.append(
            f"version: status={ver.get('status')} build={ver.get('build_id')} "
            f"activated={ver.get('activated_at')}"
        )
    routes = data.get("semantic_routes") or {}
    if routes:
        lines.append("semantic_routes:")
        for k, v in routes.items():
            lines.append(f"  {k}: {v}")
    return "\n".join(lines)


def _format_categories(rows: list[dict]) -> str:
    if not rows:
        return "无分类数据。"
    lines = [f"共 {len(rows)} 个分类(降序):", ""]
    for r in rows:
        lines.append(f"  {r['category_v2']}: {r['n']}")
    return "\n".join(lines)


def _format_memory_profile(data: dict) -> str:
    if not data.get("available"):
        return data.get("hint", "记忆层未构建。")
    lines = [f"记忆总数: {data.get('total', 0)}", "按类型:"]
    for t, n in data.get("by_type", {}).items():
        lines.append(f"  {t}: {n}")
    lines.append("")
    lines.append("明细:")
    for item in data.get("items", [])[:50]:
        lines.append(
            f"- [{item.get('memory_type')}/{item.get('memory_subtype')}] "
            f"{item.get('subject')} | 证据 {item.get('evidence_count')} | "
            f"置信 {item.get('confidence')}"
        )
        lines.append(f"  {item.get('description', '')[:240]}")
    return "\n".join(lines)


def _format_memory_detail(data: dict) -> str:
    memory = data.get("memory") or {}
    lines = [
        f"[{memory.get('memory_type')}/{memory.get('memory_subtype')}] {memory.get('subject')}",
        f"置信度: {memory.get('confidence')} | 证据数: {memory.get('evidence_count')}",
        f"描述: {memory.get('description', '')}",
    ]
    relations = data.get("relations") or []
    if relations:
        lines.extend(["", "关系:"])
        for r in relations[:30]:
            lines.append(
                f"- {r.get('from_subject')} --{r.get('relation')}({r.get('strength')})--> "
                f"{r.get('to_subject')}"
            )
    neighbors = data.get("neighbors") or {}
    if neighbors.get("levels"):
        lines.extend(["", "邻居:"])
        for level in neighbors["levels"]:
            nodes = ", ".join(
                f"{n.get('subject')}[{n.get('memory_type')}]" for n in level.get("nodes", [])
            )
            lines.append(f"- {level.get('hop')}跳: {nodes or '(无)'}")
    return "\n".join(lines)


def _json_contract(data: dict) -> str:
    """Return contract JSON as tool text so every MCP client can consume it."""
    return json.dumps(data, ensure_ascii=False, default=str, indent=2)


def _event_contract_args(arguments: dict) -> dict:
    return {
        "source": arguments.get("source"),
        "service": arguments.get("service"),
        "category": arguments.get("category") or arguments.get("category_v2"),
        "time_from": arguments.get("time_from") or arguments.get("start_time"),
        "time_to": arguments.get("time_to") or arguments.get("end_time"),
        "keyword": arguments.get("keyword") or arguments.get("query"),
    }


# === MCP Server ===========================================================

server = Server("personal-data")


@server.list_tools()
async def handle_list_tools() -> list[types.Tool]:
    """声明本 server 提供哪些 tools。客户端启动时调一次。"""
    return TOOLS


@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> list[types.TextContent]:
    """处理 tool 调用。所有异常都转成文本返回,避免 server 崩溃。"""
    arguments = arguments or {}
    # 日志走 stderr,不污染 stdio 协议
    print(f"[mcp] call {name} args={arguments}", file=sys.stderr, flush=True)

    try:
        if name == "search_semantic":
            results = _search_semantic_via_api(
                query=arguments.get("query", ""),
                top_k=arguments.get("top_k", 5),
                source=arguments.get("source"),
            )
            text = _format_semantic(results)

        elif name == "query_events":
            results = backend.query_events(
                source=arguments.get("source"),
                month=arguments.get("month"),
                category=arguments.get("category"),
                keyword=arguments.get("keyword"),
                limit=arguments.get("limit", 50),
            )
            text = _format_query(results)

        elif name == "get_event_detail":
            data = backend.get_event_detail(arguments.get("event_id", ""))
            if data is None:
                text = f"未找到 event_id={arguments.get('event_id', '')}"
            else:
                text = _format_detail(data)

        elif name == "stats":
            data = backend.stats()
            text = _format_stats(data)

        elif name == "knowledge_status":
            probe = arguments.get("probe_chroma", True)
            if isinstance(probe, str):
                probe = probe.strip().lower() not in {"0", "false", "no", "off"}
            data = backend.get_knowledge_status(probe_chroma=bool(probe))
            text = _format_knowledge_status(data)

        elif name == "list_categories":
            rows = backend.list_categories(arguments.get("source"))
            text = _format_categories(rows)

        elif name == "get_memory_profile":
            data = backend.get_memory_profile(
                memory_type=arguments.get("memory_type"),
                limit=arguments.get("limit", 50),
            )
            text = _format_memory_profile(data)

        elif name == "get_memory_by_subject":
            subject = arguments.get("subject", "")
            data = backend.get_memory_by_subject(subject)
            if data is None:
                text = f"未找到 memory subject={subject}"
            else:
                neighbors = int(arguments.get("neighbors", 0) or 0)
                if neighbors:
                    data["neighbors"] = backend.get_memory_neighbors(subject, neighbors)
                text = _format_memory_detail(data)

        elif name == "data_list_events":
            data = backend.list_events_contract(
                **_event_contract_args(arguments),
                fields=arguments.get("fields"),
                limit=arguments.get("limit", backend.DEFAULT_DATA_LIMIT),
                offset=arguments.get("offset", 0),
                order=arguments.get("order", "desc"),
            )
            text = _json_contract(data)

        elif name == "data_list_memories":
            data = backend.list_memories_contract(
                memory_type=arguments.get("memory_type"),
                memory_subtype=arguments.get("memory_subtype"),
                subject=arguments.get("subject") or arguments.get("subject_like"),
                limit=arguments.get("limit", backend.DEFAULT_DATA_LIMIT),
                offset=arguments.get("offset", 0),
            )
            text = _json_contract(data)

        elif name == "data_list_relations":
            data = backend.list_relations_contract(
                relation=arguments.get("relation") or arguments.get("relation_type"),
                from_memory_id=arguments.get("from_memory_id"),
                to_memory_id=arguments.get("to_memory_id"),
                subject=arguments.get("subject"),
                status=arguments.get("status"),
                limit=arguments.get("limit", backend.DEFAULT_DATA_LIMIT),
                offset=arguments.get("offset", 0),
            )
            text = _json_contract(data)

        elif name == "data_aggregate":
            group_by_fields = arguments.get("group_by_fields") or []
            group_by = ",".join(group_by_fields) if isinstance(group_by_fields, list) and group_by_fields else arguments.get("group_by", "source")
            data = backend.aggregate_contract(
                group_by=group_by,
                **_event_contract_args(arguments),
                limit=arguments.get("limit", backend.DEFAULT_DATA_LIMIT),
            )
            text = _json_contract(data)

        elif name == "data_timeline":
            event_args = _event_contract_args(arguments)
            subject = arguments.get("subject")
            if subject and not event_args.get("keyword"):
                event_args["keyword"] = subject
            data = backend.timeline_contract(
                interval=arguments.get("interval") or arguments.get("bucket") or "month",
                **event_args,
                limit=arguments.get("limit", backend.DEFAULT_DATA_LIMIT),
            )
            text = _json_contract(data)

        elif name == "data_export_all":
            data = backend.export_all_contract(
                export_format=arguments.get("format", "jsonl"),
                **_event_contract_args(arguments),
                fields=arguments.get("fields"),
                limit=arguments.get("limit", backend.MAX_EXPORT_LIMIT),
                offset=arguments.get("offset", 0),
                order=arguments.get("order", "desc"),
            )
            text = _json_contract(data)

        elif name == "data_export_query":
            event_args = _event_contract_args(arguments)
            if arguments.get("query") and not event_args.get("keyword"):
                event_args["keyword"] = arguments.get("query")
            data = backend.export_query_contract(
                export_format=arguments.get("format", "jsonl"),
                **event_args,
                fields=arguments.get("fields"),
                limit=arguments.get("limit", backend.MAX_EXPORT_LIMIT),
                offset=arguments.get("offset", 0),
                order=arguments.get("order", "desc"),
            )
            text = _json_contract(data)

        elif name == "data_get_event_by_id":
            data = backend.get_event_by_id_contract(
                arguments.get("event_id", ""),
                fields=arguments.get("fields"),
            )
            text = _json_contract(data)

        elif name == "data_get_memory_by_id":
            data = backend.get_memory_by_id_contract(arguments.get("memory_id", ""))
            text = _json_contract(data)

        elif name == "data_quality_report":
            text = _json_contract(backend.data_quality_report_contract())

        else:
            text = f"未知工具: {name}"

    except Exception as e:
        # 捕获所有异常,返回错误信息(而非让 server 崩溃)
        tb = traceback.format_exc()
        text = f"工具 {name} 执行失败: {e}\n\n{tb}"
        print(f"[mcp] error {name}: {e}", file=sys.stderr, flush=True)

    return [types.TextContent(type="text", text=text)]


async def main() -> None:
    """stdio 模式启动 server。"""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="personal-data",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
