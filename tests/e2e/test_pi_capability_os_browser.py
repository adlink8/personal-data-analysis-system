from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / "apps/personal_decision_cockpit"


def test_cockpit_operation_status_browser_contract():
    result = subprocess.run(
        ["npm.cmd" if os.name == "nt" else "npm", "test", "--", "--run", "PiOperationStatus"],
        cwd=APP,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "1 passed" in result.stdout


def test_browser_uat_is_metadata_only_and_truthful():
    evidence = json.loads((ROOT / "ops/reports/evidence/pi-capability-os-uat.json").read_text(encoding="utf-8"))
    source = (APP / "src/pages/system/SystemPage.tsx").read_text(encoding="utf-8")
    assert evidence["primary_activated"] is False
    assert evidence["provider_calls"] == 0
    assert "Kernel 操作控制面" in source
    assert "prompt" not in source and "credential" not in source and "response body" not in source
