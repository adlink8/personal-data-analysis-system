from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.retrieval_maintenance_tools import RetrievalMaintenanceError, RetrievalMaintenanceTools
from personal_knowledge.services.warehouse_mutations import InMemoryWarehouseStore, WarehouseOperationLedger


NOW = "2026-08-05T10:00:00+00:00"


def _build(ledger: WarehouseOperationLedger, key: str = "index-1") -> tuple[RetrievalMaintenanceTools, dict]:
    tools = RetrievalMaintenanceTools(ledger)
    result = tools.invoke("index.build", {
        "semantic_snapshot_checksum": "snapshot:semantic:1",
        "source_ids": ["unit:1", "unit:2"],
        "embedding_receipt": "embedding:fixture:1",
        "index_schema_version": "index_v1",
        "idempotency_key": key,
        "now": NOW,
    })
    return tools, result


def test_index_build_isolated_generation_and_clean_reconcile_evaluation(tmp_path: Path) -> None:
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=InMemoryWarehouseStore())
    tools, previewed = _build(ledger)
    active_before = tools.store.active_generation
    built = tools.invoke("index.build", {"preview": previewed["preview"], "idempotency_key": "index-1", "now": NOW})
    generation = built["generation_id"]
    assert generation != active_before
    assert tools.store.active_generation == active_before

    reconcile = tools.invoke("index.reconcile", {"generation_id": generation, "expected_ids": ["unit:1", "unit:2"], "indexed_ids": ["unit:1", "unit:2"]})
    assert reconcile["ok"] is True
    evaluated = tools.invoke("index.evaluate", {"generation_id": generation, "policy_id": "policy:v1", "policy_checksum": "policy-checksum-1", "reconcile": reconcile["counts"], "idempotency_key": "eval-1"})
    replay = tools.invoke("index.evaluate", {"generation_id": generation, "policy_id": "policy:v1", "policy_checksum": "policy-checksum-1", "reconcile": reconcile["counts"], "idempotency_key": "eval-1"})
    assert evaluated["passed"] is True
    assert evaluated["evidence_checksum"] == replay["evidence_checksum"]


def test_nonzero_reconcile_blocks_evaluation_and_active_fingerprint_stays(tmp_path: Path) -> None:
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite")
    tools, previewed = _build(ledger, "index-2")
    built = tools.invoke("index.build", {"preview": previewed["preview"], "idempotency_key": "index-2", "now": NOW})
    generation = built["generation_id"]
    active_before = tools.store.active_generation
    reconcile = tools.invoke("index.reconcile", {"generation_id": generation, "expected_ids": ["unit:1", "unit:2"], "indexed_ids": ["unit:1", "unit:1", "orphan:1"]})
    assert reconcile["counts"] == {"missing": 1, "orphan": 1, "duplicate": 1}
    with pytest.raises(RetrievalMaintenanceError, match="reconcile_not_clean"):
        tools.invoke("index.evaluate", {"generation_id": generation, "policy_id": "policy:v1", "policy_checksum": "policy-checksum-1", "reconcile": reconcile["counts"], "idempotency_key": "eval-2"})
    assert tools.store.active_generation == active_before

