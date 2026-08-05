from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.warehouse_mutations import (
    InMemoryWarehouseStore,
    WarehouseMutationError,
    WarehouseOperationLedger,
)


NOW = "2026-08-05T10:00:00+00:00"


def _prepare(ledger: WarehouseOperationLedger, key: str):
    return ledger.preview(
        "ingestion.commit",
        authority_id="knowledge",
        source_checksum="source:recovery:1",
        snapshot_checksum="snapshot:recovery:1",
        watermark_checksum="watermark:recovery:1",
        count=1,
        idempotency_key=key,
        before_fingerprint=ledger.store.raw_fingerprint,
        now=NOW,
    )


def test_crash_after_store_reconciles_one_receipt_and_rejects_blind_retry(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _prepare(ledger, "recovery-1")
    with pytest.raises(WarehouseMutationError, match="provider_outcome_unknown"):
        ledger.commit(preview, idempotency_key="recovery-1", now=NOW, crash_at="after_store_before_receipt")

    assert ledger.get_operation(preview["operation_id"])["status"] == "outcome_unknown"
    assert len(store.candidate_events) == 1
    with pytest.raises(WarehouseMutationError, match="provider_outcome_unknown"):
        ledger.commit(preview, idempotency_key="recovery-1", now=NOW)
    receipt = ledger.reconcile_receipt(preview["operation_id"])
    assert receipt["status"] == "committed"
    assert ledger.reconcile_receipt(preview["operation_id"]) == receipt
    assert len(store.candidate_events) == 1


def test_crash_after_receipt_is_replay_safe(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _prepare(ledger, "recovery-2")
    with pytest.raises(WarehouseMutationError, match="provider_outcome_unknown"):
        ledger.commit(preview, idempotency_key="recovery-2", now=NOW, crash_at="after_receipt")
    receipt = ledger.resume(preview["operation_id"])
    assert receipt["status"] == "committed"
    assert len(store.candidate_events) == 1


def test_unknown_outcome_can_take_one_declared_append_only_compensation(tmp_path: Path) -> None:
    store = InMemoryWarehouseStore([{"id": "raw-1", "value": "raw"}])
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=store)
    preview = _prepare(ledger, "recovery-3")
    with pytest.raises(WarehouseMutationError):
        ledger.commit(preview, idempotency_key="recovery-3", now=NOW, crash_at="after_store_before_receipt")
    raw_before = list(store.raw_rows)

    receipt = ledger.compensate(
        preview["operation_id"], idempotency_key="compensation-3", confirmed=True, now=NOW,
    )
    assert receipt["capability_id"] == "canonical.apply_correction"
    assert receipt["compensation_of"] == preview["operation_id"]
    assert store.raw_rows == raw_before
    assert len(store.candidate_events) == 1
    assert len(store.compensation_events) == 1

