"""Personal Decision Cockpit 只读 UI 投影层(overview / system status / personal state /
external delta / decision queue / decision workspace / actions recent /
proactive summary / calibration overview)。

把五个只读权威(personal / decision / proactive / external / knowledge)聚合成
前端直接可渲染的投影信封。REST 适配器见 services/api_server.py 的
``ui_rest_contract``,路由 ``/ui/overview``、``/ui/system/status``、
``/ui/personal-state``、``/ui/external/delta``、``/ui/decision-queue``、
``/ui/decision/workspace?recommendation_id=<id>``、``/ui/actions/recent``、
``/ui/proactive/summary``、``/ui/calibration/overview`` 与
``/ui/evidence/resolve?subject_type=&stable_id=&snapshot_id=&checksum=``
(personal_state 另需 ``assertion_kind/subject/domain/scope/predicate``)。

统一信封(schema_version = decision_cockpit_projection_v1):

    {schema_version, operation, ok, generated_at, snapshot_bindings,
     freshness, authorities, partial, limitations, data}

单权威失败不拖垮整体:该节 data 置 None、authorities[x]="error"、
limitations 追加中文说明,其余节照常;partial=True 标记降级,绝不伪装成功。

actions_recent.get 的 timeline event_type → stage 映射
(真实词表读自 intelligence/decision/state_machine.py):
- recommendation_published(genesis,sequence=1)→ recommendation
- confirmation(accept/reject/defer/revoke_before_action)→ decision
- action → 按 typed record 的 action_state 细分:started → action_start、
  completed → action_complete;planned/abandoned/not_taken 不占独立 stage
- outcome → outcome
- assessment → effectiveness
history 只暴露链上六字段(无 action_state),action 细分由 decision_actions
单条只读 SQL 聚合映射(同 _outcome_counts 先例);每 stage 引用链上首个匹配事件。

硬边界:
- 只读:所有 SQLite 访问一律 mode=ro + query_only,不写任何库
- 不调 provider、不做 promote、不创建 Recommendation、不改任何 lifecycle
- 保留所有 authority ID(recommendation_id / candidate_id / protocol_id / snapshot_id)
- metadata-only:personal 节只暴露 key/status/confidence/provenance_class,不含明文值
"""
from __future__ import annotations

import socket
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from personal_knowledge.core.project_paths import EXTERNAL_CONTEXT_DB, UNIFIED_DB, VAR_DB
from personal_knowledge.intelligence.decision.service import DecisionFeedbackService
from personal_knowledge.intelligence.proactive.schema import CANONICAL_DOMAINS
from personal_knowledge.intelligence.proactive.ranking import DEFAULT_RANKING_POLICY
from personal_knowledge.intelligence.proactive.service import ProactiveIntelligenceService
from personal_knowledge.intelligence.schema import (
    ASSERTION_KINDS,
    ASSERTION_LIFECYCLES,
    PROVENANCE_CLASSES,
)
from personal_knowledge.intelligence.service import IntelligenceService
from personal_knowledge.retrieval.unified_search import get_knowledge_status
from personal_knowledge.services.decision_intelligence_reads import DecisionIntelligenceReadService


INTERFACE_SCHEMA_VERSION = "decision_cockpit_projection_v1"

AUTHORITY_DB_PATHS = {
    "external_context": EXTERNAL_CONTEXT_DB,
    "decision_analysis": VAR_DB / "decision_analysis.sqlite",
    "project_pilot": VAR_DB / "project_pilot.sqlite",
    "recommendation_calibration": VAR_DB / "recommendation_calibration.sqlite",
}

_PORT_PROBES = {"mcp": 8789, "tunnel": 8081}
_REST_PORT = 8000
_TOP_ITEMS = 10

# personal_state.get / external_delta.get 的固定词表与上限
_ASSERTION_KINDS = tuple(sorted(ASSERTION_KINDS))
_PROVENANCE_CLASSES = tuple(sorted(PROVENANCE_CLASSES))
_ASSERTION_LIFECYCLES = tuple(sorted(ASSERTION_LIFECYCLES))
# IntelligenceService 的 limit 硬上限为 MAX_HISTORY_LIMIT=100
_STATE_LIMIT = 100
_CHANGES_LIMIT = 20
_DOMAIN_ASSERTIONS_MAX = 20
_EXTERNAL_FACTS_LIMIT = 100
_DELTA_WINDOW_DAYS = 7

# decision_queue.get / decision_workspace.get 的固定词表与上限
_QUEUE_LIMIT = 100
_WORKSPACE_TYPED_LIMIT = 50
_STAGE_KEYS = (
    "needs_attention", "awaiting_confirmation", "in_progress",
    "awaiting_outcome", "completed", "closed",
)
# proposed 且 expires_at 距 now 不足该窗口(或已过 / 无法解析)→ needs_attention
_NEEDS_ATTENTION_WINDOW = timedelta(hours=72)
# confirmation_state 已发布真实词表(读自 intelligence/decision/state_machine.py);
# 词表外的值一律不进入 action_state 驱动的 in_progress/awaiting_outcome 等可执行分支
# (D-36-05:Projection 不得凭空提升未知/伪造的 confirmation_state)
_KNOWN_CONFIRMATION_STATES = frozenset({"proposed", "accepted", "rejected", "deferred", "revoked"})
# 队列卡片保留的关键字段(沿用 recommendations.list 真实字段名)
_QUEUE_CARD_KEYS = (
    "recommendation_id", "domain", "recommendation_kind", "horizon", "confidence",
    "confirmation_state", "action_state", "expires_at", "current_sequence", "snapshot_id",
)
# recommendations.history 真实暴露的链上字段(该接口不暴露时间戳 / status)
_HISTORY_EVENT_KEYS = (
    "event_id", "sequence", "event_type", "typed_record_id",
    "previous_event_checksum", "payload_checksum",
)

# actions_recent.get 的固定词表与上限
_ACTIONS_RECENT_LIST_LIMIT = 20
_ACTIONS_RECENT_MAX = 10
_TIMELINE_STAGES = (
    "recommendation", "decision", "action_start",
    "action_complete", "outcome", "effectiveness",
)
# event_type → stage(action 事件例外,按 typed record 的 action_state 细分)
_EVENT_TYPE_TO_STAGE = {
    "recommendation_published": "recommendation",
    "confirmation": "decision",
    "outcome": "outcome",
    "assessment": "effectiveness",
}
_ACTION_STATE_TO_STAGE = {"started": "action_start", "completed": "action_complete"}
# 时间线条目保留的推荐卡字段(沿用 recommendations.list 真实字段名)
_ACTION_CARD_KEYS = (
    "recommendation_id", "domain", "recommendation_kind",
    "confirmation_state", "action_state", "expires_at",
)

# proactive_summary.get 的固定上限与卡片字段(沿用 inbox.list 真实字段名)
_PROACTIVE_INBOX_LIMIT = 50
_PROACTIVE_CARD_KEYS = (
    "candidate_id", "domains", "candidate_class", "presentation_kind", "importance",
    "expires_at", "valid_from", "reason_codes",
    "current_control_eligible", "current_control_reason_codes",
)

# calibration_overview.get 的固定上限
_CALIBRATION_LIST_LIMIT = 100
_CALIBRATION_EXPLAIN_MAX = 10

