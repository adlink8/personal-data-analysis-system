from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from tools.migrations import remap_superseded_session_refs as migration


def _canonical_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE canonical_sessions (
            canonical_session_id TEXT PRIMARY KEY,
            primary_source TEXT, agent TEXT, started_at TEXT, ended_at TEXT,
            message_count INTEGER, user_message_count INTEGER, file_hash TEXT,
            parent_canonical_id TEXT, relationship_type TEXT, cwd TEXT,
            git_branch TEXT, model TEXT, evidence_eligible INTEGER,
            evidence_scope TEXT, merged INTEGER, lifecycle TEXT,
            superseded_by_canonical_id TEXT
        );
        CREATE TABLE canonical_messages (
            canonical_message_id TEXT PRIMARY KEY,
            canonical_session_id TEXT, source TEXT, source_message_ref TEXT,
            ordinal INTEGER, content TEXT, content_hash TEXT
        );
        CREATE TABLE session_source_links (
            link_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT,
            source_session_id TEXT, source_raw_file TEXT, match_method TEXT,
            match_confidence REAL
        );
        """
    )


def _add_session(con: sqlite3.Connection, sid: str, lifecycle: str, eligible: int, superseded_by: str | None = None) -> None:
    con.execute(
        "INSERT INTO canonical_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (sid, "agentsview", "agent", "2026-01-01", "2026-01-02", 1, 1, None,
         None, None, None, None, None, eligible, "user", 0, lifecycle, superseded_by),
    )


def _add_message(con: sqlite3.Connection, mid: str, sid: str, source: str, source_ref: str, ordinal: int, content: str) -> None:
    digest = hashlib.sha256(" ".join(content.split()).encode()).hexdigest()[:32]
    con.execute(
        "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?)",
        (mid, sid, source, source_ref, ordinal, content, digest),
    )


def _add_link(con: sqlite3.Connection, sid: str, source: str, source_sid: str, method: str) -> None:
    con.execute(
        "INSERT INTO session_source_links VALUES (?,?,?,?,?,?,?)",
        (f"link-{sid}-{source}", sid, source, source_sid, None, method, 1.0),
    )


def _unified_schema(con: sqlite3.Connection) -> None:
    con.executescript(
        """
        CREATE TABLE knowledge_unit_evidence (id INTEGER PRIMARY KEY, unit_id TEXT, evidence_ref TEXT, evidence_type TEXT);
        CREATE TABLE knowledge_units (unit_id TEXT PRIMARY KEY, source_message_ref TEXT);
        CREATE TABLE knowledge_inventory_items (id INTEGER PRIMARY KEY, evidence_ref TEXT);
        """
    )


def _fixtures(tmp_path: Path, *, missing_active_hash: bool = False, orphan_only: bool = False) -> tuple[Path, Path, Path, Path]:
    unified_path = tmp_path / "unified.sqlite"
    current_path = tmp_path / "current.sqlite"
    old_path = tmp_path / "old.sqlite"
    baseline_path = tmp_path / "baseline.json"

    with sqlite3.connect(unified_path) as con:
        _unified_schema(con)
        if orphan_only:
            refs = ["cm|preexisting"]
        else:
            refs = ["cm|superseded", "cm|dup-member"]
        con.execute("INSERT INTO knowledge_unit_evidence VALUES (1,'u1',?,'message')", (refs[0],))
        con.execute("INSERT INTO knowledge_units VALUES ('u1',?)", (refs[0],))
        con.execute("INSERT INTO knowledge_inventory_items VALUES (1,?)", (refs[0],))
        if not orphan_only:
            con.execute("INSERT INTO knowledge_unit_evidence VALUES (2,'u2',?,'message')", (refs[1],))
            con.execute("INSERT INTO knowledge_units VALUES ('u2',?)", (refs[1],))
            con.execute("INSERT INTO knowledge_inventory_items VALUES (2,?)", (refs[1],))
        con.commit()

    for path in (current_path, old_path):
        with sqlite3.connect(path) as con:
            _canonical_schema(con)
            _add_session(con, "cs|active", "active", 1)
            _add_link(con, "cs|active", "agentsview", "av-active", "single_source")
            if path == current_path and not orphan_only:
                _add_link(con, "cs|active", "legacy", "legacy-old", "source_mapping")
            _add_message(con, "cm|active", "cs|active", "agentsview", "av:0", 1, "same content")
            if path == old_path:
                _add_session(con, "cs|old", "active", 1)
                _add_link(con, "cs|old", "legacy", "legacy-old", "single_source")
                _add_message(con, "cm|dup-member", "cs|old", "legacy", "legacy:legacy-old:0", 1, "same content")
                _add_message(con, "cm|legacy-baseline", "cs|old", "legacy", "legacy:legacy-old:1", 2, "baseline")
            else:
                _add_session(con, "cs|superseded", "superseded", 0, "cs|active")
                _add_message(con, "cm|superseded", "cs|superseded", "legacy", "legacy:legacy-old:0", 1, "same content" if not missing_active_hash else "different")
            con.commit()
    baseline_path.write_text(json.dumps({"dup_groups_legacy_av": 1, "evidence_refs_unresolved_baseline": 1}), encoding="utf-8")
    return unified_path, current_path, old_path, baseline_path


def _run(unified: Path, current: Path, old: Path, baseline: Path, write: bool = False) -> dict:
    args = ["--old-canonical-db", str(old), "--unified-db", str(unified), "--canonical-db", str(current), "--baseline-json", str(baseline)]
    if write:
        args.insert(0, "--write")
    with sqlite3.connect(unified) as u, migration._ro_connect(current) as c, migration._ro_connect(old) as o:
        plan = migration.plan_remap(u, c, o)
        changed = migration.apply_remap(u, plan) if write else None
        if write:
            u.commit()
        return migration._summary(plan, write, changed)


def test_superseded_ref_remapped(tmp_path: Path) -> None:
    unified, current, old, baseline = _fixtures(tmp_path)
    # One ref points to a current superseded row; the other is an old-only legacy member.
    result = _run(unified, current, old, baseline, write=False)
    assert result["remapped_evidence"] == 2


def test_orphan_kept_and_counted(tmp_path: Path) -> None:
    unified, current, old, baseline = _fixtures(tmp_path, missing_active_hash=True)
    result = _run(unified, current, old, baseline, write=False)
    assert result["remap_orphans"] == 1
    with sqlite3.connect(unified) as con:
        assert con.execute("SELECT COUNT(*) FROM knowledge_unit_evidence WHERE evidence_ref='cm|superseded'").fetchone()[0] == 1


def test_preexisting_orphan_separated(tmp_path: Path) -> None:
    unified, current, old, baseline = _fixtures(tmp_path, orphan_only=True)
    result = _run(unified, current, old, baseline, write=False)
    assert result["remap_orphans"] == 0
    assert result["preexisting_orphans"] == 1


def test_dry_run_no_write(tmp_path: Path) -> None:
    unified, current, old, baseline = _fixtures(tmp_path)
    before = unified.read_bytes()
    _run(unified, current, old, baseline, write=False)
    assert unified.read_bytes() == before


def test_idempotent_no_op(tmp_path: Path) -> None:
    unified, current, old, baseline = _fixtures(tmp_path)
    _run(unified, current, old, baseline, write=True)
    result = _run(unified, current, old, baseline, write=False)
    assert result["no_op"] is True
