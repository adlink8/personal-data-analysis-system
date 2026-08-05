from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.snapshot_release_tools import SnapshotAuthorityFixture, SnapshotReleaseError, SnapshotReleaseTools
from personal_knowledge.services.warehouse_mutations import WarehouseOperationLedger


NOW = "2026-08-05T10:00:00+00:00"


def _release(tools: SnapshotReleaseTools, *, action: str, key: str, current: str, target: str) -> dict:
    return tools.prepare(
        action=action, snapshot_id=f"snapshot:{target.split(':')[-1]}", generation_id=f"generation:{target.split(':')[-1]}",
        manifest={"schema_version": 1, "members": [target]}, reconcile={"missing": 0, "orphan": 0, "duplicate": 0},
        eval_passed=True, eval_checksum="eval:fixture:1", current_pointer=current, target_pointer=target,
        protected_fingerprint="fingerprint:fixture:1", idempotency_key=key, now=NOW,
    )


@pytest.mark.parametrize("fault", ["before_pointer", "pointer_write", "after_pointer"])
def test_pointer_fault_windows_converge_to_one_active_pointer(tmp_path: Path, fault: str) -> None:
    pointer = tmp_path / f"active-{fault}.pointer"
    pointer.write_text("pointer:active", encoding="utf-8")
    authority = SnapshotAuthorityFixture(pointer_path=pointer)
    tools = SnapshotReleaseTools(WarehouseOperationLedger(tmp_path / f"ledger-{fault}.sqlite"), authority=authority)
    prepared = _release(tools, action="activate", key=f"release-{fault}", current="pointer:active", target="pointer:new")
    with pytest.raises(SnapshotReleaseError, match="provider_outcome_unknown"):
        tools.execute(prepared["preview"], confirmed=True, idempotency_key=f"release-{fault}", now=NOW, fault=fault)

    reconciled = tools.reconcile(prepared["preview"]["operation_id"])
    assert reconciled["status"] in {"committed", "reconciled"}
    assert authority.read_pointer() == "pointer:new"
    assert not pointer.with_suffix(pointer.suffix + ".tmp").exists()


def test_rollback_restores_exact_previous_pointer_after_activation(tmp_path: Path) -> None:
    pointer = tmp_path / "active.pointer"
    pointer.write_text("pointer:active", encoding="utf-8")
    authority = SnapshotAuthorityFixture(pointer_path=pointer)
    tools = SnapshotReleaseTools(WarehouseOperationLedger(tmp_path / "operations.sqlite"), authority=authority)
    activation = _release(tools, action="activate", key="activate", current="pointer:active", target="pointer:new")
    tools.execute(activation["preview"], confirmed=True, idempotency_key="activate", now=NOW)
    rollback = _release(tools, action="rollback", key="rollback", current="pointer:new", target="pointer:active")
    receipt = tools.execute(rollback["preview"], confirmed=True, idempotency_key="rollback", now=NOW)
    assert receipt["active_pointer"] == "pointer:active"
    assert authority.read_pointer() == "pointer:active"