# evidence_resolve.get 的固定 subject_type 词表、personal_state 引用所需 state key
# 字段与只读证据解析结果的固定 status 词表(Phase 37:EVID-01)。resolver 只接受这三种
# 类型化引用,一律先做 stable_id/snapshot_id/checksum(personal_state 另加完整 state
# key)结构校验,再仅调度到既有只读 explain/get 路径;不接受任意资源标识或路径。
_EVIDENCE_SUBJECT_TYPES = frozenset({"personal_state", "external_fact", "decision"})
_STATE_KEY_FIELDS = ("assertion_kind", "subject", "domain", "scope", "predicate")
_EVIDENCE_RESULT_STATUSES = frozenset({
    "ok", "mismatch", "expired", "abstain", "not_found", "authority_unavailable",
})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso(value: Any) -> datetime | None:
    """解析带时区的 ISO 时间;缺失 / 无法解析 / 无时区一律返回 None。"""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _empty_domain_bucket() -> dict[str, Any]:
    return {
        "total": 0,
        "by_kind": {kind: 0 for kind in _ASSERTION_KINDS},
        "by_provenance": {cls: 0 for cls in _PROVENANCE_CLASSES},
        "conflicts": 0,
        "assertions": [],
    }


def _empty_domains() -> dict[str, Any]:
    return {domain: _empty_domain_bucket() for domain in CANONICAL_DOMAINS}


def _zero_lifecycle_counts() -> dict[str, int]:
    return {status: 0 for status in _ASSERTION_LIFECYCLES}


def _port_up(port: int) -> bool:
    """TCP 探活:只报 up/down,不发任何 payload,异常即 down。"""
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def _classify_stage(item: Mapping[str, Any], now: datetime) -> str:
    """把一条 recommendation 卡归入六个看板 stage 之一(纯函数,便于单测)。

    真实状态词汇(读自 intelligence/decision/state_machine.py):
    - confirmation_state ∈ {proposed, accepted, rejected, deferred, revoked}
    - action_state ∈ {None, planned, started, completed, abandoned, not_taken}
      (terminal: completed / abandoned / not_taken;outcome 只允许挂在 terminal action 上)
    - has_outcome 由调用方注入(decision_outcomes 是否已有记录)

    映射规则(按优先级):
    1. confirmation_state ∈ {rejected, deferred, revoked} → closed
    2. has_outcome → completed(已有 outcome,反馈闭环完成)
    3. confirmation_state 不在已发布词表内(词表见上)→ 保守 needs_attention,
       不进入下列任何 action_state 驱动分支——action 只能在 accepted 之后产生,
       词表外 confirmation 与非空 action_state 的组合视为数据异常,不得被提升
       为 in_progress/awaiting_outcome 等可执行/进行中 stage(D-36-05 词表锁定)
    4. action_state == completed 且无 outcome → awaiting_outcome
    5. action_state ∈ {abandoned, not_taken} 且无 outcome → closed
    6. action_state ∈ {planned, started} → in_progress
    7. confirmation_state == accepted(action 尚未开始)→ in_progress
    8. proposed 且 expires_at 已过 / 72h 内到期 / 无法解析 → needs_attention
    9. proposed 其余 → awaiting_confirmation
    10. 无法识别的组合保守归 needs_attention
    """
    confirmation = str(item.get("confirmation_state") or "")
    action_raw = item.get("action_state")
    action = str(action_raw) if action_raw else None
    if confirmation in {"rejected", "deferred", "revoked"}:
        return "closed"
    if bool(item.get("has_outcome")):
        return "completed"
    if confirmation not in _KNOWN_CONFIRMATION_STATES:
        return "needs_attention"
    if action == "completed":
        return "awaiting_outcome"
    if action in {"abandoned", "not_taken"}:
        return "closed"
    if action in {"planned", "started"}:
        return "in_progress"
    if confirmation == "accepted":
        return "in_progress"
    if confirmation == "proposed":
        expires = _parse_iso(item.get("expires_at"))
        if expires is None or expires <= now + _NEEDS_ATTENTION_WINDOW:
            return "needs_attention"
        return "awaiting_confirmation"
    return "needs_attention"


def _empty_decision_queue() -> dict[str, Any]:
    return {
        "total_available": 0,
        "stage_counts": {key: 0 for key in _STAGE_KEYS},
        "stages": {key: [] for key in _STAGE_KEYS},
    }


def _empty_timeline() -> list[dict[str, Any]]:
    return [
        {"stage": stage, "present": False, "event_id": None, "sequence": None, "checksum": None}
        for stage in _TIMELINE_STAGES
    ]


def _build_timeline(
    history: list[dict[str, Any]], action_states: Mapping[str, str],
) -> list[dict[str, Any]]:
    """把一条 recommendation 的 history 折成六阶段时间线(纯函数,便于单测)。

    六阶段键恒在;每阶段引用链上首个匹配事件,无该阶段 → present=False 其余 None。
    映射词表见模块 docstring;action 事件经 action_states(action_id → action_state)
    细分,planned/abandoned/not_taken 不占 stage,词表外 event_type 一律忽略。
    """
    chosen: dict[str, Mapping[str, Any]] = {}
    for event in history:
        event_type = str(event.get("event_type") or "")
        if event_type == "action":
            state = action_states.get(str(event.get("typed_record_id") or ""))
            stage = _ACTION_STATE_TO_STAGE.get(state or "")
        else:
            stage = _EVENT_TYPE_TO_STAGE.get(event_type)
        if stage and stage not in chosen:
            chosen[stage] = event
    timeline = []
    for stage in _TIMELINE_STAGES:
        event = chosen.get(stage)
        timeline.append({
            "stage": stage,
            "present": event is not None,
            "event_id": event.get("event_id") if event else None,
            "sequence": event.get("sequence") if event else None,
            "checksum": event.get("payload_checksum") if event else None,
        })
    return timeline


# external_delta.get 每 fact 的 freshness 词表(Phase 37:D-37-02 canonical External DTO)。
# lifecycle 是 External 权威自身发布的记录状态(current/stale/superseded/conflict/invalid);
# freshness 是相对当前 active snapshot 参考时刻(activated_at)派生的独立到期判断,
# 二者不得合并成同一个客户端颜色字段。
_FRESHNESS_LEVELS = frozenset({"unknown", "valid", "expiring_soon", "expired"})


def _fact_freshness(
    valid_to: Any, reference: datetime | None, window: timedelta,
) -> dict[str, Any]:
    if reference is None:
        return {"level": "unknown", "reason": "active snapshot 缺少可解析的 activated_at"}
    valid_to_dt = _parse_iso(valid_to)
    if valid_to_dt is None:
        return {"level": "valid", "reason": None}
    if valid_to_dt <= reference:
        return {"level": "expired", "reason": "valid_to 早于 snapshot 参考时间(activated_at)"}
    if valid_to_dt <= reference + window:
        return {
            "level": "expiring_soon",
            "reason": f"valid_to 距 snapshot 参考时间不足 {_DELTA_WINDOW_DAYS} 天",
        }
    return {"level": "valid", "reason": None}


def _empty_actions_recent() -> dict[str, Any]:
    return {
        "total_available": 0, "shown": 0,
        "with_outcome": 0, "awaiting_outcome": 0, "items": [],
    }


def _empty_proactive_groups() -> dict[str, list[Any]]:
    return {"now": [], "deferrable": []}


def _calibration_summary(protocol_id: str, view: Mapping[str, Any]) -> dict[str, Any]:
    """从 calibration.explain 真实视图裁剪单 protocol 摘要(纯函数,便于单测)。

    真实结构(intelligence/calibration/service.py explain):{protocol, cohort, arms,
    measurements, verdicts, proposals, limitations, causal_claim, promotion_available,
    external_action_available};protocol 行含 protocol_status 列;verdict 行含
    verdict_status 列(PASS/FAIL/INCONCLUSIVE),payload.reason_codes 为判定原因词表
    (INCONCLUSIVE 时即 inconclusive 原因);sample_size 由 cohort 行数派生
    (视图无独立字段);summary_limitations 原样保留视图固定 limitations。
    """
    protocol_rows = list(view.get("protocol") or [])
    verdicts = list(view.get("verdicts") or [])
    verdict_row = verdicts[0] if verdicts else {}
    verdict_payload = verdict_row.get("payload") or {}
    return {
        "protocol_id": protocol_id,
        "status": protocol_rows[0].get("protocol_status") if protocol_rows else None,
        "verdict": verdict_row.get("verdict_status"),
        "causal_claim": view.get("causal_claim"),
        "inconclusive_reasons": list(verdict_payload.get("reason_codes") or []),
        "sample_size": len(list(view.get("cohort") or [])),
        "summary_limitations": list(view.get("limitations") or []),
    }


