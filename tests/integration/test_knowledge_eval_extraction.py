"""Phase 17-01: L2 lineage reconcile + extraction quality."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.evaluation.extraction_quality_eval import (  # noqa: E402
    Metric,
    _has_privacy_leak,
    evaluate_extraction,
)
from personal_knowledge.evaluation.reconcile_l2_lineage import reconcile  # noqa: E402


def test_privacy_patterns() -> None:
    assert _has_privacy_leak("api_key=sk-xxx") is True
    assert _has_privacy_leak("用户喜欢 powershell") is False


def test_metric_structure() -> None:
    m = Metric("x", 3, 10, 0.3, ["a"])
    d = m.to_dict()
    assert d["numerator"] == 3
    assert d["denominator"] == 10


def test_reconcile_l2_lineage_live_or_skip() -> None:
    from personal_knowledge.core.project_paths import UNIFIED_DB

    if not UNIFIED_DB.exists():
        pytest.skip("no unified db")
    report = reconcile(UNIFIED_DB)
    assert report.get("db_unchanged") is True
    d = report.get("discrepancy") or {}
    # 768 full + 47 pilot = 815
    if d.get("full_run_units") and d.get("pilot_run_units"):
        assert d["sum_run_units"] == d["full_run_units"] + d["pilot_run_units"]
        assert d["total_l2_status_current"] == d["sum_run_units"]
        assert report.get("ok") is True
    assert "explanation" in d
    assert report.get("terminal_failure_count", 0) >= 0


def test_extraction_quality_has_denominators() -> None:
    from personal_knowledge.core.project_paths import UNIFIED_DB

    if not UNIFIED_DB.exists():
        pytest.skip("no unified db")
    report = evaluate_extraction(UNIFIED_DB, sample_limit=20)
    assert "metrics" in report
    l2 = report["metrics"]["l2"]
    for key in ("evidence_coverage", "schema_completeness", "duplication_rate"):
        m = l2[key]
        assert "numerator" in m and "denominator" in m
        assert "sample_ids" in m
    assert "privacy" in report["metrics"]
