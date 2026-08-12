"""Validate Phase 53 preregistration and metadata-only receipts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ALLOWED = {"schema", "grounding", "tool_selection", "latency", "usage_cost", "recovery", "human_usefulness"}

ALLOWED_PREREGISTRATION_EVIDENCE_CLASSES = frozenset({"synthetic_replay", "real_authorized_paired_baseline"})

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
    if set(value["metrics"]) != ALLOWED or value["evidence_class"] not in ALLOWED_PREREGISTRATION_EVIDENCE_CLASSES: raise ValueError("metrics_or_evidence_invalid")
    return {"ok": True, "status": "frozen", "evidence_class": value["evidence_class"], "case_count": len(value["authorized_case_ids"]), "provider_calls": 0}

def check_real_receipts(path: Path) -> dict:
    value = load(path)
    if value.get("evidence_class") not in {"real_authorized", "real_authorized_paired_baseline"}:
        return {"ok": False, "status": "INCONCLUSIVE", "reason": "real_authorization_missing", "provider_calls": 0}

    reasons: list[str] = []
    status = str(value.get("status") or "INCONCLUSIVE")
    member_count = int(value.get("member_count", value.get("sample_size", 0)) or 0)
    minimum = int(value.get("minimum_evidence", 0) or 0)
    provider_calls = int(value.get("provider_calls", 0) or 0)
    max_provider_calls = int(value.get("max_provider_calls", 0) or 0)
    total_cost = float(value.get("total_spent_cost_cny", value.get("total_cost_cny", 0)) or 0)
    cost_ceiling = float(value.get("cost_ceiling_cny", value.get("cost_ceiling", 0)) or 0)
    arms = value.get("arms") if isinstance(value.get("arms"), dict) else {}
    parity = value.get("paired_parity") if isinstance(value.get("paired_parity"), dict) else {}

    if status != "PASS": reasons.append("baseline_not_pass")
    if member_count < max(2, minimum): reasons.append("sample_below_minimum")
    if not arms or set(arms) != {"personalized", "generic"}:
        reasons.append("paired_arms_missing")
    expected_calls = member_count * 2 if member_count else 0
    if expected_calls and provider_calls != expected_calls: reasons.append("provider_call_count_mismatch")
    if max_provider_calls <= 0 or provider_calls > max_provider_calls: reasons.append("provider_call_budget_exceeded")
    if cost_ceiling <= 0 or total_cost > cost_ceiling: reasons.append("cost_ceiling_exceeded")
    if not parity or any(
        (key == "silent_retry" and value is not False)
        or (key != "silent_retry" and value is not True)
        for key, value in parity.items()
    ): reasons.append("paired_parity_invalid")
    if value.get("raw_bodies_committed") is True: reasons.append("raw_bodies_committed")
    if value.get("authority_mutations", value.get("authority_mutated", 0)) not in {0, False, None}: reasons.append("authority_mutation_detected")

    for arm_name, arm in arms.items():
        if not isinstance(arm, dict):
            reasons.append(f"{arm_name}_receipt_invalid")
            continue
        if arm.get("schema_valid") is not True: reasons.append("arm_response_schema_invalid")
        if arm.get("task_state") not in {"succeeded", "completed", "direct_completed"}: reasons.append(f"{arm_name}_task_not_succeeded")
        for checksum_key in ("request_checksum", "response_checksum"):
            if not isinstance(arm.get(checksum_key), str) or len(arm[checksum_key]) != 64:
                reasons.append(f"{arm_name}_{checksum_key}_invalid")

    unique_reasons = list(dict.fromkeys(reasons))
    return {
        "ok": not unique_reasons,
        "status": "PASS" if not unique_reasons else "INCONCLUSIVE",
        "reason": unique_reasons[0] if unique_reasons else "",
        "reason_codes": unique_reasons,
        "provider_calls": provider_calls,
    }

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--check-preregistration", type=Path); parser.add_argument("--check-real-receipts", type=Path); args = parser.parse_args()
    try:
        result = validate_preregistration(args.check_preregistration) if args.check_preregistration else check_real_receipts(args.check_real_receipts)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0 if result.get("ok") else 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"ok": False, "status": "INCONCLUSIVE", "reason": str(exc), "provider_calls": 0})); return 2

if __name__ == "__main__": raise SystemExit(main())
