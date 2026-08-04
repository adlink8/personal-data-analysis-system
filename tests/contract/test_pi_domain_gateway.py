from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_domain_gateway import (
    DEFAULT_CAPABILITY,
    OPERATIONS,
    PiDomainGateway,
)


def test_registry_is_static_and_unknown_inputs_are_rejected():
    gateway = PiDomainGateway(capability=DEFAULT_CAPABILITY)
    assert set(OPERATIONS) >= {"domain.inspect", "domain.candidate", "session.preview", "session.confirm"}
    bad = gateway.invoke("module.call", {"task_id": "t"}, capability=DEFAULT_CAPABILITY)
    assert bad["ok"] is False and bad["error"]["code"] == "unknown_operation"
    extra = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b", "path": "secret"}, capability=DEFAULT_CAPABILITY)
    assert extra["error"]["code"] == "undeclared_input"


def test_capability_and_binding_fail_closed_without_domain_invocation():
    called = []
    gateway = PiDomainGateway(capability="cap", read_handler=lambda operation, params: called.append(operation))
    denied = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b"}, capability="wrong")
    assert denied["error"]["code"] == "capability_invalid" and called == []
    missing = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i"}, capability="cap")
    assert missing["error"]["code"] == "binding_required"


def test_read_operation_returns_safe_metadata_only():
    gateway = PiDomainGateway(capability="cap")
    result = gateway.invoke("domain.inspect", {"task_id": "t", "idempotency_key": "i", "binding": "b"}, capability="cap")
    assert result["ok"] is True
    assert result["data"]["task_id"] == "t"
    assert "provider" not in str(result).lower()


def test_guarded_write_requires_binding_and_routes_through_interface():
    class Stub:
        def invoke(self, operation, **params):
            return {"ok": True, "operation": operation, "data": {"sequence": 1}}

    gateway = PiDomainGateway(capability="cap", service=Stub())
    result = gateway.invoke("session.preview", {"task_id": "t", "idempotency_key": "i", "binding": "b", "session_id": "s", "transition": "generate", "payload": {}, "actor_identity_hash": "a", "expected_sequence": 1, "now": "2026-08-04T00:00:00Z"}, capability="cap")
    assert result["ok"] is True
