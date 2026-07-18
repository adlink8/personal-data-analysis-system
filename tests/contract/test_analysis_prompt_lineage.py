from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import shutil

from personal_knowledge.intelligence.analysis.inputs import (
    BEGIN_EVIDENCE, END_EVIDENCE, ConfirmationEvent, build_confirmed_input,
)
from personal_knowledge.intelligence.analysis.schema import EvidenceReference, checksum
from personal_knowledge.intelligence.decision.context_binding import DecisionContextBinding, DecisionContextPolicy


ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "assets/prompts/decision_analysis_v1.txt"
SCHEMA = ROOT / "src/personal_knowledge/intelligence/analysis/schema.py"
POLICY = ROOT / "governance/policies/decision_analysis.yaml"


def _binding() -> DecisionContextBinding:
    draft = DecisionContextBinding(
        "p1", "1" * 64, "e1", "2" * 64,
        DecisionContextPolicy("global", 3600), "2026-07-18T09:00:00Z", "",
    )
    return replace(draft, binding_hash=checksum(draft.core()))


def _build(monkeypatch, **paths):
    binding = _binding()
    monkeypatch.setattr(
        "personal_knowledge.intelligence.analysis.inputs.validate_decision_context_binding",
        lambda value, personal, external, now=None: {"binding": binding.to_dict()},
    )
    refs = (
        EvidenceReference("a.personal_change", "change", "pc1", "3" * 64, "p1", "1" * 64),
        EvidenceReference("s.external_fact", "fact", "ef1", "4" * 64, "e1", "2" * 64),
    )
    return build_confirmed_input(
        binding=binding, personal_db_path="unused-personal", external_db_path="unused-external",
        goal="Choose a release approach", constraints=("finish this week",),
        weights={"reliability": .6, "speed": .4}, risk_budget="low",
        confirmation=ConfirmationEvent("confirm-1", "2026-07-18T09:01:00Z", True),
        personal_evidence=(refs[0],), external_evidence=(refs[1],), **paths,
    )


def test_prompt_delimits_untrusted_evidence_and_binds_all_lineage(monkeypatch) -> None:
    request = _build(monkeypatch)
    assert request.rendered_prompt.count(BEGIN_EVIDENCE) == 1
    assert request.rendered_prompt.count(END_EVIDENCE) == 1
    assert request.rendered_prompt.index(BEGIN_EVIDENCE) < request.rendered_prompt.index(END_EVIDENCE)
    assert request.request_manifest["prompt_checksum"] == request.prompt_checksum
    assert request.request_manifest["schema_checksum"] == request.schema_checksum
    assert request.request_manifest["policy_checksum"] == request.policy_checksum
    assert request.request_manifest["binding_hash"] == _binding().binding_hash


def test_prompt_schema_or_policy_drift_changes_request_identity(tmp_path: Path, monkeypatch) -> None:
    baseline = _build(monkeypatch)
    prompt, schema, policy = tmp_path / "prompt.txt", tmp_path / "schema.py", tmp_path / "policy.yaml"
    shutil.copyfile(PROMPT, prompt); shutil.copyfile(SCHEMA, schema); shutil.copyfile(POLICY, policy)
    prompt.write_text(prompt.read_text(encoding="utf-8") + "\nBounded output only.\n", encoding="utf-8")
    changed_prompt = _build(monkeypatch, prompt_path=prompt, schema_path=schema, policy_path=policy)
    schema.write_text(schema.read_text(encoding="utf-8") + "\n# lineage change\n", encoding="utf-8")
    changed_schema = _build(monkeypatch, prompt_path=prompt, schema_path=schema, policy_path=policy)
    policy.write_text(policy.read_text(encoding="utf-8").replace("max_candidates: 8", "max_candidates: 7"), encoding="utf-8")
    changed_policy = _build(monkeypatch, prompt_path=prompt, schema_path=schema, policy_path=policy)
    assert len({baseline.request_checksum, changed_prompt.request_checksum,
                changed_schema.request_checksum, changed_policy.request_checksum}) == 4

