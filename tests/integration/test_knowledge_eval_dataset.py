"""Phase 17-01: eval contracts and dataset audit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.evaluation.eval_contracts import (  # noqa: E402
    ContractError,
    DatasetManifest,
    EvalCase,
    EvalRunManifest,
    EvalTarget,
    audit_dataset,
    build_dataset_manifest,
    cases_checksum,
    compute_run_id,
    content_checksum,
    load_cases_jsonl,
)
from personal_knowledge.evaluation.run_knowledge_eval import load_config, resolve_cases_path  # noqa: E402
from personal_knowledge.evaluation.build_private_suite import HOLDOUT, OUT_DIR, SYN  # noqa: E402


def test_contract_roundtrip_eval_case() -> None:
    c = EvalCase(
        id="t1",
        split="synthetic",
        query="用户用什么 shell？",
        gold_evidence_refs=["cm|1"],
        expected_abstain=False,
        scenario="preference",
    )
    d = c.to_dict()
    c2 = EvalCase.from_dict(d)
    assert c2.id == "t1"
    assert c2.gold_evidence_refs == ["cm|1"]
    assert cases_checksum([c]) == cases_checksum([c2])


def test_contract_missing_required_fails() -> None:
    with pytest.raises(ContractError):
        EvalCase(id="", split="x", query="q")
    with pytest.raises(ContractError):
        EvalCase(id="a", split="x", query="")
    with pytest.raises(ContractError):
        EvalTarget(mode="not_a_mode")


def test_contract_checksum_changes_with_case() -> None:
    a = EvalCase(id="1", split="s", query="alpha")
    b = EvalCase(id="1", split="s", query="beta")
    assert cases_checksum([a]) != cases_checksum([b])
    assert content_checksum({"a": 1}) != content_checksum({"a": 2})


def test_dataset_manifest_and_run_manifest() -> None:
    path = (
        _ROOT
        / "assets"
        / "evals"
        / "knowledge_units"
        / "comprehensive_v1.synthetic.jsonl"
    )
    assert path.exists()
    m = build_dataset_manifest("comprehensive_v1", "v1", path)
    assert m.case_count >= 100
    assert m.checksum
    d = m.to_dict()
    m2 = DatasetManifest.from_dict(d)
    assert m2.checksum == m.checksum

    run = EvalRunManifest(
        run_id="a" * 64,
        dataset_checksum=m.checksum,
        config_checksum="b" * 64,
        scorer_version="v1",
        top_k=5,
        modes=["raw", "l1", "l2_only", "l1_l2", "hybrid"],
    )
    run.validate()
    rid = compute_run_id(m.checksum, "b" * 64, "v1", run.modes, 5)
    assert len(rid) == 64


def test_audit_synthetic_suite() -> None:
    path = (
        _ROOT
        / "assets"
        / "evals"
        / "knowledge_units"
        / "comprehensive_v1.synthetic.jsonl"
    )
    cases = load_cases_jsonl(path)
    audit = audit_dataset(cases)
    assert audit["ok"] is True
    assert audit["case_count"] == len(cases)
    scenarios = {c.scenario for c in cases}
    assert "cross_turn" in scenarios
    assert "privacy" in scenarios
    cross = [c for c in cases if c.requires_cross_turn]
    assert len(cross) >= 30


def test_contract_load_holdout_schema() -> None:
    path = (
        _ROOT
        / "assets"
        / "evals"
        / "knowledge_units"
        / "holdout_15_02.synthetic.jsonl"
    )
    cases = load_cases_jsonl(path)
    assert len(cases) >= 8
    assert all(c.query for c in cases)


def test_eval_config_tracks_relocated_private_suite_and_runtime_active() -> None:
    cfg = load_config(_ROOT / "assets" / "evals" / "knowledge_units" / "eval_v1.yaml")
    assert resolve_cases_path(cfg) == _ROOT / "var" / "runtime" / "private_evals" / "comprehensive_v1.private.jsonl"
    targets = cfg["targets"]
    assert targets.get("l1_l2_collection") is None
    assert targets.get("candidate_collection") is None
    assert SYN.exists() and HOLDOUT.exists()
    assert OUT_DIR == _ROOT / "var" / "runtime" / "private_evals"
