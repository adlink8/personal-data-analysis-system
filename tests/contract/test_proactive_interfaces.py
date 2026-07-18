from __future__ import annotations

from personal_knowledge.intelligence.proactive.service import ProactiveIntelligenceService
from personal_knowledge.services.api_server import proactive_rest_contract
from personal_knowledge.services.mcp_server import proactive_tool_contract
from tests.unit.test_proactive_controls import _published_candidate


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
