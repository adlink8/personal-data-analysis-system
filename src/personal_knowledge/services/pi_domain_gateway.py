"""Typed, loopback-only bridge from Pi tools to the existing Python authority."""
from __future__ import annotations

import hmac
import os
from typing import Any, Mapping

from personal_knowledge.services.capability_registry import load_registry, operations_for_profile
from personal_knowledge.services.evidence_sqlite_tool import (
    EVIDENCE_SQLITE_OPERATION,
    LEASE_SKILL_ID,
    PRIVACY_CEILING,
    EvidenceSqliteTool,
    knowledge_research_checksum,
)
from personal_knowledge.services.orchestration_service import GuardedOrchestrationInterface
from personal_knowledge.services.warehouse_mutations import MUTATION_OPERATIONS, WarehouseOperationLedger
from personal_knowledge.services.warehouse_tools import OPERATIONS as WAREHOUSE_READ_OPERATIONS, WarehouseTools
from personal_knowledge.services.semantic_maintenance_tools import OPERATIONS as SEMANTIC_OPERATIONS, SemanticMaintenanceTools
from personal_knowledge.services.retrieval_maintenance_tools import OPERATIONS as RETRIEVAL_OPERATIONS, RetrievalMaintenanceTools
from personal_knowledge.services.snapshot_release_tools import OPERATIONS as SNAPSHOT_OPERATIONS, SnapshotReleaseTools

PI_DOMAIN_GATEWAY_SCHEMA = "pi_domain_gateway_v1"
PI_DOMAIN_CAPABILITY_HEADER = "X-PI-Domain-Capability"
DEFAULT_CAPABILITY = "pi-domain-local-capability-v1"

# Python-owned canonical conversation navigation: schema-bound read-only
# providers (Plan 61-05). They expose only safe scope/history metadata, never
# canonical bodies; they are read-only by construction and carry no
# canonical/promotion operation.
CONVERSATION_READ_OPERATIONS: dict[str, dict[str, Any]] = {
    "conversation.thread.last": {
        "kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding", "limit"},
        "privacy": "R1",
    },
    "conversation.thread.recent": {
        "kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding", "limit", "cursor"},
        "privacy": "R1",
    },
    "conversation.thread.select": {
        "kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding", "conversation_id", "limit", "after"},
        "privacy": "R1",
    },
    "conversation.project_scopes.list": {
        "kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding"},
        "privacy": "R1",
    },
    "conversation.project_scope.select": {
        "kind": "read",
        "allowed": {"task_id", "idempotency_key", "binding", "project_scope_id", "limit", "after"},
        "privacy": "R1",
    },
}

OPERATIONS: dict[str, dict[str, Any]] = {
    "domain.inspect": {"kind": "read", "allowed": {"task_id", "idempotency_key", "binding"}, "privacy": "R1"},
    "domain.candidate": {"kind": "read", "allowed": {"task_id", "idempotency_key", "binding", "evidence_refs", "proposal"}, "privacy": "R1"},
    "session.preview": {"kind": "guarded_write", "allowed": {"session_id", "transition", "payload", "actor_identity_hash", "expected_sequence", "now", "task_id", "idempotency_key", "binding"}, "privacy": "R1"},
    "session.confirm": {"kind": "guarded_write", "allowed": {"preview", "confirmation_token", "confirmed", "idempotency_key", "now", "task_id", "binding"}, "privacy": "R1"},
    "evidence.sqlite_query": {
        "kind": "read",
        "allowed": {
            "task_id", "idempotency_key", "binding", "database_id", "query_id",
            "version", "parameters", "scope", "skill_id", "supporting_skills",
            "manifest_checksum", "privacy_ceiling",
        },
        "privacy": "R1",
        "checksum": "b06b0d5ce4f762515082aebc296bd804ff18ff6875d7af552f0aa936f163227e",
    },
    **CONVERSATION_READ_OPERATIONS,
}

