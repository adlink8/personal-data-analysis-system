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


def test_real_receipt_validator_rejects_incomplete_paired_report(tmp_path: Path):
    report = {
        "evidence_class": "real_authorized_paired_baseline",
        "status": "INCONCLUSIVE",
        "member_count": 1,
        "minimum_evidence": 2,
        "provider_calls": 2,
        "max_provider_calls": 2,
        "total_spent_cost_cny": 0.1,
        "cost_ceiling_cny": 30,
        "paired_parity": {"same_model": True, "one_call_per_arm": True},
        "arms": {
            "personalized": {"schema_valid": False, "task_state": "succeeded", "request_checksum": "a" * 64, "response_checksum": "b" * 64},
            "generic": {"schema_valid": False, "task_state": "succeeded", "request_checksum": "c" * 64, "response_checksum": "d" * 64},
        },
    }
    path = tmp_path / "real.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/supported/evaluate_pi_kernel.py", "--check-real-receipts", str(path)],
        cwd=ROOT, capture_output=True, text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["status"] == "INCONCLUSIVE"
    assert {"sample_below_minimum", "arm_response_schema_invalid"} <= set(payload["reason_codes"])
