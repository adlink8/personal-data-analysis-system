from __future__ import annotations

from pathlib import Path

import pytest

from personal_knowledge.services.snapshot_release_tools import SnapshotAuthorityFixture, SnapshotReleaseError, SnapshotReleaseTools
from personal_knowledge.services.warehouse_mutations import InMemoryWarehouseStore, WarehouseOperationLedger


NOW = "2026-08-05T10:00:00+00:00"


def _prepare(tools: SnapshotReleaseTools, *, action: str = "activate", key: str = "release-1") -> dict:
    return tools.prepare(
        action=action,
        snapshot_id="snapshot:new",
        generation_id="generation:new",
        manifest={"schema_version": 1, "members": ["knowledge:generation:new"]},
        reconcile={"missing": 0, "orphan": 0, "duplicate": 0},
        eval_passed=True,
        eval_checksum="eval:checksum:1",
        current_pointer="pointer:active",
        target_pointer="pointer:new",
        protected_fingerprint="fingerprint:protected:1",
        idempotency_key=key,
        actor="user",
        now=NOW,
    )


def test_guarded_write_requires_exact_preview_and_confirmation(tmp_path: Path) -> None:
    pointer = tmp_path / "active.pointer"
    pointer.write_text("pointer:active", encoding="utf-8")
    authority = SnapshotAuthorityFixture(pointer_path=pointer)
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite", store=InMemoryWarehouseStore())
    tools = SnapshotReleaseTools(ledger, authority=authority)
    prepared = _prepare(tools)
    preview = prepared["preview"]

    with pytest.raises(SnapshotReleaseError, match="explicit_confirmation_required"):
        tools.execute(preview, confirmed=False, idempotency_key="release-1", now=NOW)
    tampered = dict(preview)
    tampered["plan"] = {**preview["plan"], "target_pointer": "pointer:evil"}
    with pytest.raises(SnapshotReleaseError, match="preview_checksum_mismatch"):
        tools.execute(tampered, confirmed=True, idempotency_key="release-1", now=NOW)
    with pytest.raises(SnapshotReleaseError, match="preview_stale"):
        tools.execute(preview, confirmed=True, idempotency_key="release-1", now="2026-08-05T10:16:00+00:00")
    assert authority.read_pointer() == "pointer:active"


def test_activate_replay_is_idempotent_and_pointer_switch_is_exact(tmp_path: Path) -> None:
    pointer = tmp_path / "active.pointer"
    pointer.write_text("pointer:active", encoding="utf-8")
    authority = SnapshotAuthorityFixture(pointer_path=pointer)
    ledger = WarehouseOperationLedger(tmp_path / "operations.sqlite")
    tools = SnapshotReleaseTools(ledger, authority=authority)
    prepared = _prepare(tools, key="release-replay")
    receipt = tools.execute(prepared["preview"], confirmed=True, idempotency_key="release-replay", now=NOW)
    replay = tools.execute(prepared["preview"], confirmed=True, idempotency_key="release-replay", now=NOW)
    assert receipt == replay
    assert authority.read_pointer() == "pointer:new"
    assert not pointer.with_suffix(pointer.suffix + ".tmp").exists()


def test_prepare_rejects_failed_eval_nonzero_reconcile_and_pointer_drift(tmp_path: Path) -> None:
    authority = SnapshotAuthorityFixture()
    tools = SnapshotReleaseTools(WarehouseOperationLedger(tmp_path / "operations.sqlite"), authority=authority)
    base = dict(
        action="activate", snapshot_id="snapshot:x", generation_id="generation:x",
        manifest={"schema_version": 1}, reconcile={"missing": 0, "orphan": 0, "duplicate": 0},
        eval_passed=True, eval_checksum="eval:x", current_pointer="pointer:active", target_pointer="pointer:x",
        protected_fingerprint="fingerprint:x", idempotency_key="release-x", now=NOW,
    )
    with pytest.raises(SnapshotReleaseError, match="eval_gate_not_passed"):
        tools.prepare(**{**base, "eval_passed": False})
    with pytest.raises(SnapshotReleaseError, match="reconcile_not_clean"):
        tools.prepare(**{**base, "reconcile": {"missing": 1, "orphan": 0, "duplicate": 0}})
    authority.active_pointer = "pointer:drift"
    with pytest.raises(SnapshotReleaseError, match="pointer_binding_mismatch"):
        tools.prepare(**base)