PROJECT_OPERATIONS: dict[str, dict[str, Any]] = {
    operation["id"]: {
        "kind": "read" if operation["side_effect_class"] == "none" else "guarded_write",
        "allowed": (
            {"task_id", "idempotency_key", "binding", "authority_id", "limit", "cursor", "start_date", "end_date", "filters", "snapshot_id", "watermark_id"}
            if operation["id"] in WAREHOUSE_READ_OPERATIONS else
            {"task_id", "idempotency_key", "binding", "source_scope", "snapshot_checksum", "watermark_checksum", "batch_limit", "extractor", "model_receipt", "schema_version", "evidence_refs", "records", "actor", "profile", "now", "preview", "confirmed"}
            if operation["id"] in SEMANTIC_OPERATIONS else
            {"task_id", "idempotency_key", "binding", "semantic_snapshot_checksum", "source_ids", "embedding_receipt", "index_schema_version", "actor", "profile", "now", "preview"}
            if operation["id"] == "index.build" else
            {"task_id", "idempotency_key", "binding", "generation_id", "expected_ids", "indexed_ids"}
            if operation["id"] == "index.reconcile" else
            {"task_id", "idempotency_key", "binding", "generation_id", "policy_id", "policy_checksum", "reconcile"}
            if operation["id"] == "index.evaluate" else
            {"task_id", "idempotency_key", "binding", "action", "snapshot_id", "generation_id", "manifest", "reconcile", "eval_passed", "eval_checksum", "current_pointer", "target_pointer", "protected_fingerprint", "actor", "profile", "now", "preview", "confirmed", "fault"}
            if operation["id"] in SNAPSHOT_OPERATIONS else
            {"task_id", "idempotency_key", "binding", "authority_id", "source_checksum", "snapshot_checksum", "watermark_checksum", "count", "actor", "profile", "before_fingerprint", "preview", "confirmed", "now", "crash_at", "operation_id"}
            if operation["id"] in MUTATION_OPERATIONS else
            {"task_id", "idempotency_key", "binding", "query", "record_id", "limit", "cursor", "snapshot_id", "source_id"}
        ),
        "privacy": operation["privacy_ceiling"],
        "checksum": operation["checksum"],
        "authority": operation["authority_class"],
    }
    for operation in operations_for_profile(load_registry(), "production")
}
PROJECT_ALIASES = {
    alias["name"]: operation["id"]
    for operation in operations_for_profile(load_registry(), "production")
    for alias in operation.get("aliases", [])
}


def canonical_project_operation(operation: str) -> str:
    return PROJECT_ALIASES.get(operation, operation)

class PiDomainGatewayError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail

def _error(operation: str, code: str) -> dict[str, Any]:
    return {"schema_version": PI_DOMAIN_GATEWAY_SCHEMA, "operation": operation, "ok": False, "status": "error", "error": {"code": code}}

def _ok(operation: str, data: Any) -> dict[str, Any]:
    return {"schema_version": PI_DOMAIN_GATEWAY_SCHEMA, "operation": operation, "ok": True, "status": "success", "data": data}

