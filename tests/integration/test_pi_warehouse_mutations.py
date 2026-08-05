from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from personal_knowledge.services.warehouse_mutations import (
    InMemoryWarehouseStore,
    WarehouseMutationError,
    WarehouseOperationLedger,
)
from personal_knowledge.services.pi_domain_gateway import PiDomainGateway


NOW = "2026-08-05T10:00:00+00:00"


def _preview(ledger: WarehouseOperationLedger, operation: str, key: str, **kwargs):
    return ledger.preview(
        operation,
        authority_id="knowledge",
        source_checksum="source:fixture:1",
        snapshot_checksum="snapshot:fixture:1",
        watermark_checksum="watermark:fixture:1",
        count=2,
        idempotency_key=key,
        before_fingerprint=ledger.store.raw_fingerprint,
        now=NOW,
        **kwargs,
    )


def test_ingestion_commit_is_exact_idempotent_and_keeps_raw_immutable(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1", "body": "fixture"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    before_raw = deepcopy(store.raw_rows)
    preview = _preview(ledger, "ingestion.commit", "import-1")

    receipt = ledger.commit(preview, idempotency_key="import-1", now=NOW)
    replay = ledger.commit(preview, idempotency_key="import-1", now=NOW)

    assert receipt == replay
    assert receipt["status"] == "committed"
    assert store.raw_rows == before_raw
    assert len(store.candidate_events) == 1
    assert ledger.get_operation(preview["operation_id"])["after_fingerprint"]


def test_tamper_and_binding_mismatch_fail_before_any_store_change(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _preview(ledger, "ingestion.commit", "import-tamper")
    tampered = dict(preview)
    tampered["count"] = 99
    with pytest.raises(WarehouseMutationError, match="preview_checksum_mismatch"):
        ledger.commit(tampered, idempotency_key="import-tamper", now=NOW)
    with pytest.raises(WarehouseMutationError, match="snapshot_binding_mismatch"):
        ledger.commit(preview, idempotency_key="import-tamper", now=NOW, snapshot_checksum="snapshot:changed")
    recomputed = dict(tampered)
    from hashlib import sha256
    import json
    recomputed["preview_checksum"] = sha256(json.dumps({k: v for k, v in recomputed.items() if k != "preview_checksum"}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with pytest.raises(WarehouseMutationError, match="preview_checksum_mismatch"):
        ledger.commit(recomputed, idempotency_key="import-tamper", now=NOW)
    assert store.candidate_events == []
    assert store.raw_rows == [{"id": "raw-1"}]


def test_canonical_correction_is_confirmation_gated_and_append_only(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1", "value": "old"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _preview(ledger, "canonical.apply_correction", "correction-1")
    with pytest.raises(WarehouseMutationError, match="explicit_confirmation_required"):
        ledger.commit(preview, idempotency_key="correction-1", now=NOW)
    receipt = ledger.commit(preview, confirmed=True, idempotency_key="correction-1", now=NOW)

    assert receipt["compensation_of"] is None
    assert store.raw_rows == [{"id": "raw-1", "value": "old"}]
    assert len(store.compensation_events) == 1
    assert store.canonical_events == []


def test_same_idempotency_identity_cannot_change_source_binding(tmp_path: Path) -> None:
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite")
    _preview(ledger, "ingestion.commit", "same-key")
    with pytest.raises(WarehouseMutationError, match="idempotency_conflict"):
        ledger.preview(
            "ingestion.commit", authority_id="knowledge", source_checksum="source:changed",
            snapshot_checksum="snapshot:fixture:1", watermark_checksum="watermark:fixture:1",
            count=2, idempotency_key="same-key", now=NOW,
        )


def test_pi_gateway_routes_exact_preview_to_the_python_ledger(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _preview(ledger, "canonical.reconcile", "gateway-1")
    gateway = PiDomainGateway(capability="fixture-capability", warehouse_ledger=ledger)
    result = gateway.invoke(
        "canonical.reconcile",
        {
            "task_id": "task-1",
            "binding": "binding-1",
            "idempotency_key": "gateway-1",
            "preview": preview,
            "confirmed": True,
            "now": NOW,
        },
        capability="fixture-capability",
    )
    assert result["ok"] is True
    assert result["data"]["capability_id"] == "canonical.reconcile"
    assert result["data"]["status"] == "committed"
