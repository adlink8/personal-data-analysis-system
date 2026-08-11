"""Phase 4: background consolidation of knowledge units into the wiki page store.

The wiki is the top-layer consolidated surface: the backend agent periodically
reads knowledge-unit facts (``canonical_knowledge_units`` current rows), buckets
them by subject, and materializes one deterministic page body per subject into
``wiki_projection_pages``.  Version metadata (``wiki_projection_versions`` /
dependencies) is written alongside so the existing materialization and
dependency checks keep working unchanged.

Design:
- Idempotent: identical input produces an identical ``page_checksum``; a page
  whose latest stored checksum matches the freshly computed one is skipped.
- Incremental: a global source fingerprint short-circuits the whole run when no
  KU increment exists since the last consolidation.
- Fail-safe: a missing wiki store or unified DB degrades to a reported no-op;
  it never raises or blocks reads (reads fall back to read-time projection).
- Trigger: callable from a scheduler.  The pi kernel or cron may invoke the CLI
  or ``consolidate_wiki()`` on a cadence; nothing here depends on a scheduler.

Usage::

    python consolidate_wiki.py --dry-run
    python consolidate_wiki.py --write
    python consolidate_wiki.py --write --subjects "PowerShell" "工作流"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

from personal_knowledge.core.project_paths import UNIFIED_DB, WIKI_PROJECTION_DB
from personal_knowledge.wiki.derived_store import (
    ProjectionDependency,
    ProjectionPage,
    ProjectionVersion,
    SCHEMA_VERSION,
    connect_ro,
    connect_rw,
    insert_page,
    insert_version,
    latest_page,
)
from personal_knowledge.wiki.materialization import (
    dependency_manifest_checksum,
    projection_checksum,
)
from personal_knowledge.wiki.page_reader import subject_topic_id, subject_topic_key

PAGE_BODY_SCHEMA = "wiki_page_body_v1"
CONSOLIDATION_STATE = "wiki_consolidation_state"
MAX_CLAIMS_PER_PAGE = 200
MAX_EVIDENCE_REFS = 200
AUTHORITY_ID = "a.knowledge_unit"


@dataclass
class ConsolidationStats:
    subjects: int = 0
    pages_written: int = 0
    pages_skipped: int = 0
    units_loaded: int = 0
    skipped_subjects: int = 0
    global_noop: bool = False
    errors: list[str] = field(default_factory=list)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _checksum(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Load + bucket (KU layer)
# ---------------------------------------------------------------------------

def load_current_units(db_path: Path | str = UNIFIED_DB) -> list[dict[str, Any]]:
    """Load current canonical knowledge units (the deduplicated fact layer)."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT canonical_unit_id, subject, unit_type, question, answer,
                      confidence, lifecycle, version
               FROM canonical_knowledge_units
               WHERE status='current'""",
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        con.close()


def load_evidence_refs(db_path: Path | str = UNIFIED_DB) -> dict[str, list[str]]:
    """Map canonical_unit_id -> sorted, deduped evidence refs (message refs only)."""
    con = sqlite3.connect(f"file:{Path(db_path).as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            """SELECT m.canonical_unit_id AS cid, e.evidence_ref AS ref
               FROM canonical_unit_members m
               JOIN knowledge_unit_evidence e ON e.unit_id = m.member_unit_id
               ORDER BY m.canonical_unit_id, e.evidence_ref""",
        ).fetchall()
    finally:
        con.close()
    out: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        out[str(row["cid"])].append(str(row["ref"]))
    for cid in out:
        out[cid] = sorted(dict.fromkeys(out[cid]))
    return dict(out)


def bucket_by_subject(units: Iterable[Mapping[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Bucket canonical units by normalized subject (case-insensitive, trimmed).

    Mirrors the grouping intent of ``build_canonical_knowledge_units``: same
    subject rows aggregate into one consolidated wiki page.  Conflict units are
    NOT split out here — the wiki page keeps them as ``conflicts`` claims so the
    top layer surfaces them instead of hiding them.
    """
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for unit in units:
        subject = str((unit.get("subject") or "").strip())
        if not subject:
            continue
        buckets[subject.lower()].append(dict(unit))
    return dict(buckets)


