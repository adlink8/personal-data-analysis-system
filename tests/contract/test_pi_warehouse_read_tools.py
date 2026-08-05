from __future__ import annotations

import pytest

from personal_knowledge.services.warehouse_tools import (
    OPERATIONS,
    WarehouseToolError,
    WarehouseTools,
)


def _tools(probe=None) -> WarehouseTools:
    return WarehouseTools(
        metadata={
            "knowledge": {
                "records": 12,
                "visible": 8,
                "stable_id": "knowledge:fixture",
                "snapshot_id": "snapshot:fixture",
                "watermark_id": "watermark:fixture",
                "raw": "must-not-leak",
            }
        },
        db_open=probe,
    )


@pytest.mark.parametrize("operation", sorted(OPERATIONS))
def test_every_warehouse_read_operation_is_bounded_metadata(operation: str) -> None:
    result = _tools().invoke(operation, {"authority_id": "knowledge", "limit": 10})

    assert result["schema_version"] == "pi_warehouse_read_v1"
    assert result["operation"] == operation
    assert result["ok"] is True
    assert result["counts"]["visible"] <= 10
    assert result["stable_ids"] == ["knowledge:fixture"]
    assert result["artifact_refs"] == ["artifact://warehouse/knowledge/snapshot:fixture"]
    assert "must-not-leak" not in str(result)
    assert all("/" not in item or item.startswith("artifact://") for item in result["artifact_refs"])


def test_preflight_rejects_sql_path_unknown_authority_and_oversized_limit_before_db_open() -> None:
    opened: list[str] = []
    tools = _tools(opened.append)
    cases = [
        ({"authority_id": "knowledge", "filters": {"status": "ready; DROP TABLE"}}, "sql_fragment_forbidden"),
        ({"authority_id": "knowledge", "cursor": "../../secrets"}, "path_forbidden"),
        ({"authority_id": "not-an-authority"}, "authority_unknown"),
        ({"authority_id": "knowledge", "limit": 101}, "limit_exceeded"),
        ({"authority_id": "knowledge", "query": "select 1"}, "undeclared_input"),
    ]
    for params, code in cases:
        with pytest.raises(WarehouseToolError) as exc:
            tools.invoke("warehouse.inspect", params)
        assert exc.value.code == code
    assert opened == []


def test_bounded_filters_and_dates_are_fixed_enums() -> None:
    result = _tools().invoke(
        "warehouse.quality",
        {
            "authority_id": "knowledge",
            "limit": 1,
            "start_date": "2026-01-01",
            "end_date": "2026-01-31",
            "filters": {"status": "ready", "source_type": "knowledge"},
        },
    )
    assert result["ok"] is True
    with pytest.raises(WarehouseToolError, match="filter_invalid"):
        _tools().invoke("warehouse.quality", {"authority_id": "knowledge", "filters": {"status": "anything"}})

