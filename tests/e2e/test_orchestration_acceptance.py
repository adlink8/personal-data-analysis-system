from __future__ import annotations

import hashlib
from pathlib import Path

from personal_knowledge.intelligence.analysis.service import AnalysisReadService
from personal_knowledge.intelligence.orchestration import OrchestrationService, apply_schema
from personal_knowledge.services.api_server import orchestration_rest_contract
from personal_knowledge.services.mcp_server import orchestration_tool_contract
from personal_knowledge.services.orchestration_service import GuardedOrchestrationInterface
from tests.integration.test_project_pilot_authority import setup_authorities


ACTOR = "d" * 64
NOW = "2026-07-18T09:30:00Z"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _setup(tmp_path: Path):
    env = setup_authorities(tmp_path)
    orchestration_db = tmp_path / "orchestration.sqlite"
    apply_schema(orchestration_db)
    core = OrchestrationService(
        db_path=orchestration_db, personal_db=env["personal"], external_db=env["external"],
        confirmation_secret=b"phase-33-e2e-confirmation-secret-32-bytes",
    )
    calls = {"provider": 0, "network": 0, "external_actions": 0, "promotions": 0}
    detail = AnalysisReadService(env["analysis"]).get_run(env["run_id"])

    def runner(_manifest, _payload, _reservation_id, _now):
        calls["provider"] += 1
        return {
            "status": "success",
            "references": {
                "run_id": env["run_id"], "candidate_id": env["candidate_id"],
                "run_checksum": detail["run_checksum"],
                "candidate_checksum": detail["candidate_checksum"],
            },
        }

    interface = GuardedOrchestrationInterface(
        service=core, analysis_db=env["analysis"], pilot_db=env["pilot"],
        calibration_db=tmp_path / "calibration.sqlite", generation_runner=runner,
    )
    return env, orchestration_db, core, interface, calls


def test_real_transport_generation_replays_without_second_provider_call(tmp_path: Path) -> None:
    env, _, core, interface, calls = _setup(tmp_path)
    prepared = orchestration_rest_contract("session.prepare", {
        "goal": "Choose a compatible local runtime",
        "constraints": ["local validation only", "manual operation only"],
        "weights": {"safety": 0.7, "speed": 0.3},
        "actor_identity_hash": ACTOR,
        "max_external_age_seconds": 7200,
        "now": "2026-07-18T09:10:00Z",
    }, service=interface)
    assert prepared["ok"]
    confirmed = orchestration_tool_contract("agent_session_confirm", {
        "preview": prepared["data"], "confirmed": True,
        "idempotency_key": "confirm-e2e", "now": "2026-07-18T09:10:00Z",
    }, service=interface)
    assert confirmed["ok"] and confirmed["data"]["state"] == "confirmed"

    preview = orchestration_rest_contract("session.preview", {
        "session_id": confirmed["data"]["session_id"], "transition": "generate",
        "payload": {"personal_evidence": [], "external_evidence": []},
        "actor_identity_hash": ACTOR, "expected_sequence": 1, "now": NOW,
    }, service=interface)["data"]
    args = {"preview": preview, "confirmed": True, "idempotency_key": "generate-e2e", "now": NOW}
    first = orchestration_tool_contract("agent_session_generate", args, service=interface)
    replay = orchestration_tool_contract("agent_session_generate", args, service=interface)
    assert first["ok"], first
    assert replay["ok"], replay
    assert first["data"]["event_id"] == replay["data"]["event_id"]
    assert replay["data"]["replayed"] is True
    assert calls == {"provider": 1, "network": 0, "external_actions": 0, "promotions": 0}
    resumed = orchestration_rest_contract(
        "session.explain", {"session_id": confirmed["data"]["session_id"], "now": NOW}, service=interface,
    )
    assert resumed["data"]["state"] == "generated"
    assert resumed["data"]["next_operation"] == "publish"
    assert env["run_id"] == first["data"]["references"]["run_id"]


def test_rejected_inputs_leave_every_authority_unchanged(tmp_path: Path) -> None:
    env, orchestration_db, core, interface, calls = _setup(tmp_path)
    paths = [Path(env[key]) for key in ("personal", "external", "analysis", "pilot")] + [orchestration_db]
    before = {path: _sha(path) for path in paths}
    rejected = orchestration_rest_contract("session.prepare", {
        "goal": "Deploy investment automation", "constraints": ["send message"],
        "weights": {"speed": 1.0}, "actor_identity_hash": ACTOR, "now": NOW,
    }, service=interface)
    assert rejected["error"]["code"] == "high_risk_or_external_action_forbidden"
    assert {path: _sha(path) for path in paths} == before

    prepared = interface.invoke(
        "session.prepare", goal="Evaluate another local runtime", constraints=["manual only"],
        weights={"safety": 1.0}, actor_identity_hash=ACTOR,
        max_external_age_seconds=7200, now="2026-07-18T09:10:00Z",
    )["data"]
    token = core.issue_confirmation(prepared, expires_at="2026-07-18T09:11:00Z")
    before_expired = {path: _sha(path) for path in paths}
    expired = interface.invoke(
        "session.confirm", preview=prepared, confirmation_token=token,
        idempotency_key="expired-e2e", now="2026-07-18T09:11:01Z",
    )
    assert expired["error"]["code"] == "confirmation_expired"
    assert {path: _sha(path) for path in paths} == before_expired
    assert calls == {"provider": 0, "network": 0, "external_actions": 0, "promotions": 0}
