"""个人数据系统 REST API —— 把向量库 + 数据库暴露成 HTTP 接口。

用 Python 标准库 http.server 实现,零额外依赖。覆盖两种接入场景:
1. API 调用:任何能发 HTTP 请求的程序(curl/Postman/前端/其他服务)都能检索用户历史
2. RAG 平台接入:Dify / FastGPT / Coze 等平台都能配"自定义 HTTP 工具"接进来

所有接口内部都走 unified_search 后端,和 CLI / MCP 行为完全一致。

=== 接口列表 ============================================================

GET  /stats                 数据库 + 向量库 + 知识索引统计概览
GET  /knowledge             知识索引状态(active collection / unit_count)
GET  /knowledge/status      同上(别名)
GET  /google/assertions     Google 轻量断言列表(?type=&limit=&offset=；非 KU)
GET  /google/assertions/<id> 单条 Google 轻量断言
GET  /categories            所有 category_v2 分布(?source=可选过滤)
GET  /memory                长期记忆概览(?type=可选过滤)
GET  /memory/<subject>      单条记忆详情 + 关系(?neighbors=N 可选)
POST /search/semantic       语义检索(knowledge-first + raw fallback)
POST /search/query          精确查询(结构化条件过滤 sqlite)
GET  /event/<event_id>      单条事件全字段
GET  /profile               返回 AI 长期上下文文档内容(RAG 注入用)
GET  /health                健康检查(含 knowledge.active_collection)
GET  /ui/overview           Personal Decision Cockpit 总览投影(五权威只读聚合)
GET  /ui/system/status      Cockpit 系统状态(端口探活 / 知识索引 / 权威 DB 可读性)
GET  /ui/personal-state     Cockpit 个人状态投影(八域断言 / 生命周期 / 近期变化)
GET  /ui/external/delta     Cockpit 外部数据增量投影(source / fact / delta 分类)
GET  /ui/decision-queue     Cockpit 决策队列投影(六 stage 看板分组)
GET  /ui/decision/workspace Cockpit 决策工作区投影(?recommendation_id=<id>,四节聚合)
GET  /ui/actions/recent     Cockpit 近期行动投影(最近推荐的全链六阶段时间线)
GET  /ui/proactive/summary  Cockpit 主动情报摘要(inbox 分组 + 噪声指标)
GET  /ui/calibration/overview Cockpit 校准总览(逐 protocol verdict 摘要)
GET  /ui/evidence/resolve  Cockpit 只读证据解析(?subject_type=personal_state|external_fact|decision
                            &stable_id=&snapshot_id=&checksum=,personal_state 另需
                            assertion_kind/subject/domain/scope/predicate)
GET  /ui/topics             Wiki P0 topic.list 只读目录
GET  /ui/topic               Wiki P0 topic.get 只读主题投影
GET  /ui/topic/backlinks     Wiki P0 topic.backlinks 显式关系
GET  /ui/topic/resolve       Wiki scoped read fallback provenance
GET  /app[/<path>]          Cockpit 前端静态托管(apps/personal_decision_cockpit/dist,SPA fallback)

GET  接口也可改用 POST(方便前端统一处理),参数走 query string。
POST 接口参数走 JSON body。

=== 启动 ================================================================

    python api_server.py [--host 127.0.0.1] [--port 8000]

默认只监听 127.0.0.1(本地安全,不对外暴露)。

=== 示例 ================================================================

    # 统计概览
    curl http://127.0.0.1:8000/stats

    # 知识索引状态
    curl http://127.0.0.1:8000/knowledge

    # 语义检索(POST + JSON；knowledge-first + raw fallback)
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
- 出站 JSON 统一经 privacy_guard 封存明文密钥/凭据（MCP/Apps 同源）
- 默认 127.0.0.1 only,需要对外自己加反代 + 鉴权
"""

from __future__ import annotations

import argparse
import json
import os
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

