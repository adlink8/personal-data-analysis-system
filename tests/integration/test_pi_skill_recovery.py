from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_skill_recovery_evidence_is_complete_metadata_only() -> None:
    evidence = json.loads((ROOT / "ops/reports/evidence/pi-skill-evaluation.json").read_text(encoding="utf-8"))
    manifests = json.loads((ROOT / "governance/manifests/ai/pi-skills.json").read_text(encoding="utf-8"))["skills"]
    manifest_ids = {item["id"] for item in manifests}
    result_ids = [item["skill_id"] for item in evidence["results"]]
    assert evidence["schema"] == "pi-skill-evaluation-v1"
    assert set(result_ids) == manifest_ids
    assert len(result_ids) == len(set(result_ids)) == 11
    assert evidence["critical_failures"] == 0
    assert evidence["forbidden_tool_calls"] == 0
    assert evidence["skipped_checkpoint_count"] == 0
    assert evidence["replay_failures"] == 0
    encoded = json.dumps(evidence, ensure_ascii=False).lower()
    assert all(secret not in encoded for secret in ("password", "api_key", "authorization", "raw_body", "absolute_path"))


def test_skill_sequences_and_recovery_states_are_honest() -> None:
    evidence = json.loads((ROOT / "ops/reports/evidence/pi-skill-evaluation.json").read_text(encoding="utf-8"))
    for result in evidence["results"]:
        assert result["expected_tool_sequence"][:len(result["actual_tool_sequence"])] == result["actual_tool_sequence"]
        assert result["side_effect_count"] >= 0
    release = next(item for item in evidence["results"] if item["skill_id"] == "snapshot.release")
    assert release["status"] == "waiting_confirmation"
    assert "snapshot.activate" not in release["actual_tool_sequence"]
    assert "snapshot.rollback" not in release["actual_tool_sequence"]
