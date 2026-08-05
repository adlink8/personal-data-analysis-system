from __future__ import annotations

from personal_knowledge.services.capability_registry import load_registry, operations_for_profile
from personal_knowledge.services.pi_domain_gateway import (
    PROJECT_OPERATIONS,
    PiDomainGateway,
    canonical_project_operation,
)


def _params(operation: str) -> dict[str, object]:
    params: dict[str, object] = {
        "task_id": "pi_task_capability_test",
        "idempotency_key": f"idem:{operation}",
        "binding": "binding:capability-test",
    }
    if operation.startswith("warehouse."):
        params["authority_id"] = "knowledge"
    return params


def test_gateway_and_registry_expose_the_same_production_operations() -> None:
    registry = load_registry()
    expected = {operation["id"] for operation in operations_for_profile(registry, "production")}
    assert expected == set(PROJECT_OPERATIONS)
    assert len(expected) >= 10
    gateway = PiDomainGateway(capability="test-capability")
    for operation in sorted(expected):
        result = gateway.invoke(operation, _params(operation), capability="test-capability")
        assert result["ok"] is True
        assert result["operation"] == operation
        assert result["data"]["capability_checksum"] == PROJECT_OPERATIONS[operation]["checksum"]


def test_legacy_aliases_resolve_to_canonical_registry_ids() -> None:
    assert canonical_project_operation("search") == "knowledge.search"
    assert canonical_project_operation("external_context_list") == "external.list"
    assert canonical_project_operation("decision_analysis_get") == "decision.get"


def test_unknown_or_mutating_capabilities_fail_before_read_handler() -> None:
    calls: list[str] = []
    gateway = PiDomainGateway(capability="test-capability", read_handler=lambda operation, params: calls.append(operation))
    unknown = gateway.invoke("warehouse.drop_all", _params("warehouse.drop_all"), capability="test-capability")
    assert unknown["ok"] is False and unknown["error"]["code"] == "unknown_operation"
    denied = gateway.invoke("knowledge.search", {**_params("knowledge.search"), "sql": "select 1"}, capability="test-capability")
    assert denied["ok"] is False and denied["error"]["code"] == "undeclared_input"
    assert calls == []
