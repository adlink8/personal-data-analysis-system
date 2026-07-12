"""个人数据系统 REST API —— 把向量库 + 数据库暴露成 HTTP 接口。

用 Python 标准库 http.server 实现,零额外依赖。覆盖两种接入场景:
1. API 调用:任何能发 HTTP 请求的程序(curl/Postman/前端/其他服务)都能检索用户历史
2. RAG 平台接入:Dify / FastGPT / Coze 等平台都能配"自定义 HTTP 工具"接进来

所有接口内部都走 unified_search 后端,和 CLI / MCP 行为完全一致。

=== 接口列表 ============================================================

GET  /stats                 数据库 + 向量库统计概览
GET  /categories            所有 category_v2 分布(?source=可选过滤)
GET  /memory                长期记忆概览(?type=可选过滤)
GET  /memory/<subject>      单条记忆详情 + 关系(?neighbors=N 可选)
POST /search/semantic       语义检索(自然语言 → 向量库召回)
POST /search/query          精确查询(结构化条件过滤 sqlite)
GET  /event/<event_id>      单条事件全字段
GET  /profile               返回 AI 长期上下文文档内容(RAG 注入用)
GET  /health                健康检查

GET  接口也可改用 POST(方便前端统一处理),参数走 query string。
POST 接口参数走 JSON body。

=== 启动 ================================================================

    python api_server.py [--host 127.0.0.1] [--port 8000]

默认只监听 127.0.0.1(本地安全,不对外暴露)。

=== 示例 ================================================================

    # 统计概览
    curl http://127.0.0.1:8000/stats

    # 语义检索(POST + JSON)
    curl -X POST http://127.0.0.1:8000/search/semantic ^
         -H "Content-Type: application/json" ^
         -d "{\"query\": \"PPT 排版\", \"top_k\": 3}"

    # 精确查询
    curl -X POST http://127.0.0.1:8000/search/query ^
         -H "Content-Type: application/json" ^
         -d "{\"source\": \"Agent\", \"month\": \"2025-03\"}"

    # 拿 AI 长期上下文文档(注入 RAG / system prompt)
    curl http://127.0.0.1:8000/profile

设计原则:
- 纯标准库,装了 Python 就能跑,不强求 Flask/FastAPI
- 统一返回 {"ok": bool, "data": ..., "error": ...} 结构
- 内部异常不泄露栈,只回简短错误信息
- 默认 127.0.0.1 only,需要对外自己加反代 + 鉴权
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

# 让本模块能找到同目录依赖
_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
_THIS_DIR = _SCRIPTS_DIR  # legacy alias: scripts root for resource paths

import unified_search as backend  # noqa: E402

# AI 长期上下文文档路径(给 /profile 用)
ROOT = _THIS_DIR.parents[1]
PROFILE_MD = ROOT / "integration" / "analysis" / "ai_context" / "person_profile.md"

def _ok(data) -> bytes:
    return json.dumps(
        {"ok": True, "data": data}, ensure_ascii=False, default=str
    ).encode("utf-8")


def _contract(data) -> bytes:
    return json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")


def _err(msg: str, code: int = 400) -> tuple[bytes, int]:
    return (
        json.dumps({"ok": False, "error": msg}, ensure_ascii=False).encode("utf-8"),
        code,
    )


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _data_filters(qs: dict) -> dict:
    return {
        "source": qs.get("source"),
        "service": qs.get("service"),
        "category": qs.get("category") or qs.get("category_v2"),
        "time_from": (
            qs.get("time_from")
            or qs.get("start_time")
            or qs.get("from")
            or qs.get("start")
        ),
        "time_to": (
            qs.get("time_to")
            or qs.get("end_time")
            or qs.get("to")
            or qs.get("end")
        ),
        "keyword": qs.get("keyword") or qs.get("q"),
    }


class Handler(BaseHTTPRequestHandler):
    # 静音默认日志(太吵),自己打一行精简的
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[api] {self.command} {self.path} -> {args[1]}\n")

    def _send(self, body: bytes, code: int = 200, ctype: str = "application/json"):
        self.send_response(code)
        self.send_header("Content-Type", f"{ctype}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        # 允许本地前端/平台跨域调用
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        """读 JSON body,空/非法返回 {}。"""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):  # CORS 预检
        self._send(b"", 204)

    # --- GET 路由 ----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}

        try:
            if path == "/health":
                self._send(_ok({"status": "ok"}))
                return

            if path == "/stats":
                self._send(_ok(backend.stats()))
                return

            if path == "/categories":
                rows = backend.list_categories(qs.get("source"))
                self._send(_ok(rows))
                return

            if path == "/data/events":
                data = backend.list_events_contract(
                    **_data_filters(qs),
                    fields=qs.get("fields"),
                    limit=int(qs.get("limit", backend.DEFAULT_DATA_LIMIT)),
                    offset=int(qs.get("offset", 0)),
                    order=qs.get("order", "desc"),
                )
                self._send(_contract(data))
                return

            if path == "/data/memories":
                data = backend.list_memories_contract(
                    memory_type=qs.get("type") or qs.get("memory_type"),
                    memory_subtype=qs.get("subtype") or qs.get("memory_subtype"),
                    subject=qs.get("subject") or qs.get("subject_like"),
                    limit=int(qs.get("limit", backend.DEFAULT_DATA_LIMIT)),
                    offset=int(qs.get("offset", 0)),
                )
                self._send(_contract(data))
                return

            if path == "/data/relations":
                data = backend.list_relations_contract(
                    relation=qs.get("relation") or qs.get("relation_type"),
                    from_memory_id=qs.get("from_memory_id"),
                    to_memory_id=qs.get("to_memory_id"),
                    subject=qs.get("subject"),
                    status=qs.get("status"),
                    limit=int(qs.get("limit", backend.DEFAULT_DATA_LIMIT)),
                    offset=int(qs.get("offset", 0)),
                )
                self._send(_contract(data))
                return

            if path == "/data/aggregate":
                data = backend.aggregate_contract(
                    group_by=qs.get("group_by", "source"),
                    **_data_filters(qs),
                    limit=int(qs.get("limit", backend.DEFAULT_DATA_LIMIT)),
                )
                self._send(_contract(data))
                return

            if path == "/data/timeline":
                filters = _data_filters(qs)
                if qs.get("subject") and not filters.get("keyword"):
                    filters["keyword"] = qs.get("subject")
                data = backend.timeline_contract(
                    interval=qs.get("interval") or qs.get("bucket") or "month",
                    **filters,
                    limit=int(qs.get("limit", backend.DEFAULT_DATA_LIMIT)),
                )
                self._send(_contract(data))
                return

            if path == "/data/export":
                filters = _data_filters(qs)
                if qs.get("query") and not filters.get("keyword"):
                    filters["keyword"] = qs.get("query")
                data = backend.export_events_contract(
                    export_format=qs.get("format", "jsonl"),
                    **filters,
                    fields=qs.get("fields"),
                    limit=int(qs.get("limit", backend.MAX_EXPORT_LIMIT)),
                    offset=int(qs.get("offset", 0)),
                    order=qs.get("order", "desc"),
                )
                self._send(_contract(data))
                return

            if path == "/data/quality":
                self._send(_contract(backend.data_quality_report_contract()))
                return

            if path.startswith("/data/event/"):
                event_id = unquote(path[len("/data/event/"):])
                if not event_id:
                    body, code = _err("缺少 event_id", 400)
                    self._send(body, code)
                    return
                data = backend.get_event_by_id_contract(event_id, fields=qs.get("fields"))
                self._send(_contract(data), 200 if data.get("found") else 404)
                return

            if path.startswith("/data/memory/"):
                memory_id = unquote(path[len("/data/memory/"):])
                if not memory_id:
                    body, code = _err("缺少 memory_id", 400)
                    self._send(body, code)
                    return
                data = backend.get_memory_by_id_contract(memory_id)
                self._send(_contract(data), 200 if data.get("found") else 404)
                return

            if path == "/memory":
                rows = backend.get_memory_profile(
                    memory_type=qs.get("type"),
                    limit=int(qs.get("limit", 200)),
                )
                self._send(_ok(rows))
                return

            if path == "/memory/graph":
                data = backend.get_memory_graph_contract(
                    subject=qs.get("subject"),
                    hops=int(qs.get("hops", 1)),
                    include_llm=_truthy(qs.get("include_llm")),
                    limit=int(qs.get("limit", backend.DEFAULT_MEMORY_GRAPH_LIMIT)),
                )
                self._send(_contract(data))
                return

            if path == "/memory/relation-review":
                data = backend.get_memory_relation_review_contract(
                    limit=int(qs.get("limit", backend.DEFAULT_RELATION_REVIEW_LIMIT)),
                    status=qs.get("status"),
                )
                self._send(_contract(data))
                return

            if path.startswith("/memory/"):
                subject = unquote(path[len("/memory/"):])
                if not subject:
                    body, code = _err("缺少 memory subject", 400)
                    self._send(body, code)
                    return
                data = backend.get_memory_by_subject(subject)
                if data is None:
                    body, code = _err(f"未找到 memory subject={subject}", 404)
                    self._send(body, code)
                    return
                if qs.get("neighbors"):
                    data["neighbors"] = backend.get_memory_neighbors(
                        subject, int(qs.get("neighbors", 2))
                    )
                self._send(_ok(data))
                return

            if path == "/profile":
                if not PROFILE_MD.exists():
                    body, code = _err("AI 上下文文档未生成,请先跑 build_context_doc.py", 404)
                    self._send(body, code)
                    return
                text = PROFILE_MD.read_text(encoding="utf-8")
                self._send(_ok({"profile": text, "path": str(PROFILE_MD)}))
                return

            if path.startswith("/event/"):
                event_id = path[len("/event/"):]
                if not event_id:
                    body, code = _err("缺少 event_id", 400)
                    self._send(body, code)
                    return
                data = backend.get_event_detail(event_id)
                if data is None:
                    body, code = _err(f"未找到 event_id={event_id}", 404)
                    self._send(body, code)
                else:
                    self._send(_ok(data))
                return

            body, code = _err(f"未知路径: {path}", 404)
            self._send(body, code)

        except ValueError as e:
            body, code = _err(str(e), 400)
            self._send(body, code)
        except Exception as e:
            traceback.print_exc()
            body, code = _err(f"内部错误: {e}", 500)
            self._send(body, code)

    # --- POST 路由 ---------------------------------------------------------
    def do_POST(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        body = self._read_body()

        try:
            if path == "/search/semantic":
                query = body.get("query", "").strip()
                if not query:
                    b, c = _err("缺少 query 参数")
                    self._send(b, c)
                    return
                result = backend.search_knowledge_units(
                    query=query,
                    top_k=int(body.get("top_k", 5)),
                    source=body.get("source"),
                )
                self._send(_ok(result))
                return

            if path == "/search/query":
                results = backend.query_events(
                    source=body.get("source"),
                    month=body.get("month"),
                    category=body.get("category"),
                    keyword=body.get("keyword"),
                    limit=int(body.get("limit", 50)),
                )
                self._send(_ok(results))
                return

            body_b, code = _err(f"未知路径: {path}", 404)
            self._send(body_b, code)

        except Exception as e:
            traceback.print_exc()
            body_b, code = _err(f"内部错误: {e}", 500)
            self._send(body_b, code)

def main() -> None:
    p = argparse.ArgumentParser(description="个人数据系统 REST API")
    p.add_argument("--host", default="127.0.0.1", help="监听地址(默认 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="监听端口(默认 8000)")
    args = p.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[api] 个人数据 REST API 启动:")
    print(f"[api]   http://{args.host}:{args.port}")
    print(f"[api] 接口:")
    print(f"[api]   GET  /health               健康检查")
    print(f"[api]   GET  /stats                数据库+向量库统计")
    print(f"[api]   GET  /categories           分类分布(?source=可选)")
    print(f"[api]   GET  /memory               长期记忆概览(?type=可选)")
    print(f"[api]   GET  /memory/<subject>     单条记忆详情(+?neighbors=N)")
    print(f"[api]   POST /search/semantic      语义检索(向量库)")
    print(f"[api]   POST /search/query         精确查询(sqlite)")
    print(f"[api]   GET  /event/<id>           单条事件详情")
    print(f"[api]   GET  /profile              AI 长期上下文文档(RAG 注入)")
    print(f"[api] Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[api] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
