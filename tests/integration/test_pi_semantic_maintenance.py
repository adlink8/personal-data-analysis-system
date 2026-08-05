from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.semantic_maintenance_tools import SemanticMaintenanceError, SemanticMaintenanceTools
from personal_knowledge.services.warehouse_mutations import InMemoryWarehouseStore, WarehouseOperationLedger


NOW = "2026-08-05T10:00:00+00:00"


def _params(key: str = "semantic-1") -> dict:
    return {
        "source_scope": "knowledge",
        "snapshot_checksum": "snapshot:semantic:1",
        "watermark_checksum": "watermark:semantic:1",
        "batch_limit": 10,
        "extractor": "extractor:v1",
        "model_receipt": "model:fixture:1",
        "schema_version": "knowledge_candidate_v1",
        "evidence_refs": [{"ref": "evidence:1", "checksum": "evidence-checksum-1"}],
        "records": [{
            "candidate_id": "candidate:1",
            "claim_checksum": "claim-checksum-1",
            "unit_type": "preference",
            "evidence_refs": [],
            "extractor": "extractor:v1",
            "model_receipt": "model:fixture:1",
            "schema_version": "knowledge_candidate_v1",
        }],
        "idempotency_key": key,
        "now": NOW,
    }


def test_semantic_records_are_evidence_model_schema_bound_and_staged(tmp_path: Path) -> None:
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=InMemoryWarehouseStore())
    tools = SemanticMaintenanceTools(ledger)
    before_active = tools.store.active_inventory_fingerprint
    previewed = tools.invoke("knowledge.extract_l1", _params())
    assert previewed["status"] == "previewed"
    committed = tools.invoke("knowledge.extract_l1", {"preview": previewed["preview"], "idempotency_key": "semantic-1", "now": NOW})
    replay = tools.invoke("knowledge.extract_l1", {"preview": previewed["preview"], "idempotency_key": "semantic-1", "now": NOW})

    assert committed["status"] == "staged"
    assert committed["candidate_ids"] == ["candidate:1"]
    assert committed["candidate_ids"] == replay["candidate_ids"]
    assert tools.store.candidates["candidate:1"]["evidence_refs"][0]["ref"] == "evidence:1"
    assert tools.store.active_inventory_fingerprint == before_active


def test_semantic_tool_rejects_promotion_fields_and_cross_binding(tmp_path: Path) -> None:
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite")
    tools = SemanticMaintenanceTools(ledger)
    with pytest.raises(SemanticMaintenanceError, match="undeclared_input"):
        tools.invoke("knowledge.backfill", {**_params("semantic-2"), "promotion": True})
    bad = _params("semantic-3")
    bad["records"] = [{**bad["records"][0], "model_receipt": "model:other"}]
    with pytest.raises(SemanticMaintenanceError, match="candidate_binding_mismatch"):
        tools.invoke("knowledge.extract_l2", bad)