import personal_knowledge.retrieval.unified_search as backend  # noqa: E402
from personal_knowledge.core.privacy_guard import guard_jsonable, guard_text  # noqa: E402
from personal_knowledge.core.project_paths import UNIFIED_DB  # noqa: E402
from personal_knowledge.intelligence.service import IntelligenceService  # noqa: E402
from personal_knowledge.intelligence.decision.service import DecisionFeedbackService  # noqa: E402
from personal_knowledge.intelligence.proactive.service import ProactiveIntelligenceService  # noqa: E402
from personal_knowledge.services.decision_intelligence_reads import (  # noqa: E402
    DecisionIntelligenceReadService,
)
from personal_knowledge.services.orchestration_service import (  # noqa: E402
    GuardedOrchestrationInterface,
)
from personal_knowledge.services.pi_domain_gateway import (  # noqa: E402
    PI_DOMAIN_CAPABILITY_HEADER,
    PiDomainGateway,
)
from personal_knowledge.services.agent_contract import compact_envelope  # noqa: E402
from personal_knowledge.services.ui_projection import (  # noqa: E402
    CockpitProjectionService,
)
from personal_knowledge.services.topic_projection import (  # noqa: E402
    TopicProjectionService,
)
from personal_knowledge.wiki.materialization import WikiMaterializer  # noqa: E402

# AI 长期上下文文档路径(给 /profile 用)
ROOT = _THIS_DIR.parents[1]
PROFILE_MD = ROOT / "integration" / "analysis" / "ai_context" / "person_profile.md"
WIKI_DERIVED_STORE = ROOT / "var" / "db" / "personal_wiki_projection.sqlite"

# Personal Decision Cockpit 前端构建产物(SPA, npm run build 生成)
COCKPIT_DIST = ROOT / "apps" / "personal_decision_cockpit" / "dist"

_COCKPIT_ASSET_TYPES = {
    ".html": "text/html",
    ".js": "text/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
    ".map": "application/json",
}


def _resolve_cockpit_asset(url_path: str) -> Path | None:
    """把 /app/... URL 映射到 COCKPIT_DIST 内的文件;越界 / 缺失返回 None。

    /app、/app/ 与无扩展名子路径一律回退 index.html(SPA fallback);
    有扩展名的路径做 resolve() 后校验仍位于 COCKPIT_DIST 内(防 ../ 穿越)。
    """
    if not (url_path == "/app" or url_path.startswith("/app/")):
        return None
    if not COCKPIT_DIST.is_dir():
        return None
    rel = unquote(url_path[len("/app"):]).lstrip("/")
    segments = [seg for seg in rel.split("/") if seg and seg != "."]
    index = COCKPIT_DIST / "index.html"
    if not segments:
        return index if index.is_file() else None
    if any(seg == ".." for seg in segments):
        return None
    candidate = COCKPIT_DIST.joinpath(*segments)
    if not candidate.suffix:
        return index if index.is_file() else None
    try:
        resolved = candidate.resolve()
        root = COCKPIT_DIST.resolve()
    except OSError:
        return None
    if resolved != root and root not in resolved.parents:
        return None
    return resolved if resolved.is_file() else None


# === 同源 transport 与 CORS 策略（Phase 36：D-36-03） ======================
#
# 生产 Cockpit 由本进程以 /app 同源托管，浏览器同源 fetch 天然不受 CORS 限制，
# 不需要任何 Access-Control-Allow-Origin 响应头。唯一需要显式 CORS 的场景是
# 本地开发：Vite dev server（默认 127.0.0.1:5173）与本 REST 进程（默认 8000）
# 端口不同，浏览器发起的是跨源请求。允许的开发 Origin 只能来自启动时的显式
# 配置（环境变量），不接受任何请求内容扩大该列表。
_DEFAULT_DEV_ORIGINS = ("http://127.0.0.1:5173", "http://localhost:5173")


def _dev_allowed_origins() -> frozenset[str]:
    """显式开发 Origin allowlist：内置 Vite 默认端口 + PK_COCKPIT_DEV_ORIGINS(逗号分隔)。"""
    raw = os.environ.get("PK_COCKPIT_DEV_ORIGINS", "")
    extra = tuple(item.strip() for item in raw.split(",") if item.strip())
    return frozenset(_DEFAULT_DEV_ORIGINS + extra)


def _same_origin(origin: str, host_header: str | None) -> bool:
    """判断请求 Origin 是否与本进程自身(生产 /app 同源)一致。"""
    if not host_header:
        return False
    return origin in (f"http://{host_header}", f"https://{host_header}")


