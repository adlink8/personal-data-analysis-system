"""Immutable metadata store for Wiki materialized projections.

The store is disposable and is not an authority.  It intentionally has no
columns for page text, source bodies, embeddings, provider output or evidence
content.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping


SCHEMA_VERSION = "personal_wiki_derived_store_v1"


@dataclass(frozen=True, slots=True)
class ProjectionVersion:
    topic_id: str
    topic_type: str
    projection_format_version: str
    projection_version: str
    projection_checksum: str
    generated_at: str
    freshness_status: str
    reason_codes: tuple[str, ...]
    snapshot_bindings: Mapping[str, Any]
    dependency_manifest_checksum: str


@dataclass(frozen=True, slots=True)
class ProjectionDependency:
    authority: str
    stable_ref: str
    expected_version: str | None = None
    expected_checksum: str | None = None
    expected_sequence: int | None = None
    essential: bool = True
    order_key: str = ""

    def canonical(self) -> dict[str, Any]:
        return {
            "authority": self.authority,
            "stable_ref": self.stable_ref,
            "expected_version": self.expected_version,
            "expected_checksum": self.expected_checksum,
            "expected_sequence": self.expected_sequence,
            "essential": self.essential,
            "order_key": self.order_key or f"{self.authority}:{self.stable_ref}",
        }


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _assert_derived_path(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.suffix.lower() not in {".sqlite", ".db"}:
        raise ValueError("derived_store_path_invalid")
    return resolved


def connect_rw(path: Path | str) -> sqlite3.Connection:
    """Open the dedicated derived store for schema/transaction writes only."""
    target = _assert_derived_path(Path(path))
    target.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(target)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    _ensure_schema(con)
    return con


def connect_ro(path: Path | str) -> sqlite3.Connection:
    """Open the derived store read-only with SQLite write protection enabled."""
    target = _assert_derived_path(Path(path))
    if not target.exists():
        raise FileNotFoundError(target)
    con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    con.execute("PRAGMA foreign_keys=ON")
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS wiki_projection_versions (
            topic_id TEXT NOT NULL,
            topic_type TEXT NOT NULL,
            projection_format_version TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            projection_checksum TEXT NOT NULL,
            generated_at TEXT NOT NULL,
            freshness_status TEXT NOT NULL,
            reason_codes_json TEXT NOT NULL,
            snapshot_bindings_json TEXT NOT NULL,
            dependency_manifest_checksum TEXT NOT NULL,
            PRIMARY KEY (topic_id, projection_version)
        );
        CREATE TABLE IF NOT EXISTS wiki_projection_dependencies (
            topic_id TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            authority TEXT NOT NULL,
            stable_ref TEXT NOT NULL,
            expected_version TEXT,
            expected_checksum TEXT,
            expected_sequence INTEGER,
            essential INTEGER NOT NULL,
            order_key TEXT NOT NULL,
            PRIMARY KEY (topic_id, projection_version, authority, stable_ref),
            FOREIGN KEY (topic_id, projection_version)
                REFERENCES wiki_projection_versions(topic_id, projection_version)
        );
        CREATE TABLE IF NOT EXISTS wiki_projection_invalidations (
            invalidation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT NOT NULL,
            projection_version TEXT NOT NULL,
            reason_code TEXT NOT NULL,
            generated_at TEXT NOT NULL
        );
        """
    )
    con.commit()


def insert_version(
    con: sqlite3.Connection,
    version: ProjectionVersion,
    dependencies: Iterable[ProjectionDependency],
) -> None:
    """Insert an immutable version and its complete dependency manifest."""
    deps = tuple(dependencies)
    ordered = tuple(sorted(deps, key=lambda item: (item.order_key or f"{item.authority}:{item.stable_ref}", item.authority, item.stable_ref)))
    try:
        with con:
            con.execute(
                """INSERT INTO wiki_projection_versions
                (topic_id,topic_type,projection_format_version,projection_version,
                 projection_checksum,generated_at,freshness_status,reason_codes_json,
                 snapshot_bindings_json,dependency_manifest_checksum)
                VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    version.topic_id, version.topic_type, version.projection_format_version,
                    version.projection_version, version.projection_checksum, version.generated_at,
                    version.freshness_status, _json(list(version.reason_codes)),
                    _json(dict(version.snapshot_bindings)), version.dependency_manifest_checksum,
                ),
            )
            con.executemany(
                """INSERT INTO wiki_projection_dependencies
                (topic_id,projection_version,authority,stable_ref,expected_version,
                 expected_checksum,expected_sequence,essential,order_key)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                [
                    (
                        version.topic_id, version.projection_version, item.authority,
                        item.stable_ref, item.expected_version, item.expected_checksum,
                        item.expected_sequence, int(item.essential),
                        item.order_key or f"{item.authority}:{item.stable_ref}",
                    )
                    for item in ordered
                ],
            )
    except sqlite3.IntegrityError:
        raise ValueError("projection_version_immutable") from None


def _row_to_version(row: sqlite3.Row) -> ProjectionVersion:
    return ProjectionVersion(
        topic_id=str(row["topic_id"]), topic_type=str(row["topic_type"]),
        projection_format_version=str(row["projection_format_version"]),
        projection_version=str(row["projection_version"]), projection_checksum=str(row["projection_checksum"]),
        generated_at=str(row["generated_at"]), freshness_status=str(row["freshness_status"]),
        reason_codes=tuple(json.loads(row["reason_codes_json"])),
        snapshot_bindings=json.loads(row["snapshot_bindings_json"]),
        dependency_manifest_checksum=str(row["dependency_manifest_checksum"]),
    )


def latest_version(path: Path | str, topic_id: str) -> tuple[ProjectionVersion | None, tuple[ProjectionDependency, ...]]:
    con = connect_ro(path)
    try:
        row = con.execute(
            """SELECT * FROM wiki_projection_versions
               WHERE topic_id=? ORDER BY generated_at DESC, projection_version DESC LIMIT 1""",
            (topic_id,),
        ).fetchone()
        if row is None:
            return None, ()
        version = _row_to_version(row)
        dependencies = tuple(
            ProjectionDependency(
                authority=str(item["authority"]), stable_ref=str(item["stable_ref"]),
                expected_version=item["expected_version"], expected_checksum=item["expected_checksum"],
                expected_sequence=item["expected_sequence"], essential=bool(item["essential"]),
                order_key=str(item["order_key"]),
            )
            for item in con.execute(
                """SELECT * FROM wiki_projection_dependencies
                   WHERE topic_id=? AND projection_version=? ORDER BY order_key,authority,stable_ref""",
                (version.topic_id, version.projection_version),
            ).fetchall()
        )
        return version, dependencies
    finally:
        con.close()


__all__ = [
    "ProjectionDependency", "ProjectionVersion", "SCHEMA_VERSION",
    "connect_ro", "connect_rw", "insert_version", "latest_version",
]
