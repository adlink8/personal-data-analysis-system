from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "governance/manifests/ai/pi-baseline-preregistration.json"

def test_frozen_preregistration_validates_before_any_call():
    result = subprocess.run([sys.executable, "tools/supported/evaluate_pi_kernel.py", "--check-preregistration", str(MANIFEST)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    payload = json.loads(result.stdout); assert payload["status"] == "frozen" and payload["provider_calls"] == 0

def test_synthetic_replay_cannot_complete_real_baseline():
    report = {"evidence_class": "synthetic_replay", "provider_calls": 0}
    path = ROOT / "ops/reports/evidence/pi-legacy-real-baseline.json"
    assert report["evidence_class"] != "real_authorized"
    assert not path.exists() or json.loads(path.read_text(encoding="utf-8")).get("status") in {"blocked", "INCONCLUSIVE"}
