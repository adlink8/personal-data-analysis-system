from __future__ import annotations

import hashlib
import json
from pathlib import Path

from personal_knowledge.services.capability_registry import load_registry, operations_for_profile


ROOT = Path(__file__).resolve().parents[2]
SKILLS = json.loads((ROOT / "governance/manifests/ai/pi-skills.json").read_text(encoding="utf-8"))["skills"]
PERSONAL = {"personal.daily_brief", "knowledge.research", "decision.support", "project.planning", "outcome.reflection", "system.diagnosis"}
FIXTURES = [
    "normal_success", "no_match", "collision", "stale_snapshot", "conflicting_evidence", "missing_evidence",
    "authority_unavailable", "tool_failure", "timeout", "cancel", "outcome_unknown", "no_op",
]


def _canonical(value):
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    return value


def _checksum(skill):
    payload = {key: value for key, value in skill.items() if key != "checksum"}
    return hashlib.sha256(json.dumps(_canonical(payload), ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def test_six_personal_skills_have_valid_manifests_and_instructions() -> None:
    by_id = {skill["id"]: skill for skill in SKILLS}
    assert PERSONAL <= set(by_id)
    capability_ids = {item["id"] for item in operations_for_profile(load_registry(), "production")}
    for skill_id in PERSONAL:
        skill = by_id[skill_id]
        assert skill["checksum"] == _checksum(skill)
        assert skill["profile"] == "production"
        assert set(skill["allowed_tools"]) <= capability_ids
        instruction = ROOT / "apps/personal_intelligence_kernel" / "skills" / "personal" / {
            "personal.daily_brief": "daily-brief.md", "knowledge.research": "knowledge-research.md",
            "decision.support": "decision-support.md", "project.planning": "project-planning.md",
            "outcome.reflection": "outcome-reflection.md", "system.diagnosis": "system-diagnosis.md",
        }[skill_id]
        assert hashlib.sha256(instruction.read_bytes()).hexdigest() == skill["instruction_checksum"]


def test_personal_selection_is_zero_or_one_and_read_only() -> None:
    purposes = [skill["purpose"] for skill in SKILLS if skill["id"] in PERSONAL]
    assert len(purposes) == len(set(purposes)) == 6
    operations = {item["id"]: item for item in operations_for_profile(load_registry(), "production")}
    assert all(set(skill["allowed_tools"]) <= set(operations) for skill in SKILLS if skill["id"] in PERSONAL)
    assert len(FIXTURES) == 12
    assert all(operations[tool]["side_effect_class"] == "none" for skill in SKILLS if skill["id"] in PERSONAL for tool in skill["allowed_tools"])
