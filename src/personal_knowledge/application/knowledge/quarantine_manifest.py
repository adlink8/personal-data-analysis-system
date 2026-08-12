"""Checksummed quarantine manifests and constrained SQLite restoration.

This module owns files and fingerprints only.  Knowledge-table mutation and
serving-snapshot transitions deliberately live in ``legacy_isolation``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


MANIFEST_FORMAT = "personal-knowledge-quarantine-v1"
MANIFEST_PRODUCER = "personal_knowledge.application.knowledge.isolate_legacy_knowledge"
_GENERATION_RE = re.compile(r"^kg_[A-Za-z0-9][A-Za-z0-9_.-]{2,96}$")


class ManifestError(RuntimeError):
    """A quarantine artifact is missing, altered, or outside its authority."""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_value(digest: "hashlib._Hash", value: Any) -> None:
    if value is None:
        data = b"n"
    elif isinstance(value, bytes):
        data = b"b" + value
    else:
        data = (type(value).__name__ + ":" + str(value)).encode("utf-8", errors="surrogatepass")
    digest.update(len(data).to_bytes(8, "big"))
    digest.update(data)


def _table_order(con: sqlite3.Connection, table: str) -> str:
    columns = list(con.execute(f'PRAGMA table_info("{table}")'))
    primary = [str(row[1]) for row in sorted(columns, key=lambda row: int(row[5]) or 9999) if int(row[5])]
    if primary:
        return ",".join(f'"{name}"' for name in primary)
    return "rowid"


def database_fingerprint(path: Path) -> dict[str, Any]:
    """Return a content-sensitive, privacy-safe logical SQLite fingerprint."""
    resolved = path.resolve()
    if not resolved.is_file():
        raise ManifestError(f"SQLite database missing: {resolved}")
    con = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=60)
    try:
        quick = str(con.execute("PRAGMA quick_check").fetchone()[0])
        if quick.lower() != "ok":
            raise ManifestError(f"SQLite quick_check failed: {resolved}: {quick}")
        schema_rows = list(
            con.execute(
                "SELECT type,name,tbl_name,COALESCE(sql,'') FROM sqlite_master "
                "WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name"
            )
        )
        schema_sha = hashlib.sha256(canonical_json(schema_rows).encode("utf-8")).hexdigest()
        table_counts: dict[str, int] = {}
        table_hashes: dict[str, str] = {}
        whole = hashlib.sha256()
        table_names = [str(row[1]) for row in schema_rows if row[0] == "table"]
        for table in table_names:
            count = int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
            table_counts[table] = count
            digest = hashlib.sha256()
            try:
                order = _table_order(con, table)
                cursor = con.execute(f'SELECT * FROM "{table}" ORDER BY {order}')
            except sqlite3.OperationalError:
                cursor = con.execute(f'SELECT * FROM "{table}"')
            for row in cursor:
                digest.update(b"R")
                for value in row:
                    _update_value(digest, value)
            table_hashes[table] = digest.hexdigest()
            whole.update(table.encode("utf-8"))
            whole.update(str(count).encode("ascii"))
            whole.update(table_hashes[table].encode("ascii"))
        return {
            "schema_sha256": schema_sha,
            "logical_sha256": whole.hexdigest(),
            "table_counts": table_counts,
            "table_hashes": table_hashes,
            "quick_check": quick,
        }
    finally:
        con.close()


def source_fingerprint(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    if not resolved.is_file():
        return {"path": str(resolved), "exists": False}
    result: dict[str, Any] = {
        "path": str(resolved),
        "exists": True,
        "size": resolved.stat().st_size,
        "sha256": sha256_file(resolved),
    }
    try:
        result["sqlite"] = database_fingerprint(resolved)
    except (sqlite3.Error, ManifestError):
        pass
    wal = Path(str(resolved) + "-wal")
    if wal.is_file():
        result["wal"] = {"size": wal.stat().st_size, "sha256": sha256_file(wal)}
    return result


def fingerprint_sources(source_paths: Mapping[str, Path]) -> dict[str, dict[str, Any]]:
    return {name: source_fingerprint(path) for name, path in sorted(source_paths.items())}


def online_backup(source: Path, destination: Path) -> dict[str, Any]:
    source = source.resolve()
    destination = destination.resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    if temporary.exists():
        temporary.unlink()
    src = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True, timeout=60)
    dst = sqlite3.connect(temporary, timeout=60)
    try:
        src.backup(dst)
        dst.commit()
        check = str(dst.execute("PRAGMA quick_check").fetchone()[0])
        if check.lower() != "ok":
            raise ManifestError(f"backup quick_check failed: {check}")
    finally:
        dst.close()
        src.close()
    os.replace(temporary, destination)
    return {
        "path": str(destination),
        "sha256": sha256_file(destination),
        "size": destination.stat().st_size,
    }


def _manifest_checksum(document: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in document.items() if key != "manifest_checksum"}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _write_manifest(path: Path, document: Mapping[str, Any]) -> None:
    materialized = dict(document)
    materialized["manifest_checksum"] = _manifest_checksum(materialized)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(materialized, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def create_manifest(
    *,
    db_path: Path,
    pointer_path: Path,
    quarantine_root: Path,
    generation_id: str,
    source_paths: Mapping[str, Path],
    active_snapshot_id: str,
    old_collections: list[dict[str, Any]],
    derived_tables: list[str],
) -> tuple[Path, dict[str, Any]]:
    if not _GENERATION_RE.fullmatch(generation_id):
        raise ManifestError(f"invalid generation id: {generation_id}")
    generation_dir = (quarantine_root / generation_id).resolve()
    generation_dir.mkdir(parents=True, exist_ok=False)
    backup_path = generation_dir / "personal_system.sqlite"
    before = database_fingerprint(db_path)
    backup = online_backup(db_path, backup_path)
    backup_fingerprint = database_fingerprint(backup_path)
    if backup_fingerprint != before:
        raise ManifestError("online backup logical fingerprint mismatch")
    pointer_resolved = pointer_path.resolve()
    document: dict[str, Any] = {
        "format": MANIFEST_FORMAT,
        "producer": MANIFEST_PRODUCER,
        "generation_id": generation_id,
        "created_at": utc_now(),
        "status": "backup_ready",
        "target_db": str(db_path.resolve()),
        "backup": backup,
        "database_before": before,
        "pointer": {
            "path": str(pointer_resolved),
            "exists": pointer_resolved.exists(),
            "value": pointer_resolved.read_text(encoding="utf-8").strip() if pointer_resolved.exists() else "",
        },
        "active_snapshot_id": active_snapshot_id,
        "source_fingerprints": fingerprint_sources(source_paths),
        "old_collections": old_collections,
        "derived_tables": list(derived_tables),
    }
    manifest_path = generation_dir / "manifest.json"
    _write_manifest(manifest_path, document)
    return manifest_path, load_verified_manifest(manifest_path)


def load_verified_manifest(path: Path) -> dict[str, Any]:
    resolved = path.resolve()
    try:
        document = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest unreadable: {resolved}") from exc
    if document.get("format") != MANIFEST_FORMAT or document.get("producer") != MANIFEST_PRODUCER:
        raise ManifestError("manifest producer or format mismatch")
    generation_id = str(document.get("generation_id") or "")
    if not _GENERATION_RE.fullmatch(generation_id) or resolved.name != "manifest.json" or resolved.parent.name != generation_id:
        raise ManifestError("manifest generation path mismatch")
    if document.get("manifest_checksum") != _manifest_checksum(document):
        raise ManifestError("manifest checksum mismatch")
    backup_path = Path(str((document.get("backup") or {}).get("path") or "")).resolve()
    if backup_path != resolved.parent / "personal_system.sqlite":
        raise ManifestError("manifest backup path mismatch")
    if not backup_path.is_file() or sha256_file(backup_path) != (document.get("backup") or {}).get("sha256"):
        raise ManifestError("manifest backup checksum mismatch")
    backup_fingerprint = database_fingerprint(backup_path)
    if backup_fingerprint != document.get("database_before"):
        raise ManifestError("manifest backup logical fingerprint mismatch")
    return document


def update_manifest(path: Path, **changes: Any) -> dict[str, Any]:
    document = load_verified_manifest(path)
    document.update(changes)
    _write_manifest(path.resolve(), document)
    return load_verified_manifest(path)


def restore_from_manifest(
    manifest_path: Path,
    *,
    db_path: Path | None = None,
    pointer_path: Path | None = None,
) -> dict[str, Any]:
    document = load_verified_manifest(manifest_path)
    expected_db = Path(document["target_db"]).resolve()
    expected_pointer = Path(document["pointer"]["path"]).resolve()
    if db_path is not None and db_path.resolve() != expected_db:
        raise ManifestError("manifest target database mismatch")
    if pointer_path is not None and pointer_path.resolve() != expected_pointer:
        raise ManifestError("manifest pointer path mismatch")
    backup_path = Path(document["backup"]["path"]).resolve()
    source = sqlite3.connect(f"file:{backup_path.as_posix()}?mode=ro", uri=True, timeout=60)
    destination = sqlite3.connect(expected_db, timeout=60)
    try:
        source.backup(destination)
        destination.commit()
    finally:
        destination.close()
        source.close()
    pointer = document["pointer"]
    if pointer["exists"]:
        expected_pointer.parent.mkdir(parents=True, exist_ok=True)
        temporary = expected_pointer.with_suffix(expected_pointer.suffix + ".tmp")
        temporary.write_text(str(pointer["value"]), encoding="utf-8")
        os.replace(temporary, expected_pointer)
    elif expected_pointer.exists():
        expected_pointer.unlink()
    restored = database_fingerprint(expected_db)
    if restored != document["database_before"]:
        raise ManifestError("restored database fingerprint mismatch")
    return {
        "ok": True,
        "generation_id": document["generation_id"],
        "database_restored": True,
        "pointer_restored": True,
        "database_fingerprint": restored,
    }

