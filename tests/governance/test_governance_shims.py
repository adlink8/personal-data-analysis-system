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
    assert len(shims) == 86
    assert all(item["target_exists"] and item["static_parity"] for item in shims)
    assert all(item["owner"] and item["consumer"] and item["remove_after"] for item in shims)


def test_retirement_cohort_is_preview_only_and_requires_human_approval() -> None:
    manifest = json.loads((ROOT / "governance" / "manifests" / "entrypoints.yaml").read_text(encoding="utf-8"))
    cohort = manifest["retirement_cohorts"][0]
    assert cohort["status"] == "pending-human-approval"
    assert "consumer count = 0" in cohort["preconditions"]
    assert "rollback manifest approved" in cohort["preconditions"]