def _origin_policy(origin: str | None, host_header: str | None) -> dict:
    """集中的 Origin 判定,是 CORS 响应与跨 Origin mutation 拒绝的唯一决策点。

    - 无 Origin(既有本地非浏览器调用,如 curl/CLI/MCP): 放行,不下发 CORS header。
    - Origin 与本进程 Host 一致(生产同源 Cockpit): 放行,不下发 CORS header
      (浏览器同源请求本就不受 CORS 约束)。
    - Origin 命中显式开发 allowlist: 放行,下发该 Origin 专属 CORS header。
    - 其余任意 Origin: 拒绝,不下发 CORS header,不回显该 Origin。
    """
    if not origin:
        return {"allowed": True, "reason": "no_origin", "cors_origin": None}
    if _same_origin(origin, host_header):
        return {"allowed": True, "reason": "same_origin", "cors_origin": None}
    if origin in _dev_allowed_origins():
        return {"allowed": True, "reason": "dev_origin", "cors_origin": origin}
    return {"allowed": False, "reason": "origin_not_allowed", "cors_origin": None}


# 需要 Origin gate 前置拦截的受控 session 写路由(mutation 抵达 orchestration_rest_contract 之前)
SESSION_WRITE_ROUTES: dict[str, str] = {
    "/agent/session/prepare": "session.prepare",
    "/agent/session/confirm": "session.confirm",
    "/agent/session/preview": "session.preview",
    "/agent/session/execute": "session.execute",
    "/agent/session/generate": "session.execute",
    "/agent/session/publish": "session.execute",
    "/agent/session/decide": "session.execute",
    "/agent/session/preregister": "session.execute",
    "/agent/session/action-start": "session.execute",
    "/agent/session/action-complete": "session.execute",
    "/agent/session/observe": "session.execute",
    "/agent/session/calibrate": "session.execute",
}


# === 安全公开错误目录（Phase 36：D-36-06） ==================================
#
# /app 静态资源缺失/越界、Origin 拒绝与受控 mutation 的 transport 错误共用
# 固定 code/message；不得拼接请求路径、异常文本、密钥、provider 响应体、
# confirmation token 或 HMAC。详细诊断只进本地 stderr(traceback.print_exc)。
_SAFE_ERRORS: dict[str, str] = {
    "cockpit_asset_not_found": "请求的前端资源不存在",
    "cockpit_not_built": "前端未构建,请先执行 npm run build",
    "origin_not_allowed": "跨源请求已拒绝",
    "internal_error": "服务器内部错误",
    # 999.5 评审台页面装配失败(私有评审素材路径/异常详情只留本地 stderr)
    "review_console_error": "评审台页面装配失败",
}


def _safe_error(code: str, http_status: int) -> tuple[bytes, int]:
    """构造 allowlisted 安全错误 envelope;code 只能是模块内固定字面量,不接受外部输入。"""
    message = _SAFE_ERRORS.get(code, "请求处理失败")
    payload = {"ok": False, "error": {"code": code, "message": message}}
    return (
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        http_status,
    )


def _seal_payload(data):
    """出站数据隐私封存；保持结构不变。"""
    sealed, _meta = guard_jsonable(data)
    return sealed


def _ok(data) -> bytes:
    return json.dumps(
        {"ok": True, "data": _seal_payload(data)}, ensure_ascii=False, default=str
    ).encode("utf-8")


def _contract(data) -> bytes:
    return json.dumps(_seal_payload(data), ensure_ascii=False, default=str).encode("utf-8")


