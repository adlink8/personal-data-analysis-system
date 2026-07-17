"""Prepare, validate, activate and roll back immutable serving snapshots."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Callable, Mapping
import uuid

from personal_knowledge.core.sqlite import assert_foreign_key_integrity, connect_rw
from personal_knowledge.governance.artifact_registry import load_registry, validate_registry


def _now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def manifest_hash(manifest: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(manifest).encode("utf-8")).hexdigest()


def _id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode()).hexdigest()[:24]}"


def _event(con: sqlite3.Connection, action: str, snapshot_id: str | None, detail: dict, previous: str | None = None) -> str:
    event_id = f"se_{uuid.uuid4().hex}"
    con.execute(
        "INSERT INTO serving_snapshot_events VALUES (?,?,?,?,?,?)",
        (event_id, snapshot_id, action, previous, canonical_json(detail), _now()),
    )
    return event_id


def sync_registry_entries(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    doc = load_registry()
    issues = validate_registry(doc)
    if issues:
        raise ValueError(f"artifact registry invalid: {[x.code for x in issues]}")
    result: dict[str, dict[str, Any]] = {}
    for row in doc["artifacts"]:
        digest = hashlib.sha256(canonical_json(row).encode()).hexdigest()
        existing = con.execute(
            "SELECT layer, authority_role, privacy_class, definition_hash FROM artifact_registry_entries WHERE registry_id=?",
            (row["id"],),
        ).fetchone()
        values = (row["layer"], row["authority_role"], row["privacy"], digest)
        if existing and tuple(existing) != values:
            raise RuntimeError(f"runtime registry drift for {row['id']}")
        con.execute(
            "INSERT OR IGNORE INTO artifact_registry_entries VALUES (?,?,?,?,?,?)",
            (row["id"], *values, _now()),
        )
        result[row["authority_role"]] = row
    return result


def prepare_snapshot(
    db_path: Path,
    members: Mapping[str, Mapping[str, Any]],
    *,
    eval_gate_ref: str | None = None,
    write: bool = False,
) -> dict[str, Any]:
    ordered = {role: dict(sorted(member.items())) for role, member in sorted(members.items())}
    manifest = {"schema_version": 1, "members": ordered, "eval_gate_ref": eval_gate_ref}
    digest = manifest_hash(manifest)
    snapshot_id = _id("ss", digest)
    result = {"snapshot_id": snapshot_id, "manifest_hash": digest, "manifest": manifest, "status": "draft", "written": False}
    if not write:
        return result
    con = connect_rw(db_path, timeout=60)
    try:
        assert_foreign_key_integrity(con)
        con.execute("BEGIN IMMEDIATE")
        roles = sync_registry_entries(con)
        con.execute(
            "INSERT OR IGNORE INTO serving_snapshots VALUES (?,?,?,?,?,?,NULL)",
            (snapshot_id, canonical_json(manifest), digest, "draft", eval_gate_ref, _now()),
        )
        for role, member in ordered.items():
            definition = roles.get(role)
            if definition is None:
                raise ValueError(f"unknown serving role: {role}")
            version = str(member.get("version") or "")
            checksum = str(member.get("checksum") or "")
            location_ref = str(member.get("location_ref") or "")
            if not version or not checksum or not location_ref:
                raise ValueError(f"incomplete member metadata: {role}")
            avid = str(member.get("artifact_version_id") or _id("av", f"{definition['id']}|{version}|{checksum}"))
            con.execute(
                "INSERT OR IGNORE INTO artifact_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (avid, definition["id"], version, checksum, str(member.get("location_kind") or definition["kind"]), location_ref, "validated", definition["privacy"], member.get("producer_run_id"), member.get("evidence_version_id"), canonical_json(member.get("metadata") or {}), _now()),
            )
            con.execute(
                "INSERT OR IGNORE INTO serving_snapshot_members VALUES (?,?,?,?)",
                (snapshot_id, role, avid, member.get("watermark_id")),
            )
        _event(con, "prepare", snapshot_id, {"manifest_hash": digest, "roles": sorted(ordered)})
        con.commit()
        result["written"] = True
        return result
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def _snapshot_rows(con: sqlite3.Connection, snapshot_id: str) -> tuple[sqlite3.Row | None, list[sqlite3.Row]]:
    con.row_factory = sqlite3.Row
    snap = con.execute("SELECT * FROM serving_snapshots WHERE snapshot_id=?", (snapshot_id,)).fetchone()
    rows = con.execute(
        "SELECT m.serving_role, m.watermark_id, v.* FROM serving_snapshot_members m JOIN artifact_versions v ON v.artifact_version_id=m.artifact_version_id WHERE m.snapshot_id=? ORDER BY m.serving_role",
        (snapshot_id,),
    ).fetchall()
    return snap, rows


def validate_snapshot(
    db_path: Path,
    snapshot_id: str,
    *,
    collection_inspector: Callable[[str], Mapping[str, Any]] | None = None,
    required_roles: set[str] | None = None,
) -> dict[str, Any]:
    con = connect_rw(db_path, timeout=60)
    try:
        assert_foreign_key_integrity(con)
        snap, members = _snapshot_rows(con, snapshot_id)
        errors: list[str] = []
        if snap is None:
            return {"ok": False, "snapshot_id": snapshot_id, "errors": ["snapshot_not_found"]}
        roles = {str(row["serving_role"]) for row in members}
        missing = sorted((required_roles or set()) - roles)
        if missing:
            errors.append(f"missing_roles:{','.join(missing)}")
        for row in members:
            if row["location_kind"] == "chroma_collection":
                if collection_inspector is None:
                    errors.append(f"collection_unverified:{row['serving_role']}")
                    continue
                actual = collection_inspector(str(row["location_ref"]))
                if not actual.get("exists"):
                    errors.append(f"collection_missing:{row['serving_role']}")
                if str(actual.get("checksum") or "") != str(row["checksum"]):
                    errors.append(f"collection_checksum:{row['serving_role']}")
                expected_count = json.loads(row["metadata_json"] or "{}").get("unit_count")
                if expected_count is not None and int(actual.get("count", -1)) != int(expected_count):
                    errors.append(f"collection_count:{row['serving_role']}")
        con.execute("BEGIN IMMEDIATE")
        if errors:
            _event(con, "refuse", snapshot_id, {"errors": errors})
        else:
            con.execute("UPDATE serving_snapshots SET status='validated', validated_at=? WHERE snapshot_id=? AND status='draft'", (_now(), snapshot_id))
            _event(con, "validate", snapshot_id, {"roles": sorted(roles)})
        con.commit()
        return {"ok": not errors, "snapshot_id": snapshot_id, "errors": errors, "roles": sorted(roles)}
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def get_active_snapshot(db_path: Path) -> dict[str, Any] | None:
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT s.* FROM serving_authority a JOIN serving_snapshots s ON s.snapshot_id=a.active_snapshot_id WHERE a.singleton_id=1"
        ).fetchone()
        if row is None:
            return None
        _, members = _snapshot_rows(con, str(row["snapshot_id"]))
        return {**dict(row), "members": {m["serving_role"]: dict(m) for m in members}}
    finally:
        con.close()


def activate_snapshot(
    db_path: Path,
    snapshot_id: str,
    *,
    pointer_path: Path | None = None,
    pointer_role: str = "knowledge_retrieval",
    before_commit: Callable[[sqlite3.Connection], None] | None = None,
    inject_failure: str | None = None,
) -> dict[str, Any]:
    con = connect_rw(db_path, timeout=60)
    previous: str | None = None
    event_id = ""
    try:
        assert_foreign_key_integrity(con)
        snap, members = _snapshot_rows(con, snapshot_id)
        if snap is None or snap["status"] != "validated":
            return {"ok": False, "error": "snapshot_not_validated", "snapshot_id": snapshot_id}
        previous_row = con.execute("SELECT active_snapshot_id FROM serving_authority WHERE singleton_id=1").fetchone()
        previous = previous_row[0] if previous_row else None
        if inject_failure == "before_transaction":
            raise RuntimeError("injected before transaction")
        con.execute("BEGIN IMMEDIATE")
        if before_commit:
            before_commit(con)
        event_id = _event(con, "activate" if not previous else "activate", snapshot_id, {}, previous)
        con.execute(
            "UPDATE serving_authority SET active_snapshot_id=?, activated_at=?, activation_event_id=? WHERE singleton_id=1",
            (snapshot_id, _now(), event_id),
        )
        if inject_failure == "before_commit":
            raise RuntimeError("injected before commit")
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()

    projection_ok = True
    projection_error = ""
    if pointer_path is not None:
        try:
            if inject_failure == "projection":
                raise OSError("injected projection failure")
            active = get_active_snapshot(db_path) or {}
            member = (active.get("members") or {}).get(pointer_role) or {}
            collection = str(member.get("location_ref") or "")
            if not collection:
                raise RuntimeError(f"snapshot has no {pointer_role} projection")
            pointer_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = pointer_path.with_suffix(pointer_path.suffix + ".tmp")
            tmp.write_text(collection, encoding="utf-8")
            tmp.replace(pointer_path)
            projection_ok = pointer_path.read_text(encoding="utf-8").strip() == collection
        except Exception as exc:  # authority remains the committed SQLite snapshot
            projection_ok = False
            projection_error = str(exc)
            drift = connect_rw(db_path)
            try:
                _event(drift, "projection_drift", snapshot_id, {"error": projection_error}, previous)
                drift.commit()
            finally:
                drift.close()
    return {"ok": True, "snapshot_id": snapshot_id, "previous_snapshot_id": previous, "event_id": event_id, "projection_ok": projection_ok, "projection_error": projection_error}


def rollback_snapshot(db_path: Path, snapshot_id: str, **kwargs: Any) -> dict[str, Any]:
    current = get_active_snapshot(db_path)
    result = activate_snapshot(db_path, snapshot_id, **kwargs)
    if result.get("ok"):
        con = connect_rw(db_path)
        try:
            _event(con, "rollback", snapshot_id, {}, (current or {}).get("snapshot_id"))
            con.commit()
        finally:
            con.close()
    return result
