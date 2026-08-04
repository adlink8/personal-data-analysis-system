from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "ops/reports/evidence/pi-kernel-fault-matrix.json"

def test_fault_matrix_is_metadata_only_and_complete():
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    assert report["schema"] == "pi-kernel-fault-matrix-v1"
    assert report["provider_calls"] == 0
    assert report["sensitive_values_present"] is False
    assert len(report["cases"]) >= 8
    assert all(case["status"] == "PASS" for case in report["cases"])