# ---------------------------------------------------------------------------
# Page body construction (aggregated result only — no raw conversation text)
# ---------------------------------------------------------------------------

def _claim_from_unit(unit: Mapping[str, Any], evidence_refs: list[str]) -> dict[str, Any]:
    confidence = unit.get("confidence")
    if isinstance(confidence, float):
        import math
        confidence = None if math.isnan(confidence) else confidence
    return {
        "claim_type": "knowledge_unit",
        "unit_id": unit.get("canonical_unit_id"),
        "unit_type": unit.get("unit_type"),
        "subject": unit.get("subject"),
        "question": unit.get("question"),
        "answer": unit.get("answer"),
        "confidence": confidence,
        "lifecycle": unit.get("lifecycle"),
        "authority_ref": {
            "authority_id": AUTHORITY_ID,
            "record_type": "canonical_knowledge_unit",
            "record_id": unit.get("canonical_unit_id"),
            "checksum": None,
        },
        "evidence_refs": [{"ref": ref} for ref in evidence_refs[:8]],
    }


def build_page_body(
    subject: str, units: list[dict[str, Any]], evidence_refs_by_unit: Mapping[str, list[str]],
) -> dict[str, Any]:
    """Deterministic consolidated page body.

    Contains only aggregated result content (subject / claims / evidence refs).
    No raw conversation text, no provider output, no timestamps — so identical
    input yields an identical ``page_checksum``.
    """
    normalized = subject.strip().lower()
    unit_type_counts: dict[str, int] = defaultdict(int)
    lifecycle_counts: dict[str, int] = defaultdict(int)
    confidence_values: list[float] = []
    claims: list[dict[str, Any]] = []
    for unit in sorted(units, key=lambda item: str(item.get("canonical_unit_id"))):
        unit_type = str(unit.get("unit_type") or "unknown")
        lifecycle = str(unit.get("lifecycle") or "unknown")
        unit_type_counts[unit_type] += 1
        lifecycle_counts[lifecycle] += 1
        confidence = unit.get("confidence")
        if isinstance(confidence, (int, float)):
            confidence_values.append(float(confidence))
        claims.append(_claim_from_unit(unit, evidence_refs_by_unit.get(str(unit.get("canonical_unit_id")), [])))
        if len(claims) >= MAX_CLAIMS_PER_PAGE:
            break

    evidence_refs = sorted(dict.fromkeys(
        ref
        for claim in claims
        for ref in (row.get("ref") for row in claim.get("evidence_refs", ()) if isinstance(row, Mapping))
    ))[:MAX_EVIDENCE_REFS]
    source_fingerprint = _checksum({
        "units": [
            {
                "unit_id": unit.get("canonical_unit_id"),
                "lifecycle": unit.get("lifecycle"),
                "version": unit.get("version"),
                "answer": unit.get("answer"),
            }
            for unit in sorted(units, key=lambda item: str(item.get("canonical_unit_id")))
        ]
    })
    return {
        "schema": PAGE_BODY_SCHEMA,
        "topic": {
            "topic_id": subject_topic_id(normalized),
            "topic_type": "subject",
            "canonical_key": subject_topic_key(normalized),
            "display_label": f"subject:{normalized}",
        },
        "subject": normalized,
        "aggregation": {
            "unit_count": len(units),
            "unit_type_counts": dict(sorted(unit_type_counts.items())),
            "lifecycle_counts": dict(sorted(lifecycle_counts.items())),
            "avg_confidence": round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None,
        },
        "claims": claims,
        "evidence_refs": evidence_refs,
        "source_fingerprint": source_fingerprint,
    }


# ---------------------------------------------------------------------------
# Store writes (version metadata + page body, one transaction)
# ---------------------------------------------------------------------------

