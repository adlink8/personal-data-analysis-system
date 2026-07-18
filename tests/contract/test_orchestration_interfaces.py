from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from personal_knowledge.intelligence.analysis.schema import checksum
from personal_knowledge.intelligence.decision.context_binding import DecisionContextBinding, DecisionContextPolicy
from personal_knowledge.intelligence.orchestration import OrchestrationService, apply_schema
from personal_knowledge.services.api_server import orchestration_rest_contract
from personal_knowledge.services.mcp_server import active_tools, orchestration_tool_contract
from personal_knowledge.services.orchestration_service import GuardedOrchestrationInterface


NOW = "2026-07-19T02:00:00Z"
ACTOR = "c" * 64


def _binding(*_args, **_kwargs):
    draft = DecisionContextBinding(
        personal_snapshot_id="ss_fixture", personal_snapshot_hash="a" * 64,
        external_snapshot_id="exs_fixture", external_snapshot_hash="b" * 64,
        policy=DecisionContextPolicy("global", 86400), bound_at=NOW, binding_hash="",
    )
    return replace(draft, binding_hash=checksum(draft.core()))


def _validate(value, *_args, **_kwargs):
    typed = DecisionContextBinding.from_dict(value)
    if checksum(typed.core()) != typed.binding_hash:
        raise ValueError("binding_hash_mismatch")
    return {"ok": True}


def _interface(tmp_path: Path):
    db = tmp_path / "orchestration.sqlite"
    apply_schema(db)
    core = OrchestrationService(
        db_path=db, personal_db=tmp_path / "personal.sqlite", external_db=tmp_path / "external.sqlite",
        confirmation_secret=b"contract-confirmation-secret-at-least-32-bytes",
        binding_factory=_binding, binding_validator=_validate,
    )
    return GuardedOrchestrationInterface(service=core), core


def test_rest_and_stdio_delegate_to_identical_shared_contract(tmp_path: Path) -> None:
    interface, _ = _interface(tmp_path)
    params = {
        "goal": "Choose local validation",
        "constraints": ["manual operation only"],
        "weights": {"safety": 1.0},
        "actor_identity_hash": ACTOR,
        "now": NOW,
    }
    rest = orchestration_rest_contract("session.prepare", params, service=interface)
    mcp = orchestration_tool_contract("agent_session_prepare", params, service=interface)
    assert rest == mcp and rest["ok"]
    assert rest["data"]["operation"] == "confirm"


def test_confirmation_preview_resume_and_stable_errors(tmp_path: Path) -> None:
    interface, core = _interface(tmp_path)
    prepared = interface.invoke(
        "session.prepare", goal="Choose local validation", constraints=["manual only"],
        weights={"safety": 1.0}, actor_identity_hash=ACTOR, now=NOW,
    )["data"]
    token = core.issue_confirmation(prepared)
    confirmed = orchestration_tool_contract("agent_session_confirm", {
        "preview": prepared, "confirmation_token": token,
        "idempotency_key": "confirm-contract", "now": NOW,
    }, service=interface)
    assert confirmed["ok"] and confirmed["data"]["state"] == "confirmed"
    resumed = orchestration_rest_contract(
        "session.resume", {"session_id": confirmed["data"]["session_id"], "now": NOW}, service=interface,
    )
    assert resumed["data"]["sequence"] == 1

    missing = interface.invoke("session.confirm", preview=prepared, idempotency_key="missing", now=NOW)
    assert missing["error"]["code"] == "missing_parameter"
    stale = interface.invoke(
        "session.preview", session_id=confirmed["data"]["session_id"], transition="generate",
        payload={}, actor_identity_hash=ACTOR, expected_sequence=0, now=NOW,
    )
    assert stale["error"]["code"] == "stale_expected_sequence"
    undeclared = interface.invoke("session.resume", session_id="x", surprise=True)
    assert undeclared["error"]["code"] == "undeclared_input"


def test_tool_names_are_additive_and_mutations_are_strict() -> None:
    tools = {tool.name: tool for tool in active_tools()}
    assert "search_semantic" in tools
    expected = {
        "agent_session_prepare", "agent_session_confirm", "agent_session_preview",
        "agent_session_generate", "agent_session_publish", "agent_session_decide",
        "agent_session_observe", "agent_session_calibrate", "agent_session_resume", "agent_session_explain",
    }
    assert expected <= set(tools)
    for name in expected - {"agent_session_prepare", "agent_session_preview", "agent_session_resume", "agent_session_explain"}:
        schema = tools[name].inputSchema
        assert schema["additionalProperties"] is False
        assert {"preview", "confirmation_token", "idempotency_key"} <= set(schema["required"])
