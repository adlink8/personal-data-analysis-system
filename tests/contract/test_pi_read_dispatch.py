from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_read_dispatch import (
    READ_DISPATCH_OPERATIONS,
    build_real_warehouse_metadata,
    make_descriptive_evidence_tool,
    make_real_warehouse_tools,
    read_handler,
)
from personal_knowledge.services.warehouse_tools import AUTHORITY_ADAPTERS


def _assert_envelope(result, operation) -> None:
    assert isinstance(result, dict)
    assert result.get("operation") == operation
    # success/empty/error/synthetic 是 dispatch 主词表；wiki 权威还带
    # partial/stale 等 freshness 判定（同 topic_projection 契约）。
    assert result.get("status") in {"success", "empty", "error", "synthetic", "partial", "stale"}
    assert isinstance(result.get("ok"), bool)
    assert isinstance(result.get("provider"), str)
    # synthetic 只允许在真实数据源不可用（库缺失）时出现
    if result.get("status") == "synthetic":
        assert (result.get("error") or {}).get("detail")


def test_read_handler_routes_every_supported_operation_without_raising():
    for operation in sorted(READ_DISPATCH_OPERATIONS):
        result = read_handler(operation, {"limit": 3})
        _assert_envelope(result, operation)
        # 真实环境（库存在）下这些操作不得降级 synthetic
        assert result["status"] != "synthetic", f"{operation} 不应降级 synthetic"


def test_read_handler_unknown_operation_returns_typed_error():
    result = read_handler("module.call", {"limit": 3})
    assert result["status"] == "error" and result["ok"] is False
    assert result["error"]["code"] == "unsupported_read_operation"


def test_read_handler_never_raises_on_hostile_input():
    for payload in (None, "garbage", ["list"], {"limit": "not-a-number"}, {"record_id": 123}):
        result = read_handler("decision.list", payload)
        assert isinstance(result, dict) and result.get("operation") == "decision.list"


def test_read_handler_missing_record_parameters_are_typed_errors():
    for operation, detail_fragment in [
        ("decision.get", "record_id"),
        ("external.get", "record_id"),
        ("knowledge.get", "record_id"),
        ("knowledge.search", "query"),
        ("retrieval.search", "query"),
    ]:
        result = read_handler(operation, {})
        assert result["status"] == "error", operation
        assert result["error"]["code"] == "missing_parameter", operation
        assert detail_fragment in result["error"]["detail"]


def test_read_handler_system_and_retrieval_return_real_data():
    health = read_handler("system.health", {})
    assert health["status"] == "success" and health["ok"] is True
    assert {"services", "databases", "knowledge", "status"} <= set(health["data"])

    status = read_handler("retrieval.status", {})
    assert status["status"] == "success" and status["ok"] is True
    assert "active_collection" in status["data"] or "available" in status["data"]


def test_read_handler_decision_list_returns_real_analysis_runs():
    result = read_handler("decision.list", {"limit": 5})
    assert result["status"] in {"success", "empty"}
    assert "items" in result["data"]


def test_warehouse_metadata_factory_reads_real_authorities():
    metadata = build_real_warehouse_metadata()
    # 生产环境至少应能统计 knowledge / conversation / external 任一权威
    assert isinstance(metadata, dict)
    assert set(metadata) <= set(AUTHORITY_ADAPTERS)
    assert metadata  # 本机真实库存在，不应为空
    for authority_id, item in metadata.items():
        assert "records" in item and "visible" in item and "failed" in item
        assert item["records"] >= 0


def test_warehouse_metadata_factory_falls_back_to_empty_on_missing_db(monkeypatch, tmp_path):
    import personal_knowledge.services.pi_read_dispatch as dispatch
    from personal_knowledge.core import project_paths

    missing = tmp_path / "missing.sqlite"
    monkeypatch.setattr(dispatch, "UNIFIED_DB", missing)
    monkeypatch.setattr(dispatch, "AGENT_CONVERSATIONS_DB", missing)
    monkeypatch.setattr(dispatch, "EXTERNAL_CONTEXT_DB", missing)
    monkeypatch.setattr(dispatch, "VAR_DB", tmp_path)
    metadata = build_real_warehouse_metadata()
    # system 探针仍基于端口/库可读性，允许非空；但具体权威库缺失时不得崩溃
    assert isinstance(metadata, dict)