def _write_subject_page(
    con: sqlite3.Connection, store_path: Path, subject: str, body: dict[str, Any],
) -> bool:
    """Write a new immutable version + page for a subject.

    Returns True when a new page was written, False when the existing page is
    already up to date (identical checksum — no increment, no rebuild).
    """
    normalized = subject.strip().lower()
    topic_id = subject_topic_id(normalized)
    page_checksum = _checksum(body)
    page_body = _canonical_json(body)
    try:
        latest = latest_page(store_path, topic_id)
        if latest is not None and latest.page_checksum == page_checksum:
            return False
        previous_version = latest.projection_version if latest is not None else None
        version = "pv_1" if previous_version is None else f"pv_{int(previous_version.rsplit('_', 1)[-1]) + 1}"
    except (ValueError, FileNotFoundError, sqlite3.Error):
        version = "pv_1"
    deps = [
        ProjectionDependency(
            authority="knowledge_unit",
            stable_ref=normalized,
            expected_checksum=str(body.get("source_fingerprint") or page_checksum),
            order_key=f"knowledge_unit:{normalized}",
        )
    ]
    version_row = ProjectionVersion(
        topic_id=topic_id,
        topic_type="subject",
        projection_format_version=SCHEMA_VERSION,
        projection_version=version,
        projection_checksum=projection_checksum(
            topic_id=topic_id,
            topic_type="subject",
            snapshot_bindings={"knowledge_unit": normalized},
            dependencies=deps,
            source_refs={"authority_ids": [AUTHORITY_ID], "consolidation": PAGE_BODY_SCHEMA},
        ),
        generated_at=_utc_now(),
        freshness_status="fresh",
        reason_codes=(),
        snapshot_bindings={"knowledge_unit": normalized},
        dependency_manifest_checksum=dependency_manifest_checksum(deps),
    )
    insert_version(con, version_row, deps)
    insert_page(con, ProjectionPage(
        topic_id=topic_id,
        topic_type="subject",
        projection_version=version,
        page_body=page_body,
        page_checksum=page_checksum,
        generated_at=version_row.generated_at,
        snapshot_bindings={"knowledge_unit": normalized},
    ))
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _global_source_fingerprint(units: Iterable[Mapping[str, Any]]) -> str:
    return _checksum([
        {
            "unit_id": unit.get("canonical_unit_id"),
            "lifecycle": unit.get("lifecycle"),
            "version": unit.get("version"),
        }
        for unit in sorted(units, key=lambda item: str(item.get("canonical_unit_id")))
    ])


def _read_global_fingerprint(store_path: Path) -> str | None:
    try:
        con = connect_ro(store_path)
    except (FileNotFoundError, OSError, sqlite3.Error):
        return None
    try:
        row = con.execute(
            f"SELECT state_value FROM {CONSOLIDATION_STATE} WHERE state_key='global_source_fingerprint'"
        ).fetchone()
        return str(row[0]) if row is not None else None
    except sqlite3.Error:
        return None
    finally:
        con.close()


