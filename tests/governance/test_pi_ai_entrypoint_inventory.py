from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_inventory_is_complete_and_classified():
    manifest = json.loads((ROOT / "governance/manifests/ai/pi-ai-entrypoints.json").read_text(encoding="utf-8"))
    rows = manifest["entrypoints"]
    assert rows
    assert all(row["status"] in {"migrated", "deterministic_non_ai", "test_only", "rollback_only", "archived"} for row in rows)
    assert all(row["file"] and (ROOT / row["file"]).is_file() for row in rows)
    assert manifest["policy"]["normal_mode_controller"] == "pi_kernel"
    assert manifest["policy"]["legacy_mode"] == "rollback_only"


def test_no_real_provider_activation_is_claimed_by_phase_51_inventory():
    manifest = json.loads((ROOT / "governance/manifests/ai/pi-ai-entrypoints.json").read_text(encoding="utf-8"))
    assert manifest["policy"]["provider_calls"] == 0
    assert not any(row["status"] == "migrated" and "Codex" in row["id"] for row in manifest["entrypoints"])
