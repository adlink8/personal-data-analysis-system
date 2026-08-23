"""Phase 15 Wave 3：knowledge_unit_evidence backfill from source_message_ref."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.application.knowledge.backfill_knowledge_unit_evidence import (  # noqa: E402
    coverage_stats,
    find_candidates,
    insert_evidence,
    run_backfill,
    validate_refs,
)


def _seed_ku_db(path: Path) -> Path:
    con = sqlite3.connect(str(path))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs "
        "(run_id, run_type, generated_at, input_hash, schema_version, status) "
        "VALUES ('run1','extraction','2026-01-01','h','v1','staging')"
    )
    # u1: has evidence already
    # u2: missing evidence, valid ref
    # u3: missing evidence, valid ref
    # u4: missing evidence, empty ref
    # u5: missing evidence, invalid ref (not in canon)
    rows = [
        ("u1", "cm|ok1", "already linked"),
        ("u2", "cm|ok2", "need fill"),
        ("u3", "cm|ok3", "need fill"),
        ("u4", "", "no ref"),
        ("u5", "cm|missing", "bad ref"),
    ]
    for uid, ref, _ in rows:
        con.execute(
            "INSERT INTO knowledge_units "
            "(unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                uid,
                "run1",
                "preference",
                "s",
                f"q-{uid}",
                f"a-{uid}",
                0.9,
                "quote",
                "staging",
                "2026-01-01",
                ref,
            ),
        )
    con.execute(
        "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u1','cm|ok1')"
    )
    con.commit()
    con.close()
    return path


def _seed_canon_db(path: Path) -> Path:
    con = sqlite3.connect(str(path))
    con.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, "
        "source_message_ref TEXT, ordinal INTEGER, role TEXT, content TEXT, "
        "content_length INTEGER, timestamp TEXT, model TEXT, is_system INTEGER, "
        "is_sidechain INTEGER, content_hash TEXT, evidence_scope TEXT)"
    )
    for mid in ("cm|ok1", "cm|ok2", "cm|ok3"):
        con.execute(
            "INSERT INTO canonical_messages "
            "(canonical_message_id, canonical_session_id, source, source_message_ref, "
            "ordinal, role, content, content_length, timestamp, is_system, is_sidechain, "
            "content_hash, evidence_scope) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (mid, "cs1", "agentsview", mid, 1, "user", "hello world content long enough", 30,
             "2026-01-01", 0, 0, "h", "user"),
        )
    con.commit()
    con.close()
    return path


def test_coverage_stats(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    con = sqlite3.connect(str(db))
    stats = coverage_stats(con)
    con.close()
    assert stats["total_units"] == 5
    assert stats["units_with_evidence"] == 1
    assert stats["units_without_evidence"] == 4
    assert stats["units_without_evidence_with_ref"] == 3  # u2,u3,u5
    assert stats["coverage"] == pytest.approx(0.2)


def test_find_candidates_skips_existing_and_empty(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    con = sqlite3.connect(str(db))
    cands = find_candidates(con)
    con.close()
    ids = {u for u, _ in cands}
    assert ids == {"u2", "u3", "u5"}


def test_validate_refs_splits_valid_invalid(tmp_path: Path) -> None:
    _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    cands = [("u2", "cm|ok2"), ("u3", "cm|ok3"), ("u5", "cm|missing")]
    result = validate_refs(cands, canon)
    assert result["canon_available"] is True
    assert {u for u, _ in result["validated"]} == {"u2", "u3"}
    assert {u for u, _ in result["invalid"]} == {"u5"}
    assert result["valid_refs"] == 2
    assert result["invalid_refs"] == 1


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    report = run_backfill(db_path=db, canon_db=canon, write=False)
    assert report["ok"] is True
    assert report["mode"] == "dry-run"
    assert report["candidates_validated"] == 2
    assert report["recommendation"] == "safe_to_write"
    con = sqlite3.connect(str(db))
    n = con.execute("SELECT COUNT(*) FROM knowledge_unit_evidence").fetchone()[0]
    con.close()
    assert n == 1  # unchanged


def test_write_inserts_only_validated(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    # preserve answers
    con = sqlite3.connect(str(db))
    answers_before = {
        r[0]: r[1]
        for r in con.execute("SELECT unit_id, answer FROM knowledge_units")
    }
    con.close()

    report = run_backfill(db_path=db, canon_db=canon, write=True)
    assert report["ok"] is True
    assert report["mode"] == "write"
    assert report["inserted"] == 2
    assert report["after"]["units_with_evidence"] == 3
    assert report["after"]["coverage"] == pytest.approx(0.6)

    con = sqlite3.connect(str(db))
    rows = con.execute(
        "SELECT unit_id, evidence_ref FROM knowledge_unit_evidence ORDER BY unit_id"
    ).fetchall()
    assert rows == [("u1", "cm|ok1"), ("u2", "cm|ok2"), ("u3", "cm|ok3")]
    # no invalid ref inserted
    bad = con.execute(
        "SELECT COUNT(*) FROM knowledge_unit_evidence WHERE evidence_ref='cm|missing'"
    ).fetchone()[0]
    assert bad == 0
    answers_after = {
        r[0]: r[1]
        for r in con.execute("SELECT unit_id, answer FROM knowledge_units")
    }
    assert answers_after == answers_before
    con.close()


def test_write_is_idempotent(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    r1 = run_backfill(db_path=db, canon_db=canon, write=True)
    r2 = run_backfill(db_path=db, canon_db=canon, write=True)
    assert r1["inserted"] == 2
    assert r2["inserted"] == 0
    assert r2["after"]["units_with_evidence"] == 3


def test_never_deletes_existing_evidence(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    run_backfill(db_path=db, canon_db=canon, write=True)
    con = sqlite3.connect(str(db))
    still = con.execute(
        "SELECT evidence_ref FROM knowledge_unit_evidence WHERE unit_id='u1'"
    ).fetchone()
    con.close()
    assert still is not None
    assert still[0] == "cm|ok1"


def test_limit_caps_candidates(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    canon = _seed_canon_db(tmp_path / "canon.sqlite")
    report = run_backfill(db_path=db, canon_db=canon, write=False, limit=1)
    assert report["candidates_total"] == 1


def test_insert_evidence_or_ignore(tmp_path: Path) -> None:
    db = _seed_ku_db(tmp_path / "ku.sqlite")
    con = sqlite3.connect(str(db))
    n1 = insert_evidence(con, [("u1", "cm|ok1"), ("u2", "cm|ok2")])
    con.commit()
    n2 = insert_evidence(con, [("u1", "cm|ok1"), ("u2", "cm|ok2")])
    con.commit()
    con.close()
    assert n1 == 1  # only u2 new (u1 already existed)
    assert n2 == 0
