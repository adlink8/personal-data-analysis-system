"""Phase 17-04: promotion gate fail-closed + full entrypoint smoke."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.evaluation.gate_knowledge_candidate import evaluate_gate  # noqa: E402
from personal_knowledge.evaluation.run_knowledge_eval import run_eval  # noqa: E402


POLICY = {
    "version": "v1",
    "require_answer_eval": True,
    "required_modes": ["raw", "l1", "l1_l2", "hybrid"],
    "hard_gates": {},
    "quality_gates": {
        "ku_vs_raw_recall5_pp": {"min_delta_pp": 10},
        "frozen_regression_pp": {"max_drop_pp": 2},
    },
}


def _summary_base(**kwargs):
    s = {
        "modes": {
            "raw": {"aggregate": {"recall_at": {"5": 0.5}, "privacy_hit": 0, "secret_hit": 0}},
            "l1": {"aggregate": {"recall_at": {"5": 0.65}, "privacy_hit": 0, "secret_hit": 0}},
            "l1_l2": {"aggregate": {"recall_at": {"5": 0.60}, "privacy_hit": 0, "secret_hit": 0}},
            "hybrid": {"aggregate": {"recall_at": {"5": 1.0}, "privacy_hit": 0, "secret_hit": 0}},
        },
        "comparisons": {
            "l1_l2": {
                "delta": 0.10,
                "bootstrap": {"ci_low": 0.01, "insufficient_evidence": False},
            }
        },
        "answer": {"modes": {"l1_l2": {"aggregate": {"citation_precision": 1.0}}}},
        "candidate_collection": "cand_a",
        "candidate_checksum": "ck1",
    }
    s.update(kwargs)
    return s


def test_policy_versioned_gates() -> None:
    g = evaluate_gate(_summary_base(), POLICY, require_answer=True)
    assert "policy_version" in g
    assert g["active_collection_before"] == g["active_collection_after"]
    assert "checks" in g and g["checks"]


def test_fail_closed_missing_answer_and_privacy() -> None:
    s = _summary_base(answer={"skipped": True})
    g = evaluate_gate(s, POLICY, require_answer=True)
    assert g["passed"] is False
    assert g["verdict"] == "FAIL"

    s2 = _summary_base()
    s2["modes"]["l1"]["aggregate"]["privacy_hit"] = 1
    g2 = evaluate_gate(s2, POLICY, require_answer=True)
    assert g2["passed"] is False
    assert any("privacy" in r.lower() or "secret" in r.lower() for r in g2["reasons"])


def test_fail_closed_checksum_mismatch() -> None:
    g = evaluate_gate(
        _summary_base(),
        POLICY,
        candidate_collection="cand_a",
        candidate_checksum="OTHER",
        require_answer=True,
    )
    assert g["passed"] is False
    assert any("checksum" in r for r in g["reasons"])


def test_quality_pure_ku_regression_not_masked_by_hybrid() -> None:
    """L1+L2 pure-KU -5pp vs L1 must fail even if hybrid is 1.0."""
    s = _summary_base()
    # l1 0.65, l1_l2 0.60 → 5pp drop > 2pp
    g = evaluate_gate(s, POLICY, require_answer=True)
    assert g["passed"] is False
    assert any("regression" in r.lower() or "pure-ku" in r.lower() or "drop" in r.lower() for r in g["reasons"])
    # hybrid high must not flip to PASS
    assert s["modes"]["hybrid"]["aggregate"]["recall_at"]["5"] == 1.0


def test_full_entrypoint_offline_dry_run(tmp_path: Path) -> None:
    cfg = (
        _ROOT
        / "assets"
        / "evals"
        / "knowledge_units"
        / "eval_v1.yaml"
    )
    if not cfg.exists():
        pytest.skip("eval_v1.yaml missing")
    from personal_knowledge.domains.knowledge.promote_knowledge_index import read_active

    before = read_active()
    summary = run_eval(
        cfg,
        full=True,
        render=True,
        gate=True,
        dry_run=True,
        offline=True,
        out_dir=tmp_path / "run",
    )
    after = read_active()
    assert before == after
    assert summary.get("active_unchanged") is True
    assert (tmp_path / "run" / "summary.json").exists()
    # missing candidate / structural gate may FAIL — non-zero path tested via gate verdict
    assert "run_id" in summary


def test_full_policy_fails_closed_on_unimplemented_human_and_quality_evidence() -> None:
    policy_path = _ROOT / "assets" / "evals" / "knowledge_units" / "eval_policy_v1.yaml"
    from personal_knowledge.evaluation.gate_knowledge_candidate import load_policy

    s = _summary_base()
    for payload in s["modes"].values():
        payload["aggregate"].update(
            {"no_answer_fp_rate": 0.0, "mrr_at_5": 0.6, "p95_latency_ms": 10.0}
        )
    s["comparisons"]["l1_l2"]["bootstrap_mrr"] = {
        "ci_low": 0.0,
        "insufficient_evidence": False,
    }
    s["scenario_comparisons"] = {
        "cross_turn_l1_baseline": {
            "l1_l2": {
                "delta": 0.2,
                "bootstrap": {"n": 30, "ci_low": 0.01},
            }
        }
    }
    s["stage_details"] = {
        "lineage": {
            "ok": True,
            "l2_member_links": 815,
            "discrepancy": {"total_l2_status_current": 815},
        },
        "extraction_quality": {"metrics": {"human": []}},
    }
    for mode in ("raw", "l1", "l1_l2", "hybrid"):
        s["answer"]["modes"][mode] = {
            "aggregate": {"citation_precision": 1.0}
        }

    gate = evaluate_gate(s, load_policy(policy_path), require_answer=True)
    assert gate["passed"] is False
    assert any("grounded L2 human precision" in reason for reason in gate["reasons"])
    names = {check["name"] for check in gate["checks"]}
    assert "reconcile_integrity" in names
    assert "mrr_at_5_non_inferior" in names
    assert "cross_turn_l2_vs_l1" in names
    assert "p95_latency_vs_l1_baseline" in names
