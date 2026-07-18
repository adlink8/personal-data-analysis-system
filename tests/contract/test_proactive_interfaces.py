from __future__ import annotations

from personal_knowledge.intelligence.proactive.service import ProactiveIntelligenceService
from personal_knowledge.services.api_server import proactive_rest_contract
from personal_knowledge.services.mcp_server import proactive_tool_contract
from tests.unit.test_proactive_controls import _published_candidate
from personal_knowledge.intelligence.proactive.cli import _invoke, build_parser


def test_shared_inbox_candidate_explain_and_metrics_are_metadata_only(tmp_path) -> None:
    db, target = _published_candidate(tmp_path)
    service = ProactiveIntelligenceService(db)
    inbox = service.invoke("inbox.list", limit=10)
    assert inbox["ok"] and inbox["privacy"] == {"metadata_only": True, "private_bodies": 0}
    item = inbox["data"]["items"][0]
    assert item["candidate_id"] == target.record_id
    assert service.invoke("candidates.get", candidate_id=target.record_id)["ok"]
    assert service.invoke("candidates.explain", candidate_id=target.record_id)["ok"]
    assert service.invoke("controls.status", candidate_id=target.record_id)["ok"]
    assert service.invoke("metrics.get")["ok"]


def test_rest_and_mcp_delegate_to_one_read_contract(tmp_path) -> None:
    db, _ = _published_candidate(tmp_path)
    rest = proactive_rest_contract("inbox.list", {"limit": "10"}, db_path=db)
    mcp = proactive_tool_contract("proactive_inbox", {"limit": 10}, db_path=db)
    assert rest == mcp
    assert proactive_tool_contract("proactive_control_write", {}, db_path=db)["error"]["code"] == "unknown_operation"


def test_limits_and_reads_are_stable_and_side_effect_free(tmp_path) -> None:
    db, _ = _published_candidate(tmp_path)
    service = ProactiveIntelligenceService(db)
    assert service.invoke("inbox.list", limit=0)["error"]["code"] == "invalid_limit"
    assert service.invoke("inbox.list", limit=101)["error"]["code"] == "invalid_limit"
    before = db.stat().st_size
    first = service.invoke("digest.get", limit=10)
    second = service.invoke("digest.get", limit=10)
    assert first == second and db.stat().st_size == before


def test_guarded_local_surface_append_is_explicit_and_idempotent(tmp_path) -> None:
    db, target = _published_candidate(tmp_path)
    argv = ["--db", str(db), "surface", "--candidate-id", target.record_id,
            "--candidate-checksum", target.record_checksum, "--event-type", "presented",
            "--occurred-at", "2026-07-18T12:00:00Z", "--actor-class", "user",
            "--actor-identity-hash", "4"*64, "--expected-sequence", "0",
            "--idempotency-key", "present-one", "--write", "--i-confirm", target.record_id]
    first = _invoke(build_parser().parse_args(argv))
    second = _invoke(build_parser().parse_args(argv))
    assert first["ok"] and first["status"] == "written"
    assert second["ok"] and second["status"] == "existing"
    assert first["external_actions"] == second["external_actions"] == 0
