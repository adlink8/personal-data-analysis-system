from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.serving.snapshots import (
    activate_snapshot, get_active_snapshot, prepare_snapshot, rollback_snapshot, validate_snapshot,
)


def _db(tmp_path: Path) -> Path:
    path = tmp_path / "db.sqlite"
    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    con.close()
    return path


def _member(collection: str, checksum: str = "ck", count: int = 2) -> dict:
    return {"version": collection, "checksum": checksum, "location_kind": "chroma_collection", "location_ref": collection, "metadata": {"unit_count": count}}


def _inspect(name: str) -> dict:
    return {"exists": True, "checksum": "ck", "count": 2}


def _validated(db: Path, collection: str) -> str:
    draft = prepare_snapshot(db, {"knowledge_retrieval": _member(collection)}, eval_gate_ref="gate-pass", write=True)
    assert validate_snapshot(db, draft["snapshot_id"], collection_inspector=_inspect, required_roles={"knowledge_retrieval"})["ok"]
    return draft["snapshot_id"]


def test_prepare_dry_run_and_validation_refusal_do_not_activate(tmp_path: Path) -> None:
    db = _db(tmp_path)
    dry = prepare_snapshot(db, {"knowledge_retrieval": _member("cand")})
    assert dry["written"] is False
    assert get_active_snapshot(db) is None


def test_failed_gate_and_evidence_integrity_refuse_snapshot(tmp_path: Path) -> None:
    db = _db(tmp_path)
    written = prepare_snapshot(db, {"knowledge_retrieval": _member("cand")}, eval_gate_ref="gate-fail", write=True)
    refused = validate_snapshot(
        db,
        written["snapshot_id"],
        collection_inspector=_inspect,
        require_gate=True,
        gate_validator=lambda _: False,
        integrity_validator=lambda _: {"ok": False, "errors": ["evidence_integrity_failed"]},
    )
    assert refused["ok"] is False
    assert {"eval_gate_not_passed", "evidence_integrity_failed"} <= set(refused["errors"])
    assert get_active_snapshot(db) is None
    written = prepare_snapshot(db, {"knowledge_retrieval": _member("cand")}, write=True)
    bad = validate_snapshot(db, written["snapshot_id"], collection_inspector=lambda _: {"exists": True, "checksum": "wrong", "count": 2})
    assert bad["ok"] is False
    assert get_active_snapshot(db) is None


def test_activation_failure_before_commit_preserves_previous(tmp_path: Path) -> None:
    db = _db(tmp_path)
    pointer = tmp_path / "active.txt"
    old = _validated(db, "old")
    activate_snapshot(db, old, pointer_path=pointer)
    new = _validated(db, "new")
    with pytest.raises(RuntimeError, match="injected"):
        activate_snapshot(db, new, pointer_path=pointer, inject_failure="before_commit")
    assert get_active_snapshot(db)["snapshot_id"] == old
    assert pointer.read_text() == "old"


def test_projection_failure_does_not_split_sqlite_authority(tmp_path: Path) -> None:
    db = _db(tmp_path)
    pointer = tmp_path / "active.txt"
    old = _validated(db, "old")
    activate_snapshot(db, old, pointer_path=pointer)
    new = _validated(db, "new")
    result = activate_snapshot(db, new, pointer_path=pointer, inject_failure="projection")
    assert result["ok"] is True and result["projection_ok"] is False
    assert get_active_snapshot(db)["snapshot_id"] == new
    assert pointer.read_text() == "old"


def test_rollback_reactivates_prior_snapshot_without_deleting_history(tmp_path: Path) -> None:
    db = _db(tmp_path)
    pointer = tmp_path / "active.txt"
    old = _validated(db, "old")
    new = _validated(db, "new")
    activate_snapshot(db, old, pointer_path=pointer)
    activate_snapshot(db, new, pointer_path=pointer)
    result = rollback_snapshot(db, old, pointer_path=pointer)
    assert result["ok"] is True
    assert get_active_snapshot(db)["snapshot_id"] == old
    assert pointer.read_text() == "old"
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM serving_snapshots").fetchone()[0] == 2
    assert con.execute("SELECT COUNT(*) FROM serving_snapshot_events WHERE action='rollback'").fetchone()[0] == 1
    con.close()