class PiDomainGateway:
    def __init__(self, *, service: GuardedOrchestrationInterface | None = None, capability: str | None = None,
                 read_handler=None, warehouse_tools: WarehouseTools | None = None,
                 warehouse_ledger: WarehouseOperationLedger | None = None,
                 semantic_tools: SemanticMaintenanceTools | None = None,
                 retrieval_tools: RetrievalMaintenanceTools | None = None,
                 snapshot_tools: SnapshotReleaseTools | None = None,
                 evidence_tool: EvidenceSqliteTool | None = None) -> None:
        self.service = service
        self.capability = capability or os.environ.get("PI_DOMAIN_CAPABILITY", DEFAULT_CAPABILITY)
        self.read_handler = read_handler
        self.warehouse_tools = warehouse_tools
        self.warehouse_ledger = warehouse_ledger
        self.semantic_tools = semantic_tools
        self.retrieval_tools = retrieval_tools
        self.snapshot_tools = snapshot_tools
        self.evidence_tool = evidence_tool

    def _check(self, operation: str, params: Mapping[str, Any], capability: str | None) -> None:
        canonical = canonical_project_operation(operation)
        spec = OPERATIONS.get(canonical) or PROJECT_OPERATIONS.get(canonical)
        if spec is None:
            raise PiDomainGatewayError("unknown_operation")
        if capability is None or not hmac.compare_digest(str(capability), str(self.capability)):
            raise PiDomainGatewayError("capability_invalid")
        if not isinstance(params, Mapping) or set(params) - spec["allowed"]:
            raise PiDomainGatewayError("undeclared_input")
        if canonical.startswith("domain.") and not params.get("task_id"):
            raise PiDomainGatewayError("task_id_required")
        if not params.get("idempotency_key"):
            raise PiDomainGatewayError("idempotency_key_required")
        if not params.get("binding"):
            raise PiDomainGatewayError("binding_required")

    def invoke(self, operation: str, params: Mapping[str, Any] | None = None, *, capability: str | None = None) -> dict[str, Any]:
        params = dict(params or {})
        try:
            self._check(operation, params, capability)
            canonical = canonical_project_operation(operation)
            spec = OPERATIONS.get(canonical) or PROJECT_OPERATIONS[canonical]
            routed = {key: value for key, value in params.items() if key not in {"task_id", "binding"}}
            if canonical in WAREHOUSE_READ_OPERATIONS:
                data = (self.warehouse_tools or WarehouseTools()).invoke(
                    canonical, {key: value for key, value in routed.items() if key != "idempotency_key"}
                )
                data["capability_checksum"] = spec["checksum"]
                return _ok(canonical, data)
            if canonical in SEMANTIC_OPERATIONS or canonical in RETRIEVAL_OPERATIONS or canonical in SNAPSHOT_OPERATIONS:
                if canonical in SEMANTIC_OPERATIONS:
                    tool = self.semantic_tools
                elif canonical in RETRIEVAL_OPERATIONS:
                    tool = self.retrieval_tools
                else:
                    tool = self.snapshot_tools
                if tool is None:
                    return _ok(canonical, {"status": "authority_unavailable", "execution": "not_run", "capability_checksum": spec["checksum"]})
                data = tool.invoke(canonical, routed)
                if isinstance(data, dict):
                    data["capability_checksum"] = spec["checksum"]
                return _ok(canonical, data)
            if canonical in MUTATION_OPERATIONS:
                if self.warehouse_ledger is None:
                    return _ok(canonical, {"status": "authority_unavailable", "execution": "not_run", "capability_checksum": spec["checksum"]})
                data = self.warehouse_ledger.invoke(canonical, routed)
                if isinstance(data, dict):
                    data["capability_checksum"] = spec["checksum"]
                return _ok(canonical, data)
            if canonical == EVIDENCE_SQLITE_OPERATION:
                # Explicit operation registration only: no dynamic callable/path.
                # Lease, manifest checksum and privacy ceiling are validated here
                # (before the adapter), and the adapter repeats query-ID/scope/
                # binding denial. Never a promotion/canonical mutation route.
                if params.get("skill_id") != LEASE_SKILL_ID:
                    return _error(canonical, "lease_invalid")
                if params.get("manifest_checksum") != knowledge_research_checksum():
                    return _error(canonical, "manifest_drift")
                if params.get("privacy_ceiling") != PRIVACY_CEILING:
                    return _error(canonical, "privacy_ceiling_mismatch")
                tool = self.evidence_tool or EvidenceSqliteTool()
                data = tool.invoke({key: value for key, value in params.items() if key not in {"task_id", "idempotency_key"}})
                if isinstance(data, dict):
                    data["capability_checksum"] = spec.get("checksum")
                return _ok(canonical, data)
            if spec["kind"] == "read":
                if self.read_handler is not None:
                    return _ok(canonical, self.read_handler(canonical, params))
                return _ok(canonical, {"status": "synthetic", "operation": canonical, "task_id": params.get("task_id"), "evidence_refs": params.get("evidence_refs", []), "capability_checksum": spec.get("checksum")})
            target = self.service or GuardedOrchestrationInterface()
            # Only the existing guarded interface receives writes; no dynamic callable names enter it.
            routed = {key: value for key, value in params.items() if key not in {"task_id", "binding", "idempotency_key"}}
            result = target.invoke(operation, **routed)
            return _ok(operation, result)
        except PiDomainGatewayError as exc:
            return _error(operation, exc.code)
        except Exception as exc:  # transport-safe envelope; detail stays local
            code = str(getattr(exc, "code", "") or "domain_unavailable").split(":", 1)[0]
            safe_codes = {
                "missing_parameter", "explicit_confirmation_required", "confirmation_expired", "preview_checksum_mismatch",
                "invalid_request", "provider_outcome_unknown", "preview_stale", "snapshot_binding_mismatch",
                "watermark_binding_mismatch", "idempotency_conflict", "idempotency_mismatch", "warehouse_authority_unavailable",
                "preview_required", "fingerprint_binding_mismatch",
                "lease_invalid", "manifest_drift", "privacy_ceiling_mismatch",
                "database_unknown", "unknown_query", "version_mismatch", "binding_required", "scope_denied",
                "sql_forbidden", "parameter_invalid", "path_forbidden", "limit_exceeded",
                "supporting_skill_rejected", "database_unavailable", "schema_gate_failed",
                "query_timeout", "descriptor_invalid", "undeclared_input",
            }
            return _error(operation, code if code in safe_codes else "domain_unavailable")

def invoke_pi_domain(operation: str, params: Mapping[str, Any] | None = None, *, capability: str | None = None, service=None) -> dict[str, Any]:
    return PiDomainGateway(service=service).invoke(operation, params, capability=capability)

__all__ = ["OPERATIONS", "PROJECT_OPERATIONS", "PROJECT_ALIASES", "PI_DOMAIN_GATEWAY_SCHEMA", "PI_DOMAIN_CAPABILITY_HEADER", "PiDomainGateway", "PiDomainGatewayError", "canonical_project_operation", "invoke_pi_domain"]
