"""Immutable artifact publication versions and source watermarks.

The tracked registry describes artifact types.  This module records only
metadata about successful publications in the private unified SQLite store.
It never activates a serving snapshot.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping

from personal_knowledge.application.serving.snapshots import canonical_json, sync_registry_entries
from personal_knowledge.core.sqlite import assert_foreign_key_integrity, connect_rw


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _stable_id(prefix: str, value: str) -> str:
    return f"{prefix}_{hashlib.sha256(value.encode('utf-8')).hexdigest()[:24]}"


def file_checksum(path: Path) -> str:
    """Return a content checksum without exposing file contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def json_checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _table_exists(con: sqlite3.Connection, name: str) -> bool:
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def require_version_schema(con: sqlite3.Connection) -> None:
    required = {"artifact_registry_entries", "artifact_versions", "source_watermarks"}
    missing = sorted(name for name in required if not _table_exists(con, name))
    if missing:
        raise RuntimeError(
            "artifact version schema missing: " + ", ".join(missing)
            + "; run the knowledge schema migration first"
        )


def record_publication(
    db_path: Path,
    *,
    registry_id: str,
    version: str,
    checksum: str,
    location_kind: str,
    location_ref: str,
    source_key: str,
    watermark_value: str,
    producer_run_id: str | None = None,
    evidence_version_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Record a successful publication atomically and idempotently.

    A watermark can only reference the immutable version inserted in the same
    transaction (or an identical pre-existing version). Repeating unchanged
    input returns the same IDs and writes no new rows.
    """
    values = (version.strip(), checksum.strip(), location_ref.strip(), watermark_value.strip())
    if any(not value for value in values):
        raise ValueError("version, checksum, location_ref and watermark_value are required")

    con = connect_rw(db_path, timeout=60)
    try:
        assert_foreign_key_integrity(con)
        require_version_schema(con)
        con.execute("BEGIN IMMEDIATE")
        registry_by_role = sync_registry_entries(con)
        definition = next(
            (row for row in registry_by_role.values() if row["id"] == registry_id), None
        )
        if definition is None:
            raise ValueError(f"unknown registry id: {registry_id}")
        version_id = _stable_id("av", f"{registry_id}|{version}|{checksum}")
        watermark_id = _stable_id(
            "wm", f"{registry_id}|{source_key}|{watermark_value}"
        )
        version_exists = con.execute(
            "SELECT 1 FROM artifact_versions WHERE artifact_version_id=?", (version_id,)
        ).fetchone() is not None
        watermark_exists = con.execute(
            "SELECT 1 FROM source_watermarks WHERE watermark_id=?", (watermark_id,)
        ).fetchone() is not None
        now = _now()
        con.execute(
            "INSERT OR IGNORE INTO artifact_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                version_id,
                registry_id,
                version,
                checksum,
                location_kind,
                location_ref,
                "published",
                definition["privacy"],
                producer_run_id,
                evidence_version_id,
                canonical_json(dict(metadata or {})),
                now,
            ),
        )
        con.execute(
            "INSERT OR IGNORE INTO source_watermarks VALUES (?,?,?,?,?,?)",
            (
                watermark_id,
                registry_id,
                source_key,
                watermark_value,
                version_id,
                now,
            ),
        )
        # watermark_id 是 registry|source_key|value 的稳定哈希：同一 source 位置
        # 重新发布（如同一 canonical build 重建索引）时，已存在的 watermark 仍指向
        # 旧 artifact version，导致 doctor 报 watermark_version_mismatch。
        # 这里把指向校正到本次发布的 version（幂等：指向相同则不触发）。
        con.execute(
            "UPDATE source_watermarks SET artifact_version_id=?, recorded_at=? "
            "WHERE watermark_id=? AND artifact_version_id<>?",
            (version_id, now, watermark_id, version_id),
        )
        con.commit()
        return {
            "registry_id": registry_id,
            "artifact_version_id": version_id,
            "watermark_id": watermark_id,
            "version": version,
            "checksum": checksum,
            "created": not version_exists,
            "watermark_created": not watermark_exists,
        }
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def publication_status(db_path: Path) -> dict[str, Any]:
    """Read current publication metadata; never creates or changes state."""
    if not db_path.exists():
        return {"ok": False, "schema_ready": False, "error": "unified_db_missing", "artifacts": {}}
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        try:
            require_version_schema(con)
        except RuntimeError as exc:
            return {"ok": False, "schema_ready": False, "error": str(exc), "artifacts": {}}
        rows = con.execute(
            "SELECT r.registry_id, r.authority_role, v.artifact_version_id, v.version, "
            "v.checksum, v.location_kind, v.location_ref, v.producer_run_id, "
            "v.metadata_json, v.created_at, w.watermark_id, w.source_key, "
            "w.value AS watermark_value, w.recorded_at "
            "FROM artifact_registry_entries r "
            "LEFT JOIN artifact_versions v ON v.artifact_version_id=("
            " SELECT v2.artifact_version_id FROM artifact_versions v2 "
            " WHERE v2.registry_id=r.registry_id ORDER BY v2.created_at DESC, v2.artifact_version_id DESC LIMIT 1) "
            "LEFT JOIN source_watermarks w ON w.watermark_id=("
            " SELECT w2.watermark_id FROM source_watermarks w2 "
            " WHERE w2.registry_id=r.registry_id ORDER BY w2.recorded_at DESC, w2.watermark_id DESC LIMIT 1) "
            "ORDER BY r.registry_id"
        ).fetchall()
        artifacts: dict[str, dict[str, Any]] = {}
        for row in rows:
            item = dict(row)
            item["metadata"] = json.loads(item.pop("metadata_json") or "{}") if item.get("artifact_version_id") else {}
            artifacts[str(row["registry_id"])] = item
        return {"ok": True, "schema_ready": True, "artifacts": artifacts}
    finally:
        con.close()
