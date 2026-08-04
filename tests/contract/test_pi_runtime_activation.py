from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import json

from personal_knowledge.services.pi_runtime_activation import ActivationError, RuntimeActivation, validate_primary_readiness


def test_fresh_runtime_defaults_to_legacy_and_requires_exact_confirmation(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    assert runtime.current()["mode"] == "legacy"
    prepared = runtime.prepare("shadow", evidence_checksum="synthetic-evidence")
    try:
        runtime.confirm(prepared, confirmation_phrase="wrong", idempotency_key="i1")
    except ActivationError as exc:
        assert exc.code == "confirmation_mismatch"
    else: raise AssertionError("upgrade without exact confirmation")
    state = runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="i1")
    assert state["mode"] == "shadow"; runtime.close()


def test_downgrade_preserves_append_only_history(tmp_path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    p = runtime.prepare("shadow", evidence_checksum="e"); runtime.confirm(p, confirmation_phrase=p["confirmation_phrase"], idempotency_key="i1")
    state = runtime.downgrade("kernel_failed")
    assert state["mode"] == "legacy" and state["sequence"] == 2
    assert runtime.db.execute("SELECT COUNT(*) FROM activation_events").fetchone()[0] == 2; runtime.close()


def test_primary_readiness_requires_complete_evidence_bundle(tmp_path, monkeypatch):
    inventory = tmp_path / "inventory.json"
    baseline = tmp_path / "baseline.json"
    fault_matrix = tmp_path / "fault.json"
    browser_uat = tmp_path / "browser.json"
    readiness = tmp_path / "readiness.json"
    inventory.write_text(json.dumps({"entrypoints": [{"id": "entrypoint_a", "status": "migrated", "target_route": "pi_kernel_task"}]}), encoding="utf-8")
    baseline.write_text(json.dumps({"status": "PASS", "evidence_class": "real_authorized_paired_baseline", "member_count": 2, "provider_calls": 4, "raw_bodies_committed": False, "authority_mutations": 0, "paired_parity": {"same_frozen_protocol": True, "same_model": True, "same_purpose": True, "one_call_per_arm": True, "silent_retry": False}, "arms": {"personalized": {"schema_valid": True, "task_state": "succeeded"}, "generic": {"schema_valid": True, "task_state": "direct_completed"}}}), encoding="utf-8")
    fault_matrix.write_text(json.dumps({"evidence_class": "synthetic_replay", "provider_calls": 0, "cases": [{"status": "PASS"}]}), encoding="utf-8")
    browser_uat.write_text(json.dumps({"human_acceptance_signed": True, "privacy_boundary": "PASS_NO_PROMPT_OR_PROVIDER_BODY", "authority_mutations": 0, "real_personal_cohort_accessed": True}), encoding="utf-8")
    readiness.write_text(json.dumps({"schema": "pi-primary-readiness-v1", "status": "READY", "authority_mutations": 0, "raw_bodies_committed": False, "entrypoint_receipts": {"entrypoint_a": {"provider": "pi-kernel", "receipt_count": 1, "legacy_receipt_count": 0}}}), encoding="utf-8")

    result = validate_primary_readiness(readiness, inventory_path=inventory, baseline_path=baseline, fault_matrix_path=fault_matrix, browser_uat_path=browser_uat)
    assert result["ready"] is True
    assert result["production_entrypoint_count"] == 1

    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"phase53_decision": "proceed"}), encoding="utf-8")
    monkeypatch.setattr("personal_knowledge.services.pi_runtime_activation.validate_primary_readiness", lambda _path: result)
    runtime = RuntimeActivation(tmp_path / "primary.sqlite", policy_path=policy)
    for mode, key in (("shadow", "shadow"), ("canary", "canary")):
        prepared = runtime.prepare(mode, evidence_checksum=key)
        runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key=key)
    prepared = runtime.prepare("primary", evidence_checksum="baseline", readiness=True, readiness_evidence_path=readiness)
    assert prepared["preview"]["readiness_checksum"] == result["readiness_checksum"]
    runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="primary")
    assert runtime.current()["mode"] == "primary"
    runtime.close()

    readiness.write_text(json.dumps({"schema": "pi-primary-readiness-v1", "status": "READY", "entrypoint_receipts": {}}), encoding="utf-8")
    result = validate_primary_readiness(readiness, inventory_path=inventory, baseline_path=baseline, fault_matrix_path=fault_matrix, browser_uat_path=browser_uat)
    assert result["ready"] is False
    assert "entrypoint_receipt_inventory_mismatch" in result["reason_codes"]
