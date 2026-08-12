from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_knowledge.services.pi_runtime_activation import ActivationError, RuntimeActivation, validate_primary_readiness

ROOT = Path(__file__).resolve().parents[2]


def test_real_primary_readiness_remains_blocked_until_user_activation():
    result = validate_primary_readiness(ROOT / "ops/reports/evidence/pi-primary-readiness.json")
    # Phase 53 PASS + entrypoint receipts 已齐，仅剩 primary 激活未执行（需用户确认）
    assert result["ready"] is False
    assert "readiness_status_not_ready" in result["reason_codes"]
    assert "baseline_not_pass" not in result["reason_codes"]
    assert "entrypoint_receipt_inventory_mismatch" not in result["reason_codes"]


def test_primary_and_canary_cannot_prepare_from_legacy_without_new_confirmation(tmp_path: Path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    # legacy 不能直接跳 canary/primary（transition_illegal）
    with pytest.raises(ActivationError, match="transition_illegal"):
        runtime.prepare("canary", evidence_checksum="uat:synthetic")
    # shadow 升级需 evidence
    prepared = runtime.prepare("shadow", evidence_checksum="uat:synthetic")
    runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="shadow:blocked")
    # decision=proceed 后 canary 可从 shadow 升级，但需 evidence
    with pytest.raises(ActivationError, match="evidence_required"):
        runtime.prepare("canary", evidence_checksum="")
    assert runtime.current()["mode"] == "shadow"
    runtime.close()


def test_declared_failure_downgrades_exactly_and_preserves_activation_history(tmp_path: Path):
    runtime = RuntimeActivation(tmp_path / "activation.sqlite")
    prepared = runtime.prepare("shadow", evidence_checksum="uat:synthetic", cohort="phase60-fixture", stop_conditions=["kernel_failure"])
    runtime.confirm(prepared, confirmation_phrase=prepared["confirmation_phrase"], idempotency_key="shadow:fixture")
    before = runtime.current()
    downgraded = runtime.downgrade("declared_kernel_failure")
    assert before["mode"] == "shadow" and downgraded["mode"] == "legacy"
    assert downgraded["sequence"] == 2
    assert runtime.db.execute("SELECT COUNT(*) FROM activation_events").fetchone()[0] == 2
    assert runtime.pointer_path.exists()
    runtime.close()


def test_primary_evidence_report_is_honest_and_no_live_call_claimed():
    report_path = ROOT / "ops/reports/evidence/pi-capability-os-primary.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "blocked"
    assert report["mode"] == "legacy" and report["primary_activated"] is False
    assert report["provider_calls"] == 0 and report["authority_mutated"] is False