def consolidate_wiki(
    db_path: Path | str = UNIFIED_DB,
    store_path: Path | str = WIKI_PROJECTION_DB,
    *,
    write: bool = False,
    subjects: Iterable[str] = (),
    limit: int | None = None,
) -> ConsolidationStats:
    """Consolidate current canonical knowledge units into subject wiki pages.

    Idempotent and fail-safe.  ``write=False`` runs a dry run that only
    reports what would change.  When ``subjects`` is provided only those
    buckets are processed; ``limit`` caps the number of subjects processed.
    """
    store = Path(store_path)
    stats = ConsolidationStats()
    try:
        units = load_current_units(db_path)
    except (sqlite3.Error, OSError) as exc:
        stats.errors.append(f"unified_db_unavailable: {exc}")
        return stats
    stats.units_loaded = len(units)
    if not units:
        return stats

    fingerprint = _global_source_fingerprint(units)
    if write:
        try:
            con = connect_rw(store)
        except (sqlite3.Error, OSError) as exc:
            stats.errors.append(f"wiki_store_unavailable: {exc}")
            return stats
        try:
            con.execute(
                f"CREATE TABLE IF NOT EXISTS {CONSOLIDATION_STATE} "
                "(state_key TEXT PRIMARY KEY, state_value TEXT NOT NULL, updated_at TEXT NOT NULL)"
            )
        except sqlite3.Error as exc:
            stats.errors.append(f"wiki_store_schema: {exc}")
            con.close()
            return stats
        try:
            prior = _read_global_fingerprint(store)
            if prior == fingerprint:
                stats.global_noop = True
                return stats
            buckets = bucket_by_subject(units)
            evidence = load_evidence_refs(db_path)
            selected = sorted(buckets.items(), key=lambda pair: pair[0])
            if subjects:
                wanted = {str(item).strip().lower() for item in subjects}
                selected = [pair for pair in selected if pair[0] in wanted]
            if limit is not None:
                selected = selected[: max(0, int(limit))]
            for subject_key, bucket_units in selected:
                subject = subject_key
                try:
                    body = build_page_body(subject, bucket_units, evidence)
                    wrote = _write_subject_page(con, store, subject, body)
                except (sqlite3.Error, OSError) as exc:
                    stats.errors.append(f"subject_write_error:{subject}: {exc}")
                    stats.skipped_subjects += 1
                    continue
                stats.subjects += 1
                if wrote:
                    stats.pages_written += 1
                else:
                    stats.pages_skipped += 1
            con.execute(
                f"INSERT OR REPLACE INTO {CONSOLIDATION_STATE} "
                "(state_key, state_value, updated_at) VALUES ('global_source_fingerprint', ?, ?)",
                (fingerprint, _utc_now()),
            )
            con.commit()
            stats.pages_skipped = max(0, stats.subjects - stats.pages_written)
            return stats
        finally:
            con.close()

    # Dry run: report counts without touching the store.
    buckets = bucket_by_subject(units)
    selected = sorted(buckets.items(), key=lambda pair: pair[0])
    if subjects:
        wanted = {str(item).strip().lower() for item in subjects}
        selected = [pair for pair in selected if pair[0] in wanted]
    if limit is not None:
        selected = selected[: max(0, int(limit))]
    stats.subjects = len(selected)
    evidence = load_evidence_refs(db_path)
    for subject_key, bucket_units in selected:
        body = build_page_body(subject_key, bucket_units, evidence)
        checksum = _checksum(body)
        try:
            latest = latest_page(store, subject_topic_id(subject_key))
        except (FileNotFoundError, OSError, sqlite3.Error):
            latest = None
        if latest is not None and latest.page_checksum == checksum:
            stats.pages_skipped += 1
        else:
            stats.pages_written += 1
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Phase 4: consolidate KU into wiki pages")
    parser.add_argument("--db", type=Path, default=UNIFIED_DB, help="unified DB path")
    parser.add_argument("--store", type=Path, default=WIKI_PROJECTION_DB, help="wiki projection store path")
    parser.add_argument("--write", action="store_true", help="write pages (default is dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="explicit dry-run")
    parser.add_argument("--subjects", nargs="*", default=[], help="only consolidate these subjects")
    parser.add_argument("--limit", type=int, default=None, help="cap number of subjects processed")
    args = parser.parse_args(argv)
    write = bool(args.write) and not args.dry_run
    stats = consolidate_wiki(args.db, args.store, write=write, subjects=args.subjects, limit=args.limit)
    print("=" * 60)
    print("Phase 4 Wiki Consolidation")
    print("=" * 60)
    print(f"mode:            {'write' if write else 'dry-run'}")
    print(f"units loaded:    {stats.units_loaded}")
    print(f"subjects:        {stats.subjects}")
    print(f"pages written:   {stats.pages_written}")
    print(f"pages skipped:   {stats.pages_skipped}")
    print(f"global no-op:    {stats.global_noop}")
    if stats.errors:
        print("errors:")
        for error in stats.errors:
            print(f"  - {error}")
    return 1 if stats.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