# === 安全公开 limitation/error 目录(Phase 36:D-36-06) =========================
#
# 单权威/单条读取失败时,公开 limitations 与内联 "error" 字段只能引用这里的固定
# code/message,绝不拼接 str(exc)、异常类型、路径、密钥、provider body 或
# confirmation/HMAC 材料;详细异常仅用于该异常自身触发的服务端行为(如重新抛出
# 给上层隔离),不得以任何形式序列化进返回给浏览器的 JSON。
_SAFE_FAILURE_CODES: dict[str, str] = {
    "authority_read_failed": "读取失败",
    "history_count_unavailable": "历史计数读取异常",
    "item_assembly_failed": "全链组装失败",
    "protocol_explain_failed": "explain 失败",
}


def _safe_failure_message(name: str, code: str) -> str:
    """构造 allowlisted 安全 limitation 文案;code 只能是模块内固定字面量,不接受
    str(exc) 或其它不可信输入。"""
    return f"{name} {_SAFE_FAILURE_CODES[code]}({code})"


def _safe_failure_error(code: str) -> dict[str, str]:
    """构造 allowlisted 安全内联 error 字段(actions_recent/calibration 单条失败用)。"""
    return {"code": code, "message": _SAFE_FAILURE_CODES[code]}


# state.current / changes.recent 等 IntelligenceService 读操作在“当前 active
# snapshot 尚无已提交 personal_state run”时返回 ok=False + error.code=="run_missing"。
# 这是权威自身发布的真实空状态语义(尚未产出个人状态分析),不是读取异常,必须映射
# 为 empty 而非 error,否则会把“还没跑分析”误报成“读取失败”掩盖真实降级原因。
_INTELLIGENCE_EMPTY_CODES = frozenset({"run_missing"})


def _intelligence_data_or_raise(
    result: dict[str, Any], fallback_code: str,
) -> dict[str, Any] | None:
    """校验 IntelligenceService 读操作结果:成功返回 data;真实空状态(run_missing)
    返回 None 交调用方降级为零值 empty 分区;其余失败 raise ValueError(safe code)
    交 _collect/单条 try 隔离为 error(safe code 来自权威自身的固定错误词表,
    不是 str(exc),因此可安全传播)。"""
    if result.get("ok"):
        return result["data"]
    code = str((result.get("error") or {}).get("code") or fallback_code)
    if code in _INTELLIGENCE_EMPTY_CODES:
        return None
    raise ValueError(code)


def _db_readable(path: Path) -> bool:
    """以 mode=ro 打开并执行 SELECT 1 验证可读性。"""
    if not path.exists():
        return False
    try:
        con = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
            con.execute("SELECT 1")
        finally:
            con.close()
        return True
    except (OSError, sqlite3.Error):
        return False


