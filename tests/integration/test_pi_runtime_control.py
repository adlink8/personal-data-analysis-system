from __future__ import annotations

from personal_knowledge.services.pi_operation_projection import safe_operation


def _op(state="outcome_unknown"):
    return {"operation_id": "op:authority:1", "operation_kind": "authority_transaction", "task_id": "task:1", "session_id": "session:1", "correlation_id": "corr:1", "authority_class": "authority:python", "side_effect_class": "mutation", "snapshot_id": "snapshot:1", "state": state, "version": 2, "attempt": 1, "budget": {}, "receipt_refs": [], "fingerprint_refs": [], "recovery_actions": ["reconcile", "compensate"], "reason": "authority_timeout", "created_at": "2026-08-05T00:00:00Z", "updated_at": "2026-08-05T00:00:00Z"}


def test_cross_plane_failure_is_visible_and_not_retryable_without_receipts():
    projected = safe_operation(_op())
    assert projected["operation_kind"] == "authority_transaction"
    assert projected["state"] == "outcome_unknown"
    assert "reconcile" in projected["allowed_actions"]
    assert projected["receipt_refs"] == [] and projected["fingerprint_refs"] == []


def test_each_failure_plane_keeps_single_kernel_metadata_contract():
    for kind in ("kernel_task", "kernel_session", "kernel_skill", "domain_tool", "provider", "authority_transaction"):
        projected = safe_operation({**_op("manual_review"), "operation_kind": kind})
        assert projected["schema_version"] == "pi_operation_projection_v1"
        assert projected["operation_kind"] == kind
        assert "prompt" not in projected and "path" not in projected
