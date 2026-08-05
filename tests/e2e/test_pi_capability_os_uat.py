from __future__ import annotations

import hashlib
import json
from pathlib import Path

from personal_knowledge.services.capability_registry import load_registry, operations_for_profile

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "governance/manifests/ai/pi-capability-os-preregistration.json"
EVIDENCE = ROOT / "ops/reports/evidence/pi-capability-os-uat.json"


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_frozen_capability_os_preregistration_is_zero_call_and_checksum_bound():
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["schema"] == "pi-capability-os-preregistration-v1"
    assert prereg["evidence_class"] == "synthetic_replay"
    assert prereg["provider_mode"] == "replay" and prereg["provider_calls"] == 0
    assert prereg["cost_ceiling_cny"] == 0 and prereg["attempts_per_case"] == 1
    assert len(prereg["case_ids"]) == 16
    assert set(prereg["case_ids"]) == set(prereg["case_input_checksums"])
    unsigned = {key: value for key, value in prereg.items() if key != "preregistration_checksum"}
    assert prereg["registry_checksum"] == load_registry()["checksum"]
    assert prereg["skill_manifest_checksum"] == _sha256(ROOT / "governance/manifests/ai/pi-skills.json")
    assert prereg["runtime_policy_checksum"] == _sha256(ROOT / "governance/manifests/ai/pi-runtime-policy.json")
    assert prereg["entrypoints_checksum"] == _sha256(ROOT / "governance/manifests/ai/pi-ai-entrypoints.json")
    assert prereg["preregistration_checksum"] == hashlib.sha256(_canonical(unsigned).encode()).hexdigest()


def test_uat_covers_phase_55_to_59_and_zero_tolerance_is_clean():
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert evidence["schema"] == "pi-capability-os-uat-v1"
    assert evidence["evidence_class"] == "synthetic_replay"
    assert evidence["preregistration_checksum"] == prereg["preregistration_checksum"]
    assert evidence["case_count"] == len(prereg["case_ids"]) == len(evidence["cases"])
    assert {case["id"] for case in evidence["cases"]} == set(prereg["case_ids"])
    assert all(case["status"] == "PASS" for case in evidence["cases"])
    assert all(case["side_effect_count"] == 0 for case in evidence["cases"])
    assert evidence["provider_calls"] == 0 and evidence["authority_mutations"] == 0
    assert evidence["primary_activated"] is False
    assert evidence["zero_tolerance"] == {"unauthorized_write": 0, "fingerprint_corruption": 0, "privacy_leak": 0, "duplicate_side_effect": 0, "gate_bypass": 0, "split_coordinator": 0}
    assert evidence["real_baseline"]["status"] in {"INCONCLUSIVE", "BLOCKED"}


def test_registry_and_skill_surface_match_frozen_uat():
    registry = load_registry()
    operations = operations_for_profile(registry, "production")
    assert len(operations) == 44
    assert {operation["id"] for operation in operations} >= {"knowledge.search", "warehouse.inspect", "ingestion.preview", "canonical.verify", "index.build", "index.evaluate", "snapshot.prepare"}
    skills = json.loads((ROOT / "governance/manifests/ai/pi-skills.json").read_text(encoding="utf-8"))
    assert skills["schema"] == "pi-skills-v1" and len(skills["skills"]) == 11
    assert all(skill["status"] == "active" and skill["profile"] == "production" for skill in skills["skills"])


def test_uat_evidence_does_not_claim_live_authorization():
    evidence_text = EVIDENCE.read_text(encoding="utf-8")
    assert "synthetic_replay" in evidence_text
    assert '"primary_activated": false' in evidence_text.lower()
    assert '"provider_calls": 0' in evidence_text
