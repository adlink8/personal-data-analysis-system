"""Validate Phase 53 preregistration and metadata-only receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED = {"schema", "grounding", "tool_selection", "latency", "usage_cost", "recovery", "human_usefulness"}

def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict): raise ValueError("manifest_invalid")
    return value

def validate_preregistration(path: Path) -> dict:
    value = load(path)
    required = {"schema", "version", "cohort_id", "model", "route_purpose", "timeout_seconds", "max_output_tokens", "cost_ceiling", "attempts_per_arm", "authorized_case_ids", "input_checksums", "metrics", "preregistration_checksum"}
    if not required <= set(value): raise ValueError("preregistration_missing_field")
    if value["schema"] != "pi-baseline-preregistration-v1" or value["attempts_per_arm"] != 1: raise ValueError("preregistration_policy_invalid")
    if not value["authorized_case_ids"] or set(value["authorized_case_ids"]) != set(value["input_checksums"]): raise ValueError("case_checksum_mismatch")
    if set(value["metrics"]) != ALLOWED or value["evidence_class"] != "synthetic_replay": raise ValueError("metrics_or_evidence_invalid")
    return {"ok": True, "status": "frozen", "evidence_class": value["evidence_class"], "case_count": len(value["authorized_case_ids"]), "provider_calls": 0}

def check_real_receipts(path: Path) -> dict:
    value = load(path)
    if value.get("evidence_class") != "real_authorized": return {"ok": False, "status": "INCONCLUSIVE", "reason": "real_authorization_missing", "provider_calls": 0}
    return {"ok": True, "status": "PASS", "provider_calls": int(value.get("provider_calls", 0))}

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check-preregistration", type=Path); parser.add_argument("--check-real-receipts", type=Path); args = parser.parse_args()
    try:
        result = validate_preregistration(args.check_preregistration) if args.check_preregistration else check_real_receipts(args.check_real_receipts)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0 if result.get("ok") else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVE", "reason": str(exc), "provider_calls": 0})); return 2

if __name__ == "__main__": raise SystemExit(main())
