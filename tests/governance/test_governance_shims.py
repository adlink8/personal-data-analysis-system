from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _checker():
    path = ROOT / "integration" / "scripts" / "governance" / "check_shim_budget.py"
    spec = importlib.util.spec_from_file_location("shim_budget_checker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_all_legacy_shims_resolve_to_existing_static_targets() -> None:
    shims = _checker().discover_shims()
    # Live shim inventory after Phase 20–21 retirements (was 86 pre-cleanup).
    assert len(shims) == 85
    assert all(item["target_exists"] and item["static_parity"] for item in shims)
    assert all(item["owner"] and item["consumer"] and item["remove_after"] for item in shims)


def test_retirement_cohort_is_preview_only_and_requires_human_approval() -> None:
    manifest = json.loads((ROOT / "governance" / "manifests" / "entrypoints.yaml").read_text(encoding="utf-8"))
    cohort = manifest["retirement_cohorts"][0]
    assert cohort["status"] == "pending-human-approval"
    assert "consumer count = 0" in cohort["preconditions"]
    assert "rollback manifest approved" in cohort["preconditions"]


def test_baseline_only_down_accepts_reduced_surface_and_rejects_growth() -> None:
    checker = _checker()
    assert checker._baseline_errors(85, 86, "shim", only_down=True) == []
    assert checker._baseline_errors(87, 86, "shim", only_down=True) == [
        "shim budget increased: expected at most 86, found 87"
    ]
    assert checker._baseline_errors(85, 86, "shim", only_down=False) == [
        "shim baseline drift: expected 86, found 85"
    ]