class CockpitProjectionService:
    """Read-only cockpit projection over the five read authorities."""

    def __init__(
        self,
        db_path: Path | None = None,
        read_service: DecisionIntelligenceReadService | None = None,
    ) -> None:
        self.db_path = Path(db_path) if db_path else UNIFIED_DB
        self.read_service = read_service or DecisionIntelligenceReadService()

    @staticmethod
    def _error(operation: str, code: str, detail: str = "") -> dict[str, Any]:
        return {
            "schema_version": INTERFACE_SCHEMA_VERSION,
            "operation": operation,
            "ok": False,
            "error": {"code": code, "detail": detail},
        }

    def invoke(self, operation: str, **params: Any) -> dict[str, Any]:
        handler = getattr(self, "_" + operation.replace(".", "_"), None)
        if handler is None:
            return self._error(operation, "unknown_operation", operation)
        return handler(**params)

    def _envelope(
        self,
        operation: str,
        generated_at: str,
        sections: dict[str, Any],
        authorities: dict[str, str],
        limitations: list[str],
        snapshot_bindings: dict[str, Any],
        freshness: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "schema_version": INTERFACE_SCHEMA_VERSION,
            "operation": operation,
            "ok": True,
            "generated_at": generated_at,
            "snapshot_bindings": snapshot_bindings,
            "freshness": freshness,
            "authorities": authorities,
            "partial": any(status == "error" for status in authorities.values()),
            "limitations": limitations,
            "data": sections,
        }

    @staticmethod
    def _collect(
        loaders: dict[str, Callable[[], dict[str, Any]]],
        limitations: list[str],
        is_empty: Callable[[str, dict[str, Any]], bool],
    ) -> tuple[dict[str, Any], dict[str, str]]:
        sections: dict[str, Any] = {}
        authorities: dict[str, str] = {}
        for name, loader in loaders.items():
            try:
                section = loader()
            except Exception:  # noqa: BLE001 — 单节失败必须被隔离,详情不进入公开响应
                sections[name] = None
                authorities[name] = "error"
                limitations.append(_safe_failure_message(name, "authority_read_failed"))
                continue
            sections[name] = section
            authorities[name] = "empty" if is_empty(name, section) else "ok"
        return sections, authorities

    # --- overview.get ------------------------------------------------------

    def _overview_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {
            "personal": self._personal_section,
            "decision": self._decision_section,
            "proactive": self._proactive_section,
            "external": self._external_section,
            "knowledge": self._knowledge_section,
        }
        sections, authorities = self._collect(loaders, limitations, self._overview_empty)
        personal = sections.get("personal") or {}
        external = sections.get("external") or {}
        knowledge = sections.get("knowledge") or {}
        snapshot_bindings = {
            "personal": personal.get("snapshot_id"),
            "external": external.get("snapshot_id"),
            "serving": knowledge.get("serving_snapshot_id"),
        }
        freshness = {
            "personal_as_of": personal.get("as_of"),
            "knowledge_unit_count": knowledge.get("unit_count"),
            "generated_at": generated_at,
        }
        return self._envelope(
            "overview.get", generated_at, sections, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _overview_empty(name: str, section: dict[str, Any]) -> bool:
        if name in {"personal", "decision", "proactive"}:
            return not section.get("total_available")
        if name == "external":
            return not (section.get("sources_count") or section.get("facts_count"))
        return not section.get("unit_count")

    def _personal_section(self) -> dict[str, Any]:
        result = IntelligenceService(self.db_path).invoke("state.current", limit=50)
        data = _intelligence_data_or_raise(result, "personal_read_failed")
        if data is None:
            return {
                "snapshot_id": None, "as_of": None, "total_available": 0,
                "domains": {}, "status_counts": {}, "top_items": [],
            }
        items = list(data.get("items") or [])
        domains: dict[str, int] = {}
        status_counts: dict[str, int] = {}
        for item in items:
            key = item.get("key") or {}
            domain = str(key.get("domain") or "unknown")
            domains[domain] = domains.get(domain, 0) + 1
            status = str(item.get("status") or "unknown")
            status_counts[status] = status_counts.get(status, 0) + 1
        top_items = [
            {
                "key": item.get("key"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "provenance_class": item.get("provenance_class"),
            }
            for item in items[:_TOP_ITEMS]
        ]
        return {
            "snapshot_id": (result.get("snapshot") or {}).get("snapshot_id"),
            "as_of": data.get("as_of"),
            "total_available": data.get("total_available", len(items)),
            "domains": domains,
            "status_counts": status_counts,
            "top_items": top_items,
        }

    def _decision_section(self) -> dict[str, Any]:
        result = DecisionFeedbackService(self.db_path).invoke("recommendations.list", limit=20)
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        data = result["data"]
        items = list(data.get("items") or [])
        queue: dict[str, int] = {}
        for item in items:
            state = str(item.get("confirmation_state") or "unknown")
            queue[state] = queue.get(state, 0) + 1
        return {
            "total_available": data.get("total_available", len(items)),
            "queue": queue,
            "items": [
                {
                    "recommendation_id": item.get("recommendation_id"),
                    "domain": item.get("domain"),
                    "recommendation_kind": item.get("recommendation_kind"),
                    "horizon": item.get("horizon"),
                    "confidence": item.get("confidence"),
                    "confirmation_state": item.get("confirmation_state"),
                    "action_state": item.get("action_state"),
                    "expires_at": item.get("expires_at"),
                }
                for item in items[:_TOP_ITEMS]
            ],
        }

    def _proactive_section(self) -> dict[str, Any]:
        result = ProactiveIntelligenceService(self.db_path).invoke("inbox.list", limit=10)
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "proactive_read_failed"))
        data = result["data"]
        items = list(data.get("items") or [])
        return {
            "total_available": data.get("total_available", len(items)),
            "items": [
                {
                    "candidate_id": item.get("candidate_id"),
                    "domains": item.get("domains"),
                    "importance": item.get("importance"),
                    "candidate_class": item.get("candidate_class"),
                    "expires_at": item.get("expires_at"),
                    "reason_codes": item.get("reason_codes"),
                }
                for item in items[:_TOP_ITEMS]
            ],
        }

    def _external_section(self) -> dict[str, Any]:
        result = self.read_service.invoke("external.list", limit=10)
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "external_read_failed"))
        data = result["data"]
        snapshot = data.get("snapshot") or {}
        return {
            "snapshot_id": snapshot.get("snapshot_id"),
            "sources_count": len(data.get("sources") or []),
            "facts_count": len(data.get("facts") or []),
        }

    def _knowledge_section(self) -> dict[str, Any]:
        status = get_knowledge_status(probe_chroma=False)
        return {
            "active_collection": status.get("active_collection"),
            "unit_count": status.get("unit_count") or status.get("db_unit_count"),
            "serving_snapshot_id": status.get("serving_snapshot_id"),
        }

    # --- system.status.get -------------------------------------------------

    def _system_status_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {
            "ports": self._ports_section,
            "knowledge": self._knowledge_status_section,
            "authority_dbs": self._authority_dbs_section,
        }
        sections, authorities = self._collect(loaders, limitations, lambda _name, _section: False)
        knowledge = sections.get("knowledge") or {}
        snapshot_bindings = {
            "personal": None,
            "external": None,
            "serving": knowledge.get("serving_snapshot_id"),
        }
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": knowledge.get("unit_count"),
            "generated_at": generated_at,
        }
        return self._envelope(
            "system.status.get", generated_at, sections, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _ports_section() -> dict[str, Any]:
        ports = {"rest": {"up": True, "port": _REST_PORT}}
        for name, port in _PORT_PROBES.items():
            ports[name] = {"up": _port_up(port), "port": port}
        return ports

    @staticmethod
    def _knowledge_status_section() -> dict[str, Any]:
        status = get_knowledge_status(probe_chroma=True)
        keys = (
            "available", "active_collection", "unit_count", "serving_snapshot_id",
            "snapshot_hash", "snapshot_drift", "pointer_exists",
        )
        section = {key: status.get(key) for key in keys}
        # chroma 实测字段(chroma 未起时以 chroma_error 形式返回)照实带上
        for key in ("chroma_available", "chroma_port", "chroma_error", "db_unit_count"):
            if key in status:
                section[key] = status.get(key)
        return section

    @staticmethod
    def _authority_dbs_section() -> dict[str, Any]:
        return {
            name: {
                "path": path.name,
                "exists": path.exists(),
                "readable": _db_readable(path),
            }
            for name, path in AUTHORITY_DB_PATHS.items()
        }

    # --- personal_state.get ------------------------------------------------

    def _personal_state_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {
            "state": lambda: self._personal_state_detail(limitations),
            "changes": self._recent_changes_detail,
        }
        sections, authorities = self._collect(loaders, limitations, self._personal_state_empty)
        # data 为扁平复合形状,失败节贡献零值字段(partial + limitations 表达降级)
        state = sections.get("state") or {}
        changes = sections.get("changes") or {}
        data = {
            "snapshot_id": state.get("snapshot_id"),
            "as_of": state.get("as_of"),
            "total_available": state.get("total_available", 0),
            "history_total_available": state.get("history_total_available"),
            "domains": state.get("domains") or _empty_domains(),
            "lifecycle_counts": state.get("lifecycle_counts") or _zero_lifecycle_counts(),
            "recent_changes": changes.get("items") or [],
        }
        snapshot_bindings = {
            "personal": state.get("snapshot_id"),
            "external": None,
            "serving": None,
        }
        freshness = {
            "personal_as_of": state.get("as_of"),
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "personal_state.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _personal_state_empty(_name: str, section: dict[str, Any]) -> bool:
        return not section.get("total_available")

    def _personal_state_detail(self, limitations: list[str]) -> dict[str, Any]:
        service = IntelligenceService(self.db_path)
        result = service.invoke("state.current", limit=_STATE_LIMIT)
        data = _intelligence_data_or_raise(result, "personal_read_failed")
        if data is None:
            return {
                "snapshot_id": None, "as_of": None, "total_available": 0,
                "history_total_available": None,
                "domains": _empty_domains(), "lifecycle_counts": _zero_lifecycle_counts(),
            }
        items = list(data.get("items") or [])
        total_available = data.get("total_available", len(items))
        domains = _empty_domains()
        lifecycle_counts = _zero_lifecycle_counts()
        skipped_domains = 0
        for item in items:
            key = item.get("key") or {}
            status = str(item.get("status") or "")
            if status in lifecycle_counts:
                lifecycle_counts[status] += 1
            bucket = domains.get(str(key.get("domain") or ""))
            if bucket is None:
                skipped_domains += 1
                continue
            bucket["total"] += 1
            kind = str(key.get("assertion_kind") or "")
            if kind in bucket["by_kind"]:
                bucket["by_kind"][kind] += 1
            provenance = str(item.get("provenance_class") or "")
            if provenance in bucket["by_provenance"]:
                bucket["by_provenance"][provenance] += 1
            if status == "conflict":
                bucket["conflicts"] += 1
            if len(bucket["assertions"]) < _DOMAIN_ASSERTIONS_MAX:
                bucket["assertions"].append({
                    "key": key,
                    "provenance_class": item.get("provenance_class"),
                    "status": item.get("status"),
                    "confidence": item.get("confidence"),
                    "current_assertion_id": item.get("current_assertion_id"),
                    # snapshot 绑定见 data.snapshot_id(单快照全局一致);checksum 与
                    # current_assertion_id 一起构成 evidence.resolve 的稳定引用三元组
                    # (Phase 37:EVID-01),不额外暴露断言明文值
                    "current_value_checksum": item.get("current_value_checksum"),
                    "evidence_count": len(item.get("evidence_status") or []),
                })
        if skipped_domains:
            limitations.append(
                f"{skipped_domains} 条断言的 domain 不在固定八域词表内,未计入 domains 分桶"
            )
        if total_available > len(items):
            limitations.append(
                f"state.current 仅取前 {len(items)}/{total_available} 条,"
                "domains/lifecycle_counts 为截断统计"
            )
        history_total: Any = None
        try:
            history = service.invoke("state.history", limit=1)
            if history.get("ok"):
                history_total = (history.get("data") or {}).get("total_available")
            else:
                limitations.append(
                    "state.history 计数读取失败(%s)"
                    % str((history.get("error") or {}).get("code") or "unknown")
                )
        except Exception:  # noqa: BLE001 — 历史计数降级不拖垮 state 节,详情不进入公开响应
            limitations.append(_safe_failure_message("state.history", "history_count_unavailable"))
        return {
            "snapshot_id": (result.get("snapshot") or {}).get("snapshot_id"),
            "as_of": data.get("as_of"),
            "total_available": total_available,
            "history_total_available": history_total,
            "domains": domains,
            "lifecycle_counts": lifecycle_counts,
        }

    def _recent_changes_detail(self) -> dict[str, Any]:
        result = IntelligenceService(self.db_path).invoke("changes.recent", limit=_CHANGES_LIMIT)
        data = _intelligence_data_or_raise(result, "changes_read_failed")
        if data is None:
            return {"total_available": 0, "items": []}
        items = [
            {
                "record_id": item.get("record_id"),
                "record_type": item.get("record_type"),
                "status": item.get("status"),
                "domain": (item.get("key") or {}).get("domain"),
                "subject": (item.get("key") or {}).get("subject"),
                "effective_at": item.get("effective_at"),
            }
            for item in list(data.get("items") or [])
        ]
        return {"total_available": data.get("total_available", len(items)), "items": items}

    # --- external_delta.get ------------------------------------------------

    def _external_delta_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {"external": lambda: self._external_delta_section(limitations)}
        sections, authorities = self._collect(loaders, limitations, self._external_delta_empty)
        section = sections.get("external")
        snapshot_bindings = {
            "personal": None,
            "external": (section or {}).get("snapshot", {}).get("snapshot_id"),
            "serving": None,
        }
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "external_delta.get", generated_at, section, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _external_delta_empty(_name: str, section: dict[str, Any]) -> bool:
        return not (section.get("sources") or section.get("facts"))

    def _external_delta_section(self, limitations: list[str]) -> dict[str, Any]:
        result = self.read_service.invoke("external.list", limit=_EXTERNAL_FACTS_LIMIT)
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "external_read_failed"))
        data = result["data"]
        snapshot_raw = data.get("snapshot") or {}
        sources = [
            {
                "source_id": source.get("source_id"),
                "authority_role": source.get("authority_role"),
                "source_type": source.get("source_type"),
                "topic": source.get("topic"),
                "region": source.get("region"),
                "endpoint": source.get("endpoint"),
            }
            for source in list(data.get("sources") or [])
        ]
        raw_facts = list(data.get("facts") or [])
        reference = _parse_iso(snapshot_raw.get("activated_at"))
        if reference is None:
            limitations.append(
                "active snapshot 缺少可解析的 activated_at,delta 分类与逐 fact freshness 全部保守留空/unknown"
            )
        window = timedelta(days=_DELTA_WINDOW_DAYS)
        fact_ids = [str(fact.get("fact_id")) for fact in raw_facts if fact.get("fact_id")]
        source_ids_by_fact = self._external_fact_source_ids(fact_ids)
        facts: list[dict[str, Any]] = []
        for fact in raw_facts:
            lifecycle = str(fact.get("lifecycle") or "")
            fact_id = str(fact.get("fact_id") or "")
            facts.append({
                "fact_id": fact.get("fact_id"),
                # canonical External DTO(Phase 37:D-37-02):subject/predicate 命名轴 +
                # 固定 来源/地区/有效期/quality/confidence/lifecycle/conflict/freshness 字段,
                # 不再与 fact_type/observed_at/source_id 两套互相冲突的字段并存
                "fact_checksum": fact.get("fact_checksum"),
                "subject": fact.get("subject"),
                "predicate": fact.get("predicate"),
                "region": fact.get("region"),
                "valid_from": fact.get("valid_from"),
                "valid_to": fact.get("valid_to"),
                "source_quality": fact.get("source_quality"),
                "fact_confidence": fact.get("fact_confidence"),
                "source_ids": source_ids_by_fact.get(fact_id, []),
                "lifecycle": fact.get("lifecycle"),
                "conflict": lifecycle == "conflict",
                "freshness": _fact_freshness(fact.get("valid_to"), reference, window),
            })
        delta: dict[str, list[Any]] = {"new": [], "updated": [], "expiring": [], "conflicts": []}
        if reference is not None:
            for fact in facts:
                valid_from = _parse_iso(fact.get("valid_from"))
                if valid_from is not None and abs(reference - valid_from) <= window:
                    delta["new"].append(fact["fact_id"])
                valid_to = _parse_iso(fact.get("valid_to"))
                if valid_to is not None and valid_to <= reference + window:
                    delta["expiring"].append(fact["fact_id"])
                if fact["conflict"]:
                    delta["conflicts"].append(fact["fact_id"])
        limitations.append("external.list 不暴露逐 fact 更新事件,delta.updated 恒为空数组")
        return {
            "snapshot": {
                "snapshot_id": snapshot_raw.get("snapshot_id"),
                "snapshot_hash": snapshot_raw.get("snapshot_hash"),
                "activated_at": snapshot_raw.get("activated_at"),
            },
            "sources": sources,
            "facts": facts,
            "delta": delta,
            "counts": {
                "sources": len(sources),
                "facts": len(facts),
                "conflicts": len(delta["conflicts"]),
            },
        }

    @staticmethod
    def _external_fact_source_ids(fact_ids: list[str]) -> dict[str, list[str]]:
        """一次性只读聚合 fact_id → 支撑 observation 的 source_id 列表(同 _outcome_counts 先例)。

        external_facts 表本身不直接持有 source_id;来源身份需经
        external_fact_support → external_observations 关联还原,单条 explain
        (facts.get)不做该 join,故这里用一次 mode=ro 批量查询取代 N+1。
        """
        if not fact_ids:
            return {}
        con = sqlite3.connect(f"file:{EXTERNAL_CONTEXT_DB.resolve().as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
            placeholders = ",".join("?" for _ in fact_ids)
            rows = con.execute(
                "SELECT fs.fact_id, o.source_id FROM external_fact_support fs "
                "JOIN external_observations o ON o.observation_id = fs.observation_id "
                f"WHERE fs.fact_id IN ({placeholders})",
                fact_ids,
            ).fetchall()
            grouped: dict[str, set[str]] = {}
            for fact_id, source_id in rows:
                grouped.setdefault(str(fact_id), set()).add(str(source_id))
            return {key: sorted(values) for key, values in grouped.items()}
        finally:
            con.close()

    # --- decision_queue.get ------------------------------------------------

    def _decision_queue_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {"decision": lambda: self._decision_queue_section(limitations)}
        sections, authorities = self._collect(loaders, limitations, self._decision_queue_empty)
        # data 恒为完整看板形状,decision 节失败时退化为全零(authorities/limitations 表达降级)
        data = sections.get("decision") or _empty_decision_queue()
        snapshot_bindings = {"personal": None, "external": None, "serving": None}
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "decision_queue.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _decision_queue_empty(_name: str, section: dict[str, Any]) -> bool:
        return not section.get("total_available")

    def _decision_queue_section(self, limitations: list[str]) -> dict[str, Any]:
        result = DecisionFeedbackService(self.db_path).invoke(
            "recommendations.list", limit=_QUEUE_LIMIT,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        data = result["data"]
        items = list(data.get("items") or [])
        total_available = data.get("total_available", len(items))
        outcome_counts = self._outcome_counts()
        now = datetime.now(timezone.utc)
        queue = _empty_decision_queue()
        queue["total_available"] = total_available
        for item in items:
            card = {key: item.get(key) for key in _QUEUE_CARD_KEYS}
            has_outcome = outcome_counts.get(str(item.get("recommendation_id") or ""), 0) > 0
            stage = _classify_stage({**card, "has_outcome": has_outcome}, now)
            queue["stages"][stage].append(card)
            queue["stage_counts"][stage] += 1
        if total_available > len(items):
            limitations.append(
                f"recommendations.list 仅取前 {len(items)}/{total_available} 条,"
                "stage_counts/stages 为截断统计"
            )
        return queue

    def _outcome_counts(self) -> dict[str, int]:
        """一次性只读统计各 recommendation 的 outcome 数。

        逐条调 recommendations.outcomes 会对每条重跑全链校验(N+1),看板只需
        has_outcome 布尔,故用单条 mode=ro SQL 聚合;明细仍以 recommendations.outcomes 为准。
        """
        con = sqlite3.connect(f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute(
                "SELECT recommendation_id, COUNT(*) FROM decision_outcomes"
                " GROUP BY recommendation_id"
            ).fetchall()
            return {str(row[0]): int(row[1]) for row in rows}
        finally:
            con.close()

    # --- decision_workspace.get --------------------------------------------

    def _decision_workspace_get(self, recommendation_id: Any = None, **_params: Any) -> dict[str, Any]:
        rid = str(recommendation_id or "").strip()
        if not rid:
            return self._error(
                "decision_workspace.get", "invalid_input", "recommendation_id 必填",
            )
        generated_at = _utc_now()
        limitations: list[str] = [
            "recommendations.history 不暴露事件时间戳/status,history 仅含链上校验字段",
        ]
        loaders = {
            "recommendation": lambda: self._workspace_recommendation(rid),
            "history": lambda: self._workspace_history(rid),
            "outcomes": lambda: self._workspace_typed(rid, "recommendations.outcomes"),
            "effectiveness": lambda: self._workspace_typed(rid, "recommendations.effectiveness"),
        }
        sections, authorities = self._collect(loaders, limitations, self._workspace_empty)
        recommendation = sections.get("recommendation")
        data = {
            "recommendation": recommendation,
            "history": sections.get("history") or [],
            "outcomes": sections.get("outcomes") or [],
            "effectiveness": sections.get("effectiveness") or [],
            "linked_analysis_run_id": self._linked_analysis_run_id(recommendation),
        }
        snapshot_bindings = {
            "personal": (recommendation or {}).get("snapshot_id"),
            "external": None,
            "serving": None,
        }
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "decision_workspace.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _workspace_empty(name: str, section: Any) -> bool:
        if name == "recommendation":
            return False
        return not section

    def _workspace_recommendation(self, rid: str) -> dict[str, Any]:
        result = DecisionFeedbackService(self.db_path).invoke(
            "recommendations.get", recommendation_id=rid,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        return dict(result["data"])

    def _workspace_history(self, rid: str) -> list[dict[str, Any]]:
        result = DecisionFeedbackService(self.db_path).invoke(
            "recommendations.history", recommendation_id=rid, limit=_QUEUE_LIMIT,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        return [
            {key: event.get(key) for key in _HISTORY_EVENT_KEYS}
            for event in list(result["data"].get("items") or [])
        ]

    def _workspace_typed(self, rid: str, operation: str) -> list[dict[str, Any]]:
        result = DecisionFeedbackService(self.db_path).invoke(
            operation, recommendation_id=rid, limit=_WORKSPACE_TYPED_LIMIT,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        return [dict(item) for item in list(result["data"].get("items") or [])]

    @staticmethod
    def _linked_analysis_run_id(recommendation: Any) -> str | None:
        """从 support[] 提取上游 analysis run;真实词表中 support 条目的
        authority_id 恒为 a.personal_change(无 "analysis" 值),其 source_run_id
        即来源分析 run;support 缺失时回退 recommendation.source_run_id。"""
        if not isinstance(recommendation, Mapping):
            return None
        for entry in recommendation.get("support") or ():
            if isinstance(entry, Mapping) and entry.get("source_run_id"):
                return str(entry["source_run_id"])
        source_run_id = recommendation.get("source_run_id")
        return str(source_run_id) if source_run_id else None

    # --- actions_recent.get ------------------------------------------------

    def _actions_recent_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = [
            "recommendations.history 不暴露事件时间戳/status,timeline 仅含链上校验字段",
        ]
        loaders = {"decision": lambda: self._actions_recent_section(limitations)}
        sections, authorities = self._collect(loaders, limitations, self._actions_recent_empty)
        # data 恒为完整形状,decision 节失败时退化为全零(authorities/limitations 表达降级)
        data = sections.get("decision") or _empty_actions_recent()
        snapshot_bindings = {"personal": None, "external": None, "serving": None}
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "actions_recent.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _actions_recent_empty(_name: str, section: dict[str, Any]) -> bool:
        return not section.get("total_available")

    def _actions_recent_section(self, limitations: list[str]) -> dict[str, Any]:
        result = DecisionFeedbackService(self.db_path).invoke(
            "recommendations.list", limit=_ACTIONS_RECENT_LIST_LIMIT,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "decision_read_failed"))
        data = result["data"]
        items = list(data.get("items") or [])
        total_available = data.get("total_available", len(items))
        if total_available > len(items):
            limitations.append(
                f"recommendations.list 按 created_at 升序仅取前 {len(items)}/{total_available} 条,"
                "最近推荐可能未进入窗口"
            )
        action_states = self._action_states()
        # 升序窗口内最近的一组在尾部,超出 _ACTIONS_RECENT_MAX 的只计数不组装
        window = items[-_ACTIONS_RECENT_MAX:] if len(items) > _ACTIONS_RECENT_MAX else items
        section = _empty_actions_recent()
        section["total_available"] = total_available
        for item in window:
            card = {key: item.get(key) for key in _ACTION_CARD_KEYS}
            rid = str(item.get("recommendation_id") or "")
            try:
                entry = self._actions_recent_item(rid, card, action_states)
            except Exception:  # noqa: BLE001 — 单条组装失败必须被隔离,详情不进入公开响应
                limitations.append(
                    _safe_failure_message(f"recommendation {rid}", "item_assembly_failed")
                )
                entry = {
                    **card, "timeline": _empty_timeline(),
                    "outcomes": [], "effectiveness": [],
                    "error": _safe_failure_error("item_assembly_failed"),
                }
            else:
                if entry["outcomes"]:
                    section["with_outcome"] += 1
                elif str(item.get("action_state") or "") == "completed":
                    section["awaiting_outcome"] += 1
            section["items"].append(entry)
        section["shown"] = len(section["items"])
        return section

    def _actions_recent_item(
        self, rid: str, card: dict[str, Any], action_states: Mapping[str, str],
    ) -> dict[str, Any]:
        """组装单条推荐的全链时间线条目。

        复用 decision_workspace 的三个只读节函数(history / outcomes /
        effectiveness),不另起一套调用;失败抛异常由调用方隔离成单条 error。
        """
        history = self._workspace_history(rid)
        outcomes = self._workspace_typed(rid, "recommendations.outcomes")
        effectiveness = self._workspace_typed(rid, "recommendations.effectiveness")
        return {
            **card,
            "timeline": _build_timeline(history, action_states),
            "outcomes": outcomes,
            "effectiveness": effectiveness,
        }

    def _action_states(self) -> dict[str, str]:
        """一次性只读取 action_id → action_state。

        history 只暴露链上六字段(无 action_state),timeline 的 action_start /
        action_complete 细分只需状态词,故用单条 mode=ro SQL 取全量映射
        (同 _outcome_counts 先例);明细仍以 recommendations.history 为准。
        """
        con = sqlite3.connect(f"file:{self.db_path.resolve().as_posix()}?mode=ro", uri=True)
        try:
            con.execute("PRAGMA query_only=ON")
            rows = con.execute(
                "SELECT action_id, action_state FROM decision_actions"
            ).fetchall()
            return {str(row[0]): str(row[1]) for row in rows}
        finally:
            con.close()

    # --- proactive_summary.get ----------------------------------------------

    def _proactive_summary_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {
            "inbox": lambda: self._proactive_inbox_section(limitations),
            "metrics": self._proactive_metrics_section,
        }
        sections, authorities = self._collect(loaders, limitations, self._proactive_summary_empty)
        # data 恒为完整复合形状,失败节贡献零值字段(partial + limitations 表达降级)
        inbox = sections.get("inbox") or {}
        data = {
            "total_available": inbox.get("total_available", 0),
            "groups": inbox.get("groups") or _empty_proactive_groups(),
            "metrics": sections.get("metrics"),
            "notes": [
                "suppressed/cooldown 状态需按 candidate_id 调 /proactive/controls/status "
                "逐条查询(前端按需)",
                "now/deferrable 按 importance.final_score >= ranking policy "
                f"threshold({DEFAULT_RANKING_POLICY.threshold}) 分组,仅覆盖 eligible 候选",
            ],
        }
        snapshot_bindings = {"personal": None, "external": None, "serving": None}
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "proactive_summary.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _proactive_summary_empty(name: str, section: dict[str, Any]) -> bool:
        if name == "inbox":
            return not section.get("total_available")
        return False

    def _proactive_inbox_section(self, limitations: list[str]) -> dict[str, Any]:
        result = ProactiveIntelligenceService(self.db_path).invoke(
            "inbox.list", limit=_PROACTIVE_INBOX_LIMIT,
        )
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "proactive_read_failed"))
        data = result["data"]
        items = list(data.get("items") or [])
        total_available = data.get("total_available", len(items))
        if total_available > len(items):
            limitations.append(
                f"inbox.list 仅取前 {len(items)}/{total_available} 条,分组为截断统计"
            )
        groups = _empty_proactive_groups()
        unscored = 0
        for item in items:
            card = {key: item.get(key) for key in _PROACTIVE_CARD_KEYS}
            score = (item.get("importance") or {}).get("final_score")
            # importance 结构不确定时保守归 deferrable + limitation,不臆造分组
            if isinstance(score, bool) or not isinstance(score, (int, float)):
                unscored += 1
                groups["deferrable"].append(card)
            elif score >= DEFAULT_RANKING_POLICY.threshold:
                groups["now"].append(card)
            else:
                groups["deferrable"].append(card)
        if unscored:
            limitations.append(
                f"{unscored} 条候选的 importance.final_score 缺失/非数值,保守归入 deferrable"
            )
        return {"total_available": total_available, "groups": groups}

    def _proactive_metrics_section(self) -> dict[str, Any]:
        result = ProactiveIntelligenceService(self.db_path).invoke("metrics.get")
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "proactive_read_failed"))
        # metrics.get 的 data 全为 metadata-only 计数字段,原样保留
        return dict(result["data"])

    # --- calibration_overview.get --------------------------------------------

    def _calibration_overview_get(self, **_params: Any) -> dict[str, Any]:
        generated_at = _utc_now()
        limitations: list[str] = []
        loaders = {"calibration": lambda: self._calibration_overview_section(limitations)}
        sections, authorities = self._collect(loaders, limitations, self._calibration_overview_empty)
        # data 恒为完整形状,calibration 节失败时退化为全零(authorities/limitations 表达降级)
        data = sections.get("calibration") or {"total": 0, "shown": 0, "protocols": []}
        snapshot_bindings = {"personal": None, "external": None, "serving": None}
        freshness = {
            "personal_as_of": None,
            "knowledge_unit_count": None,
            "generated_at": generated_at,
        }
        return self._envelope(
            "calibration_overview.get", generated_at, data, authorities, limitations,
            snapshot_bindings, freshness,
        )

    @staticmethod
    def _calibration_overview_empty(_name: str, section: dict[str, Any]) -> bool:
        return not section.get("total")

    def _calibration_overview_section(self, limitations: list[str]) -> dict[str, Any]:
        result = self.read_service.invoke("calibration.list", limit=_CALIBRATION_LIST_LIMIT)
        if not result.get("ok"):
            raise ValueError(str((result.get("error") or {}).get("code") or "calibration_read_failed"))
        data = result["data"]
        ids = [
            str(item.get("protocol_id") or "")
            for item in list(data.get("items") or [])
        ]
        # calibration.list 无 total_available,count 即 limit 窗口内行数
        total = data.get("count", len(ids))
        if total >= _CALIBRATION_LIST_LIMIT:
            limitations.append(
                f"calibration.list 达到上限 {_CALIBRATION_LIST_LIMIT},total 为下界"
            )
        protocols: list[dict[str, Any]] = []
        for pid in ids[:_CALIBRATION_EXPLAIN_MAX]:
            try:
                view_result = self.read_service.invoke("calibration.explain", protocol_id=pid)
                if not view_result.get("ok"):
                    raise ValueError(str(
                        (view_result.get("error") or {}).get("code") or "calibration_read_failed"
                    ))
                protocols.append(_calibration_summary(pid, view_result["data"]))
            except Exception:  # noqa: BLE001 — 单 protocol 失败必须被隔离,详情不进入公开响应
                limitations.append(
                    _safe_failure_message(f"protocol {pid}", "protocol_explain_failed")
                )
                protocols.append({
                    "protocol_id": pid, "status": None, "verdict": None,
                    "causal_claim": None, "inconclusive_reasons": [],
                    "sample_size": 0, "summary_limitations": [],
                    "error": _safe_failure_error("protocol_explain_failed"),
                })
        if total > len(protocols):
            limitations.append(
                f"calibration.explain 仅覆盖前 {len(protocols)}/{total} 个 protocol,其余只计数"
            )
        return {"total": total, "shown": len(protocols), "protocols": protocols}

    # --- evidence_resolve.get -------------------------------------------------
    #
    # 唯一的只读证据下钻入口(Phase 37:EVID-01)。输入是三种类型化引用之一
    # (personal_state / external_fact / decision),服务端先校验 stable_id /
    # snapshot_id / checksum(personal_state 另需完整 state key)结构,再仅调度到
    # 既有 IntelligenceService.state.explain、DecisionIntelligenceReadService
    # .external.explain 或 DecisionFeedbackService.recommendations.get 三条只读路径
    # 之一——不接受任意资源标识、路径或 URL。篡改/过期 binding、未知 subject、
    # 单 authority 故障与 evidence 不足一律返回可区分的 typed status,绝不回退到
    # "最新记录"、绝不返回 sealed assertion value / 原始正文 / provider body /
    # confirmation-HMAC 材料;External 分支同样只返回与 external_delta.get 同构
    # 的 metadata(不含 raw value),保持与列表投影同一隐私边界。

    def _evidence_resolve_get(self, **params: Any) -> dict[str, Any]:
        subject_type = str(params.get("subject_type") or "").strip()
        stable_id = str(params.get("stable_id") or "").strip()
        snapshot_id = str(params.get("snapshot_id") or "").strip()
        checksum_value = str(params.get("checksum") or "").strip()
        if subject_type not in _EVIDENCE_SUBJECT_TYPES:
            return self._error(
                "evidence_resolve.get", "invalid_input",
                "subject_type 必须是 personal_state/external_fact/decision 之一",
            )
        if not (stable_id and snapshot_id and checksum_value):
            return self._error(
                "evidence_resolve.get", "invalid_input", "stable_id/snapshot_id/checksum 均为必填",
            )
        reference: dict[str, Any] = {
            "subject_type": subject_type, "stable_id": stable_id,
            "snapshot_id": snapshot_id, "checksum": checksum_value,
        }
        if subject_type == "personal_state":
            key = {field: str(params.get(field) or "").strip() for field in _STATE_KEY_FIELDS}
            if any(not value for value in key.values()):
                return self._error(
                    "evidence_resolve.get", "invalid_input",
                    "personal_state 引用缺少完整 state key"
                    "(assertion_kind/subject/domain/scope/predicate)",
                )
            reference.update(key)

        generated_at = _utc_now()
        resolvers: dict[str, Callable[[Mapping[str, Any]], tuple[str, dict[str, Any] | None, list[str], list[str]]]] = {
            "personal_state": self._resolve_personal_state_evidence,
            "external_fact": self._resolve_external_fact_evidence,
            "decision": self._resolve_decision_evidence,
        }
        try:
            status, evidence_result, limitations, next_actions = resolvers[subject_type](reference)
        except Exception:  # noqa: BLE001 — 单次证据解析失败必须被隔离,详情不进入公开响应
            status, evidence_result = "authority_unavailable", None
            next_actions = ["稍后重试,或返回状态/External/决策页重新进入下钻"]
            limitations = [_safe_failure_message(subject_type, "authority_read_failed")]
        authority_status = (
            "error" if status == "authority_unavailable"
            else "empty" if status == "not_found"
            else "ok"
        )
        data = {
            "status": status, "reference": reference,
            "result": evidence_result, "next_actions": next_actions,
        }
        snapshot_bindings = {
            "personal": snapshot_id if subject_type == "personal_state" else None,
            "external": snapshot_id if subject_type == "external_fact" else None,
            "serving": None,
        }
        freshness = {
            "personal_as_of": None, "knowledge_unit_count": None, "generated_at": generated_at,
        }
        return self._envelope(
            "evidence_resolve.get", generated_at, data, {"evidence": authority_status}, limitations,
            snapshot_bindings, freshness,
        )

    def _resolve_personal_state_evidence(
        self, reference: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None, list[str], list[str]]:
        key_params = {field: reference[field] for field in _STATE_KEY_FIELDS}
        result = IntelligenceService(self.db_path).invoke(
            "state.explain", snapshot_id=reference["snapshot_id"], **key_params,
        )
        if not result.get("ok"):
            code = str((result.get("error") or {}).get("code") or "")
            if code == "state_key_missing":
                return "not_found", None, [], ["确认该断言在当前 snapshot 下是否仍存在"]
            if code in {"snapshot_missing", "snapshot_not_validated", "run_missing"}:
                # run_missing 同 _intelligence_data_or_raise 的既有口径(D-36-02):
                # "该 snapshot 尚无已提交 personal_state run" 是权威自身的空状态语义,
                # 不是读取异常;这里的引用必然指向一次曾经存在的断言,故归入
                # expired(绑定的 snapshot 语境已不可再被解释),而非伪造的 authority 故障
                return (
                    "expired", None, [f"引用的 snapshot 已失效({code})"],
                    ["刷新个人状态页后重新下钻"],
                )
            raise ValueError(code or "personal_evidence_read_failed")
        data = result["data"]
        if (
            data.get("current_assertion_id") != reference["stable_id"]
            or data.get("current_value_checksum") != reference["checksum"]
        ):
            return (
                "mismatch", None, ["当前断言已变化,stable_id/checksum 不再匹配"],
                ["刷新个人状态页后重新下钻"],
            )
        evidence = [
            {
                "ref": item.get("ref"), "artifact_type": item.get("artifact_type"),
                "status": item.get("status"), "eligible": item.get("eligible"),
                "privacy_class": item.get("privacy_class"),
            }
            for item in list(data.get("evidence") or [])
        ]
        payload = {
            "subject_type": "personal_state", "stable_id": reference["stable_id"],
            "snapshot_id": data.get("snapshot_id"), "checksum": data.get("current_value_checksum"),
            "key": data.get("key"), "record_lifecycle": data.get("state_status"),
            "provenance_class": data.get("provenance_class"), "confidence": data.get("confidence"),
            "as_of": data.get("as_of"), "evidence": evidence,
            "uncertainty": list(data.get("uncertainty") or []),
        }
        if data.get("abstained"):
            return "abstain", payload, [], ["evidence 暂不满足可用性判定,可稍后重试或改看其它断言"]
        return "ok", payload, [], []

    def _resolve_external_fact_evidence(
        self, reference: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None, list[str], list[str]]:
        result = self.read_service.invoke(
            "external.explain", resource_type="fact", resource_id=reference["stable_id"],
        )
        if not result.get("ok"):
            code = str((result.get("error") or {}).get("code") or "")
            if code == "fact_missing":
                return "not_found", None, [], ["确认 fact_id 是否仍存在"]
            if code in {"fact_not_in_active_snapshot", "fact_snapshot_drift"}:
                return (
                    "expired", None, [f"fact 与当前 active External snapshot 不一致({code})"],
                    ["刷新 External 页面后重新查看"],
                )
            raise ValueError(code or "external_evidence_read_failed")
        item = (result.get("data") or {}).get("item") or {}
        if (
            item.get("snapshot_id") != reference["snapshot_id"]
            or item.get("fact_checksum") != reference["checksum"]
        ):
            return (
                "mismatch", None, ["当前 External snapshot 或 fact checksum 已变化"],
                ["刷新 External 页面后重新下钻"],
            )
        payload = {
            "subject_type": "external_fact", "stable_id": item.get("fact_id"),
            "snapshot_id": item.get("snapshot_id"), "checksum": item.get("fact_checksum"),
            "subject": item.get("subject"), "predicate": item.get("predicate"),
            "region": item.get("region"), "valid_from": item.get("valid_from"),
            "valid_to": item.get("valid_to"), "source_quality": item.get("source_quality"),
            "fact_confidence": item.get("fact_confidence"), "lifecycle": item.get("lifecycle"),
        }
        limitations = list((result.get("data") or {}).get("limitations") or [])
        next_actions = list((result.get("data") or {}).get("next_actions") or [])
        return "ok", payload, limitations, next_actions

    def _resolve_decision_evidence(
        self, reference: Mapping[str, Any],
    ) -> tuple[str, dict[str, Any] | None, list[str], list[str]]:
        result = DecisionFeedbackService(self.db_path).invoke(
            "recommendations.get", recommendation_id=reference["stable_id"],
        )
        if not result.get("ok"):
            code = str((result.get("error") or {}).get("code") or "")
            if code == "recommendation_missing":
                return "not_found", None, [], ["确认 recommendation_id 是否仍存在"]
            raise ValueError(code or "decision_evidence_read_failed")
        item = result["data"]
        if (
            item.get("snapshot_id") != reference["snapshot_id"]
            or item.get("recommendation_checksum") != reference["checksum"]
        ):
            return (
                "mismatch", None, ["当前 recommendation snapshot 或 checksum 已变化"],
                ["刷新决策工作区后重新下钻"],
            )
        payload = {
            "subject_type": "decision", "stable_id": item.get("recommendation_id"),
            "snapshot_id": item.get("snapshot_id"), "checksum": item.get("recommendation_checksum"),
            "confirmation_state": item.get("confirmation_state"),
            "action_state": item.get("action_state"),
            "recommendation_kind": item.get("recommendation_kind"), "domain": item.get("domain"),
            "rationale_codes": item.get("rationale_codes"), "support": item.get("support"),
        }
        return "ok", payload, [], []


__all__ = [
    "AUTHORITY_DB_PATHS",
    "CockpitProjectionService",
    "INTERFACE_SCHEMA_VERSION",
]
