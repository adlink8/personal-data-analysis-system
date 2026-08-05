from __future__ import annotations

import hashlib
import json
from pathlib import Path

from personal_knowledge.services.capability_registry import load_registry, operations_for_profile


ROOT = Path(__file__).resolve().parents[2]
SKILLS = json.loads((ROOT / "governance/manifests/ai/pi-skills.json").read_text(encoding="utf-8"))["skills"]
DATA = {"knowledge.maintenance", "warehouse.health", "warehouse.failed_batch_recovery", "retrieval.rebuild", "snapshot.release"}


def _canonical(value):
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    return value


def _checksum(skill):
    payload = {key: value for key, value in skill.items() if key != "checksum"}
    return hashlib.sha256(json.dumps(_canonical(payload), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def test_five_data_skills_use_only_approved_tools_and_have_exact_sequences() -> None:
    by_id = {skill["id"]: skill for skill in SKILLS}
    capability_ids = {item["id"] for item in operations_for_profile(load_registry(), "production")}
    expected = {
        "knowledge.maintenance": ["warehouse.inspect", "knowledge.extract_l1", "knowledge.repair_candidates", "knowledge.detect_conflicts", "knowledge.backfill", "canonical.verify"],
        "warehouse.health": ["warehouse.inspect", "warehouse.lineage", "warehouse.quality", "warehouse.freshness", "warehouse.integrity", "warehouse.failed_batches"],
        "warehouse.failed_batch_recovery": ["warehouse.failed_batches", "ingestion.preview", "ingestion.quarantine", "ingestion.commit", "canonical.verify"],
        "retrieval.rebuild": ["warehouse.inspect", "index.build", "index.reconcile", "index.evaluate", "snapshot.prepare"],
        "snapshot.release": ["warehouse.inspect", "index.reconcile", "index.evaluate", "snapshot.prepare", "snapshot.activate", "snapshot.rollback"],
    }
    assert DATA <= set(by_id)
    for skill_id, tools in expected.items():
        skill = by_id[skill_id]
        assert skill["checksum"] == _checksum(skill)
        assert [step["tool"] for step in skill["steps"]] == tools
        assert set(skill["allowed_tools"]) == set(tools)
        assert set(tools) <= capability_ids
    release_steps = by_id["snapshot.release"]["steps"]
    assert release_steps[-2]["tool"] == "snapshot.activate" and release_steps[-2]["requires_confirmation"] is True
    assert release_steps[-1]["tool"] == "snapshot.rollback" and release_steps[-1]["requires_confirmation"] is True


def test_data_skill_policy_never_treats_success_as_promotion() -> None:
    by_id = {skill["id"]: skill for skill in SKILLS}
    assert "snapshot.activate" in by_id["snapshot.release"]["allowed_tools"]
    assert "snapshot.rollback" in by_id["snapshot.release"]["allowed_tools"]
    assert "snapshot.activate" not in by_id["retrieval.rebuild"]["allowed_tools"]
    assert "canonical.apply_correction" not in by_id["knowledge.maintenance"]["allowed_tools"]