def test_warehouse_tools_missing_authority_defaults_to_all_authorities():
    tools = make_real_warehouse_tools()
    result = tools.invoke("warehouse.inspect", {"limit": 5})
    assert result["ok"] is True
    assert result["authority_id"] == "all"
    assert result["count"] >= 1
    assert result["counts"]["records"] > 0
    for item in result["authorities"]:
        assert item["operation"] == "warehouse.inspect"
        assert item["authority_id"] in AUTHORITY_ADAPTERS


def test_warehouse_tools_explicit_authority_still_works():
    tools = make_real_warehouse_tools()
    result = tools.invoke("warehouse.inspect", {"authority_id": "knowledge", "limit": 5})
    assert result["ok"] is True
    assert result["authority_id"] == "knowledge"
    assert "counts" in result


def test_api_server_gateway_wires_read_handler_and_warehouse_tools():
    import personal_knowledge.services.api_server as api_server
    from personal_knowledge.services.pi_domain_gateway import DEFAULT_CAPABILITY

    gateway = api_server.PI_DOMAIN_GATEWAY
    assert gateway.read_handler is not None
    assert gateway.warehouse_tools is not None
    assert gateway.evidence_tool is not None

    base = {"task_id": "t", "idempotency_key": "i", "binding": "b"}
    for operation in ("system.health", "retrieval.status"):
        result = gateway.invoke(operation, {**base}, capability=DEFAULT_CAPABILITY)
        assert result["ok"] is True
        assert "synthetic" not in str(result).lower()

    result = gateway.invoke("warehouse.inspect", {**base}, capability=DEFAULT_CAPABILITY)
    assert result["ok"] is True
    assert result["data"]["authority_id"] == "all"


def test_descriptive_evidence_tool_keeps_lease_strict_and_explains_missing_params():
    from personal_knowledge.services.evidence_sqlite_tool import (
        LEASE_SKILL_ID,
        PRIVACY_CEILING,
        knowledge_research_checksum,
    )

    tool = make_descriptive_evidence_tool()
    # lease 契约保持严格：skill_id 不匹配仍 fail-closed
    lease = tool.invoke({
        "database_id": "canonical_conversation_v1",
        "query_id": "conversation.evidence_messages.v1",
        "version": "1.0.0",
        "parameters": {"session_id": "s", "limit": 5},
        "scope": {"session_id": "s"},
        "skill_id": "system.diagnosis",
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
        "binding": "b",
    })
    assert lease["ok"] is False and lease["error"]["code"] == "lease_invalid"

    # 缺 session_id（其余 lease 字段合法）→ 明确说明缺 session_id
    missing = tool.invoke({
        "database_id": "canonical_conversation_v1",
        "query_id": "conversation.evidence_messages.v1",
        "version": "1.0.0",
        "parameters": {"limit": 5},
        "scope": {"session_id": "s"},
        "skill_id": LEASE_SKILL_ID,
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
        "binding": "b",
    })
    assert missing["ok"] is False
    assert missing["error"]["code"] == "parameter_invalid"
    assert "session_id" in missing["error"]["detail"]

    # 缺 database_id → 明确说明
    unknown_db = tool.invoke({
        "query_id": "conversation.evidence_messages.v1",
        "version": "1.0.0",
        "parameters": {"session_id": "s", "limit": 5},
        "scope": {"session_id": "s"},
        "skill_id": LEASE_SKILL_ID,
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
        "binding": "b",
    })
    assert unknown_db["ok"] is False
    assert unknown_db["error"]["code"] == "database_unknown"
    assert "database_id" in unknown_db["error"]["detail"]