def _err(msg: str, code: int = 400) -> tuple[bytes, int]:
    safe_msg = guard_text(msg).text
    return (
        json.dumps({"ok": False, "error": safe_msg}, ensure_ascii=False).encode("utf-8"),
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


def intelligence_rest_contract(
    operation: str,
    params: dict,
    *,
    db_path: Path | None = None,
    resolver=None,
) -> dict:
    """Thin REST adapter over the shared intelligence service."""
    values = {key: value for key, value in params.items() if value not in {None, ""}}
    if "limit" in values:
        try:
            values["limit"] = int(values["limit"])
        except (TypeError, ValueError):
            return IntelligenceService._error(operation, "invalid_limit", str(values["limit"]))
    return IntelligenceService(db_path or UNIFIED_DB, resolver=resolver).invoke(
        operation, **values
    )


def decision_rest_contract(
    operation: str,
    params: dict,
    *,
    db_path: Path | None = None,
) -> dict:
    """Thin read-only REST adapter over the shared decision service."""
    values = {key: value for key, value in params.items() if value not in {None, ""}}
    if "limit" in values:
        try:
            values["limit"] = int(values["limit"])
        except (TypeError, ValueError):
            return DecisionFeedbackService._error(
                operation, "invalid_limit", str(values["limit"])
            )
    return DecisionFeedbackService(db_path or UNIFIED_DB).invoke(operation, **values)


def proactive_rest_contract(operation: str, params: dict, *, db_path: Path | None = None) -> dict:
    """Thin read-only REST adapter over proactive intelligence."""
    values = {key: value for key, value in params.items() if value not in {None, ""}}
    if "limit" in values:
        try:
            values["limit"] = int(values["limit"])
        except (TypeError, ValueError):
            return ProactiveIntelligenceService._error(operation, "invalid_limit", str(values["limit"]))
    return ProactiveIntelligenceService(db_path or UNIFIED_DB).invoke(operation, **values)


def agent_read_rest_contract(
    operation: str, params: dict, *, service: DecisionIntelligenceReadService | None = None,
) -> dict:
    """Thin REST adapter for Phase 28-31 read authorities."""
    values = {key: value for key, value in params.items() if value not in {None, ""}}
    return compact_envelope((service or DecisionIntelligenceReadService()).invoke(operation, **values))


def orchestration_rest_contract(
    operation: str, params: dict, *, service: GuardedOrchestrationInterface | None = None,
) -> dict:
    """Thin REST adapter over the shared guarded orchestration contract."""
    try:
        target = service or GuardedOrchestrationInterface()
    except Exception as exc:
        code = str(getattr(exc, "code", "") or str(exc) or "service_unavailable").split(":", 1)[0]
        return compact_envelope(GuardedOrchestrationInterface._envelope(operation, ok=False, code=code))
    return compact_envelope(target.invoke(operation, **params))


def ui_rest_contract(
    operation: str, params: dict, *, service: CockpitProjectionService | None = None,
) -> dict:
    """Thin read-only REST adapter over the cockpit UI projection."""
    return (service or CockpitProjectionService()).invoke(operation, **params)


def topic_rest_contract(
    operation: str, params: dict, *, service: TopicProjectionService | None = None,
) -> dict:
    """Thin GET-only adapter over the Wiki topic projection service."""
    values = {key: value for key, value in params.items() if value not in {None, ""}}
    if "limit" in values:
        try:
            values["limit"] = int(values["limit"])
        except (TypeError, ValueError):
            return TopicProjectionService()._envelope_error(operation, "invalid_topic_key", limitations=["limit 无效"])
    target = service or TopicProjectionService(materializer=WikiMaterializer(WIKI_DERIVED_STORE))
    return target.invoke(operation, **values)


class Handler(BaseHTTPRequestHandler):
    # 静音默认日志(太吵),自己打一行精简的
    def log_message(self, fmt, *args):
        sys.stderr.write(f"[api] {self.command} {self.path} -> {args[1]}\n")

    def _origin_policy_for_request(self) -> dict:
        return _origin_policy(self.headers.get("Origin"), self.headers.get("Host"))

    def _send(self, body: bytes, code: int = 200, ctype: str = "application/json"):
        self.send_response(code)
        # 文本类响应声明 charset;二进制资源(图片/字体等)不追加
        if ctype.startswith("text/") or ctype in {
            "application/json", "application/javascript", "image/svg+xml",
        }:
            ctype = f"{ctype}; charset=utf-8"
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # 生产同源不需要 CORS header;仅显式开发 Origin 获得专属(非 wildcard)响应头
        decision = self._origin_policy_for_request()
        if decision["cors_origin"]:
            self.send_header("Access-Control-Allow-Origin", decision["cors_origin"])
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        """读 JSON body,空/非法返回 {}。处理编码兼容性。"""
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        # 优先 UTF-8,回退系统 locale 编码(兼容 Windows GBK 终端)
        for enc in ("utf-8", "gbk", "gb2312", "gb18030"):
            try:
                text = raw.decode(enc)
                data = json.loads(text)
                return data if isinstance(data, dict) else {}
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
        return {}

    def do_OPTIONS(self):  # CORS 预检
        decision = self._origin_policy_for_request()
        if not decision["allowed"]:
            # 未知 Origin 的预检 → 安全拒绝;不下发 CORS header,不回显 Origin
            body, code = _safe_error("origin_not_allowed", 403)
            self._send(body, code)
            return
        self._send(b"", 204)

    # --- GET 路由 ----------------------------------------------------------
    def do_GET(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}

        try:
            # Cockpit 前端静态托管(用未 rstrip 的 url.path 区分 /app 与 /app/)
            if url.path == "/app" or url.path.startswith("/app/"):
                if url.path == "/app":
                    self.send_response(301)
                    self.send_header("Location", "/app/")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                asset = _resolve_cockpit_asset(url.path)
                if asset is not None:
                    ctype = _COCKPIT_ASSET_TYPES.get(
                        asset.suffix.lower(), "application/octet-stream"
                    )
                    self._send(asset.read_bytes(), 200, ctype)
                    return
                if not COCKPIT_DIST.is_dir():
                    body, code = _safe_error("cockpit_not_built", 404)
                    self._send(body, code)
                    return
                # 资源不存在或路径遍历越界(_resolve_cockpit_asset 已拒绝)统一走安全错误,
                # 不回显原始请求路径
                body, code = _safe_error("cockpit_asset_not_found", 404)
                self._send(body, code)
                return

            if path == "/health":
                ku = backend.get_knowledge_status(probe_chroma=False)
                self._send(
                    _ok(
                        {
                            "status": "ok",
                            "knowledge": {
                                "available": ku.get("available"),
                                "active_collection": ku.get("active_collection"),
                                "unit_count": ku.get("unit_count") or ku.get("db_unit_count"),
                            },
                        }
                    )
                )
                return

            if path == "/stats":
                self._send(_ok(backend.stats()))
                return

            # 999.5 单人评审台(gold 三键核对 + judge 校准打分),localhost only。
            # 页面数据服务端即时装配自 private_evals,不进任何 authority 面。
            if path == "/ui/review":
                from personal_knowledge.services.eval_review import build_review_page
                try:
                    page = build_review_page().encode("utf-8")
                except Exception:
                    # 页面装配触及私有评审素材;异常详情只留本地 stderr,
                    # 公开响应固定安全 code/message,不回显路径/traceback
                    traceback.print_exc()
                    b, c = _safe_error("review_console_error", 500)
                    self._send(b, c)
                    return
                # 页面含私有评审数据:禁止任何浏览器/中间缓存(no-store)。
                # _send 不支持附加 header,这里手动下发,避免改动共享方法。
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(page)
                return

            intelligence_routes = {
                "/intelligence/state/current": "state.current",
                "/intelligence/state/history": "state.history",
                "/intelligence/changes/recent": "changes.recent",
                "/intelligence/state/explain": "state.explain",
            }
            if path in intelligence_routes:
                params = {
                    "snapshot_id": qs.get("snapshot_id"),
                    "run_id": qs.get("run_id"),
                    "as_of": qs.get("as_of"),
                }
                if path.endswith("/current") or path.endswith("/history") or path.endswith("/recent"):
                    params["limit"] = qs.get("limit", "50")
                if path.endswith("/recent"):
                    params["window_start"] = qs.get("window_start")
                if path.endswith("/explain"):
                    params.update({
                        "assertion_kind": qs.get("assertion_kind"),
                        "subject": qs.get("subject"),
                        "domain": qs.get("domain"),
                        "scope": qs.get("scope"),
                        "predicate": qs.get("predicate"),
                    })
                data = intelligence_rest_contract(intelligence_routes[path], params)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            decision_routes = {
                "/decision/recommendations": "recommendations.list",
                "/decision/recommendation": "recommendations.get",
                "/decision/recommendation/history": "recommendations.history",
                "/decision/recommendation/outcomes": "recommendations.outcomes",
                "/decision/recommendation/effectiveness": "recommendations.effectiveness",
            }
            if path in decision_routes:
                params = {
                    "recommendation_id": qs.get("recommendation_id"),
                    "domain": qs.get("domain"),
                    "limit": qs.get("limit", "50"),
                }
                if path == "/decision/recommendation":
                    params.pop("limit")
                    params.pop("domain")
                elif path != "/decision/recommendations":
                    params.pop("domain")
                data = decision_rest_contract(decision_routes[path], params)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            proactive_routes = {
                "/proactive/inbox": "inbox.list",
                "/proactive/digest": "digest.get",
                "/proactive/candidate": "candidates.get",
                "/proactive/candidate/explain": "candidates.explain",
                "/proactive/controls/status": "controls.status",
                "/proactive/metrics": "metrics.get",
            }
            if path in proactive_routes:
                params = {"candidate_id": qs.get("candidate_id"), "domain": qs.get("domain"), "limit": qs.get("limit", "50"), "as_of": qs.get("as_of")}
                if path in {"/proactive/candidate", "/proactive/candidate/explain"}:
                    params = {"candidate_id": qs.get("candidate_id")}
                elif path == "/proactive/controls/status":
                    params = {"candidate_id": qs.get("candidate_id"), "as_of": qs.get("as_of")}
                elif path == "/proactive/metrics":
                    params = {}
                data = proactive_rest_contract(proactive_routes[path], params)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            agent_routes = {
                "/agent/external": "external.list",
                "/agent/external/item": "external.get",
                "/agent/external/explain": "external.explain",
                "/agent/analysis": "analysis.list",
                "/agent/analysis/item": "analysis.get",
                "/agent/analysis/explain": "analysis.explain",
                "/agent/pilot": "pilot.list",
                "/agent/pilot/item": "pilot.get",
                "/agent/pilot/explain": "pilot.explain",
                "/agent/calibration": "calibration.list",
                "/agent/calibration/item": "calibration.get",
                "/agent/calibration/explain": "calibration.explain",
            }
            if path in agent_routes:
                operation = agent_routes[path]
                params = {"limit": qs.get("limit", "50")}
                if operation.startswith("external.") and operation != "external.list":
                    params = {"resource_type": qs.get("resource_type"), "resource_id": qs.get("resource_id")}
                elif operation.startswith("analysis.") and operation != "analysis.list":
                    params = {"run_id": qs.get("run_id")}
                elif operation.startswith("pilot.") and operation != "pilot.list":
                    params = {"case_id": qs.get("case_id"), "as_of": qs.get("as_of")}
                    if operation == "pilot.get":
                        params.pop("as_of")
                elif operation.startswith("calibration.") and operation != "calibration.list":
                    params = {"protocol_id": qs.get("protocol_id")}
                data = agent_read_rest_contract(operation, params)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            session_read_routes = {
                "/agent/session/resume": "session.resume",
                "/agent/session/explain": "session.explain",
            }
            if path in session_read_routes:
                data = orchestration_rest_contract(
                    session_read_routes[path], {"session_id": qs.get("session_id"), "now": qs.get("now")},
                )
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            ui_routes = {
                "/ui/overview": "overview.get",
                "/ui/system/status": "system.status.get",
                "/ui/personal-state": "personal_state.get",
                "/ui/external/delta": "external_delta.get",
                "/ui/decision-queue": "decision_queue.get",
                "/ui/decision/workspace": "decision_workspace.get",
                "/ui/actions/recent": "actions_recent.get",
                "/ui/proactive/summary": "proactive_summary.get",
                "/ui/calibration/overview": "calibration_overview.get",
                "/ui/evidence/resolve": "evidence_resolve.get",
            }
            if path in ui_routes:
                params = {}
                if path == "/ui/decision/workspace":
                    params = {"recommendation_id": qs.get("recommendation_id")}
                elif path == "/ui/actions/recent":
                    # 游标分页透传:cursor 不透明,limit 可选;GET-only,无副作用
                    params = {"cursor": qs.get("cursor"), "limit": qs.get("limit")}
                elif path == "/ui/evidence/resolve":
                    # 只读证据解析(Phase 37:EVID-01);GET-only,无对应 POST 路由,
                    # 参数原样透传给 evidence_resolve.get 做结构校验,不在此层猜测/补全
                    params = {
                        "subject_type": qs.get("subject_type"),
                        "stable_id": qs.get("stable_id"),
                        "snapshot_id": qs.get("snapshot_id"),
                        "checksum": qs.get("checksum"),
                        "assertion_kind": qs.get("assertion_kind"),
                        "subject": qs.get("subject"),
                        "domain": qs.get("domain"),
                        "scope": qs.get("scope"),
                        "predicate": qs.get("predicate"),
                    }
                data = ui_rest_contract(ui_routes[path], params)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            topic_routes = {
                "/ui/topics": "topic.list",
                "/ui/topic": "topic.get",
                "/ui/topic/backlinks": "topic.backlinks",
                "/ui/topic/resolve": "topic.resolve",
            }
            if path in topic_routes:
                operation = topic_routes[path]
                params = {
                    "topic_type": qs.get("topic_type"),
                    "topic_id": qs.get("topic_id"),
                    "topic_key": qs.get("topic_key"),
                    "query": qs.get("query"),
                    "cursor": qs.get("cursor"),
                    "limit": qs.get("limit", "50"),
                }
                if operation != "topic.list":
                    params.pop("cursor")
                    if operation != "topic.backlinks":
                        params.pop("limit")
                if operation == "topic.resolve":
                    params = {"topic_key": qs.get("topic_key"), "query": qs.get("query")}
                data = topic_rest_contract(operation, params)
                error = data.get("error") if isinstance(data, dict) else None
                status = 200 if data.get("ok") else 404 if error == "topic_not_found" else 400
                self._send(_contract(data), status)
                return

            if path in ("/knowledge", "/knowledge/status"):
                probe = not _truthy(qs.get("no_chroma"))
                self._send(_ok(backend.get_knowledge_status(probe_chroma=probe)))
                return

            if path == "/google/assertions":
                data = backend.list_google_light_assertions(
                    assertion_type=qs.get("type") or qs.get("assertion_type"),
                    limit=int(qs.get("limit", 50)),
                    offset=int(qs.get("offset", 0)),
                )
                self._send(_ok(data))
                return

            if path.startswith("/google/assertions/"):
                # IDs contain '|' (e.g. gla|interest_topic|…); must unquote %7C
                aid = unquote(path[len("/google/assertions/") :].strip("/"))
                if not aid:
                    body, code = _err("assertion_id required", 400)
                    self._send(body, code)
                    return
                item = backend.get_google_light_assertion(aid)
                if item is None:
                    body, code = _err(f"assertion not found: {aid}", 404)
                    self._send(body, code)
                    return
                self._send(_ok(item))
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
                # default true; accept false/0/no/off
                include_evidence = True
                if "include_evidence" in qs:
                    include_evidence = _truthy(qs.get("include_evidence"))
                data = backend.get_memory_by_id_contract(
                    memory_id, include_evidence=include_evidence
                )
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
        except Exception:
            # 详细异常留本地 stderr;公开响应只回安全 code/message,不拼接 str(exc)
            traceback.print_exc()
            body, code = _safe_error("internal_error", 500)
            self._send(body, code)

    # --- POST 路由 ---------------------------------------------------------
    def do_POST(self):
        url = urlparse(self.path)
        path = url.path.rstrip("/") or "/"

        try:
            if path in {"/ui/topics", "/ui/topic", "/ui/topic/backlinks", "/ui/topic/resolve"}:
                self._send(
                    json.dumps({"ok": False, "error": {"code": "method_not_allowed"}}, ensure_ascii=False).encode("utf-8"),
                    405,
                )
                return
            if path in SESSION_WRITE_ROUTES:
                # Origin gate 必须先于 body 解析与 orchestration 委派(D-36-03):
                # 不匹配 Origin 时零解析、零委派、零写入。
                decision = self._origin_policy_for_request()
                if not decision["allowed"]:
                    body, code = _safe_error("origin_not_allowed", 403)
                    self._send(body, code)
                    return

            # 999.5 评审 labels 与 session 写路由同规则(D-36-03):
            # Origin gate 先于 body 解析,不匹配 Origin 时零解析、零写入。
            if path == "/ui/review/labels":
                decision = self._origin_policy_for_request()
                if not decision["allowed"]:
                    body, code = _safe_error("origin_not_allowed", 403)
                    self._send(body, code)
                    return

            body = self._read_body()

            if path == "/internal/pi-domain/dispatch":
                # Internal means loopback process ownership plus an injected capability;
                # operation IDs are validated by the gateway and never become imports.
                operation = body.get("operation")
                params = body.get("params") if isinstance(body.get("params"), dict) else {}
                result = PiDomainGateway().invoke(
                    operation, params,
                    capability=self.headers.get(PI_DOMAIN_CAPABILITY_HEADER),
                )
                self._send(_contract(result), 200 if result.get("ok") else 400)
                return

            if path in SESSION_WRITE_ROUTES:
                operation = SESSION_WRITE_ROUTES[path]
                expected = path.rsplit("/", 1)[-1].replace("-", "_")
                if operation == "session.execute" and path != "/agent/session/execute":
                    preview = body.get("preview") or {}
                    if preview.get("operation") != expected:
                        data = compact_envelope(GuardedOrchestrationInterface._envelope(
                            operation, ok=False, code="route_operation_mismatch",
                        ))
                    else:
                        data = orchestration_rest_contract(operation, body)
                else:
                    data = orchestration_rest_contract(operation, body)
                self._send(_contract(data), 200 if data.get("ok") else 400)
                return

            # 999.5 评审 labels 保存:只写 private_evals 下带时间戳的新文件,
            # 不触碰 SSOT/eval registry;非法判定值直接 400。
            if path == "/ui/review/labels":
                from personal_knowledge.services.eval_review import save_review_labels
                try:
                    self._send(_ok(save_review_labels(body)))
                except ValueError as exc:
                    b, c = _err(str(exc), 400)
                    self._send(b, c)
                return

            if path == "/search/semantic":
                query = body.get("query", "").strip()
                if not query:
                    b, c = _err("缺少 query 参数")
                    self._send(b, c)
                    return
                # knowledge-first + raw fallback；可选 collection_override 仅用于 canary/评测
                result = backend.search_knowledge_units(
                    query=query,
                    top_k=int(body.get("top_k", 5)),
                    source=body.get("source"),
                    include_evidence=bool(body.get("include_evidence", False)),
                    collection_override=(body.get("collection") or body.get("collection_override") or None),
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

        except Exception:
            # 详细异常留本地 stderr;公开响应只回安全 code/message,不拼接 str(exc)
            traceback.print_exc()
            body_b, code = _safe_error("internal_error", 500)
            self._send(body_b, code)

    def _wiki_method_not_allowed(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path in {"/ui/topics", "/ui/topic", "/ui/topic/backlinks", "/ui/topic/resolve"}:
            payload = {"ok": False, "error": {"code": "method_not_allowed"}}
            self._send(json.dumps(payload, ensure_ascii=False).encode("utf-8"), 405)
            return True
        return False

    def do_PUT(self):
        if not self._wiki_method_not_allowed():
            self._send(*_safe_error("internal_error", 405))

    def do_PATCH(self):
        if not self._wiki_method_not_allowed():
            self._send(*_safe_error("internal_error", 405))

    def do_DELETE(self):
        if not self._wiki_method_not_allowed():
            self._send(*_safe_error("internal_error", 405))

def main() -> None:
    p = argparse.ArgumentParser(description="个人数据系统 REST API")
    p.add_argument("--host", default="127.0.0.1", help="监听地址(默认 127.0.0.1)")
    p.add_argument("--port", type=int, default=8000, help="监听端口(默认 8000)")
    args = p.parse_args()

    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"[api] 个人数据 REST API 启动:")
    print(f"[api]   http://{args.host}:{args.port}")
    print(f"[api] 接口:")
    print(f"[api]   GET  /health               健康检查(+knowledge 摘要)")
    print(f"[api]   GET  /stats                数据库+向量库+知识索引统计")
    print(f"[api]   GET  /knowledge            知识索引状态(?no_chroma=1)")
    print(f"[api]   GET  /categories           分类分布(?source=可选)")
    print(f"[api]   GET  /memory               长期记忆概览(?type=可选)")
    print(f"[api]   GET  /memory/<subject>     单条记忆详情(+?neighbors=N)")
    print(f"[api]   POST /search/semantic      语义检索(knowledge-first)")
    print(f"[api]   POST /search/query         精确查询(sqlite)")
    print(f"[api]   GET  /event/<id>           单条事件详情")
    print(f"[api]   GET  /profile              AI 长期上下文文档(RAG 注入)")
    print(f"[api]   GET  /intelligence/*       个人状态/变化只读接口")
    print(f"[api]   GET  /data/*               分页/导出/聚合/时间线/质量")
    print(f"[api] Ctrl+C 退出")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[api] 已停止")
        server.shutdown()


if __name__ == "__main__":
    main()
