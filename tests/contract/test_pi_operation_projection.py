from __future__ import annotations

import personal_knowledge.services.pi_operation_projection as projection


def _operation(state="outcome_unknown"):
    return {
        "operation_id": "op:provider:1", "operation_kind": "provider", "task_id": "task:1", "session_id": "session:1", "correlation_id": "corr:1",
        "authority_class": "authority:kernel", "side_effect_class": "mutation", "snapshot_id": "snapshot:1", "state": state, "version": 2, "attempt": 1,
        "budget": {"token_limit": 100, "cost_limit": 0, "timeout_ms": 1000, "token_used": 10, "cost_used": 0}, "receipt_refs": [], "fingerprint_refs": [],
        "recovery_actions": ["reconcile", "resume"], "reason": "provider_timeout", "created_at": "2026-08-05T00:00:00Z", "updated_at": "2026-08-05T00:00:00Z",
    }


def test_operation_projection_is_metadata_only():
    projected = projection.safe_operation({**_operation(), "prompt": "must not cross"})
    assert projected["schema_version"] == projection.PI_OPERATION_PROJECTION_SCHEMA
    assert projected["state"] == "outcome_unknown"
    assert all(key not in projected for key in ("prompt", "content", "credential", "path"))


def test_operation_list_and_guarded_mutation_use_kernel_only(monkeypatch):
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "GET":
            return 200, {"ok": True, "operations": [_operation()]}
        return 200, {"ok": True, "operation": {**_operation(), "state": "manual_review", "version": 3}, "action": "reconcile", "retry_allowed": False, "reconciled_before_retry": True}

    monkeypatch.setattr(projection, "_request_json", fake_request)
    listing = projection.operation_list()
    assert listing["state"] == "ready" and listing["operations"][0]["operation_kind"] == "provider"
    result = projection.mutate_operation("reconcile", {"operation_id": "op:provider:1", "expected_version": 2, "idempotency_key": "ui:1", "receipt_refs": [], "fingerprint_refs": []})
    assert result["ok"] is True and result["reconciled_before_retry"] is True
    assert calls[1][1] == "/v1/operations/op:provider:1/reconcile"
    assert "prompt" not in calls[1][2] and "credential" not in calls[1][2]


def test_offline_and_stale_commands_are_truthful(monkeypatch):
    monkeypatch.setattr(projection, "_request_json", lambda *args, **kwargs: (0, {}))
    assert projection.operation_list()["state"] == "offline"
    result = projection.mutate_operation("cancel", {"operation_id": "op:1", "expected_version": 1, "idempotency_key": "ui:offline"})
    assert result["error"]["code"] == "kernel_offline"
    assert projection.mutate_operation("cancel", {"operation_id": "", "expected_version": 1, "idempotency_key": "ui:bad"})["error"]["code"] == "operation_identity_required"
