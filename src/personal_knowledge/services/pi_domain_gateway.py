"""Typed, loopback-only bridge from Pi tools to the existing Python authority."""
from __future__ import annotations

import hmac
import os
from typing import Any, Mapping

from personal_knowledge.services.orchestration_service import GuardedOrchestrationInterface

PI_DOMAIN_GATEWAY_SCHEMA = "pi_domain_gateway_v1"
PI_DOMAIN_CAPABILITY_HEADER = "X-PI-Domain-Capability"
DEFAULT_CAPABILITY = "pi-domain-local-capability-v1"

OPERATIONS: dict[str, dict[str, Any]] = {
    "domain.inspect": {"kind": "read", "allowed": {"task_id", "idempotency_key", "binding"}, "privacy": "R1"},
    "domain.candidate": {"kind": "read", "allowed": {"task_id", "idempotency_key", "binding", "evidence_refs", "proposal"}, "privacy": "R1"},
    "session.preview": {"kind": "guarded_write", "allowed": {"session_id", "transition", "payload", "actor_identity_hash", "expected_sequence", "now", "task_id", "idempotency_key", "binding"}, "privacy": "R1"},
    "session.confirm": {"kind": "guarded_write", "allowed": {"preview", "confirmation_token", "confirmed", "idempotency_key", "now", "task_id", "binding"}, "privacy": "R1"},
}

class PiDomainGatewayError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail

def _error(operation: str, code: str) -> dict[str, Any]:
    return {"schema_version": PI_DOMAIN_GATEWAY_SCHEMA, "operation": operation, "ok": False, "status": "error", "error": {"code": code}}

def _ok(operation: str, data: Any) -> dict[str, Any]:
    return {"schema_version": PI_DOMAIN_GATEWAY_SCHEMA, "operation": operation, "ok": True, "status": "success", "data": data}

class PiDomainGateway:
    def __init__(self, *, service: GuardedOrchestrationInterface | None = None, capability: str | None = None, read_handler=None) -> None:
        self.service = service
        self.capability = capability or os.environ.get("PI_DOMAIN_CAPABILITY", DEFAULT_CAPABILITY)
        self.read_handler = read_handler

    def _check(self, operation: str, params: Mapping[str, Any], capability: str | None) -> None:
        spec = OPERATIONS.get(operation)
        if spec is None:
            raise PiDomainGatewayError("unknown_operation")
        if capability is None or not hmac.compare_digest(str(capability), str(self.capability)):
            raise PiDomainGatewayError("capability_invalid")
        if not isinstance(params, Mapping) or set(params) - spec["allowed"]:
            raise PiDomainGatewayError("undeclared_input")
        if operation.startswith("domain.") and not params.get("task_id"):
            raise PiDomainGatewayError("task_id_required")
        if not params.get("idempotency_key"):
            raise PiDomainGatewayError("idempotency_key_required")
        if not params.get("binding"):
            raise PiDomainGatewayError("binding_required")

    def invoke(self, operation: str, params: Mapping[str, Any] | None = None, *, capability: str | None = None) -> dict[str, Any]:
        params = dict(params or {})
        try:
            self._check(operation, params, capability)
            spec = OPERATIONS[operation]
            if spec["kind"] == "read":
                if self.read_handler is not None:
                    return _ok(operation, self.read_handler(operation, params))
                return _ok(operation, {"status": "synthetic", "operation": operation, "task_id": params["task_id"], "evidence_refs": params.get("evidence_refs", [])})
            target = self.service or GuardedOrchestrationInterface()
            # Only the existing guarded interface receives writes; no dynamic callable names enter it.
            routed = {key: value for key, value in params.items() if key not in {"task_id", "binding", "idempotency_key"}}
            result = target.invoke(operation, **routed)
            return _ok(operation, result)
        except PiDomainGatewayError as exc:
            return _error(operation, exc.code)
        except Exception as exc:  # transport-safe envelope; detail stays local
            code = str(getattr(exc, "code", "") or "domain_unavailable").split(":", 1)[0]
            return _error(operation, code if code in {"missing_parameter", "explicit_confirmation_required", "confirmation_expired", "preview_checksum_mismatch", "invalid_request"} else "domain_unavailable")

def invoke_pi_domain(operation: str, params: Mapping[str, Any] | None = None, *, capability: str | None = None, service=None) -> dict[str, Any]:
    return PiDomainGateway(service=service).invoke(operation, params, capability=capability)

__all__ = ["OPERATIONS", "PI_DOMAIN_GATEWAY_SCHEMA", "PI_DOMAIN_CAPABILITY_HEADER", "PiDomainGateway", "PiDomainGatewayError", "invoke_pi_domain"]
