"""prepare_production_delta extract floor policy tests.

Covers the C2 fix: the watermark-date floor is off by default so late-synced
historical sessions (started_at earlier than the watermark commit date but with
genuinely new refs) are queued for extraction instead of being silently dropped.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.application.knowledge.refresh_knowledge_units import (
    prepare_production_delta,
)

_PROVIDER = dict(
    provider="openai",
    endpoint="https://api.openai.com/v1",
    auth_mode="api_key",
    model="gpt-test",
)

_OLD_STARTED = "2026-01-01T10:00:00"
_RECENT_STARTED = "2026-07-20T10:00:00"
_WM_UPDATED_AT = "2026-07-15T00:00:00"


def _make_canonical_db(path: Path) -> None:
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE canonical_sessions ("
        "canonical_session_id TEXT PRIMARY KEY, agent TEXT, started_at TEXT, "
        "evidence_eligible INTEGER NOT NULL DEFAULT 1)"
    )
    con.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, "
        "content TEXT, source TEXT, role TEXT)"
    )
    con.execute(
        "INSERT INTO canonical_sessions VALUES ('s_old', 'test', ?, 1)",
        (_OLD_STARTED,),
    )
    con.execute(
        "INSERT INTO canonical_sessions VALUES ('s_recent', 'test', ?, 1)",
        (_RECENT_STARTED,),
    )
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('m_old', 's_old', 'late-synced historical session user message content', 'test', 'user')"
    )
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('m_recent', 's_recent', 'recent session user message content here ok', 'test', 'user')"
    )
    con.commit()
    con.close()


def _make_unified_db(path: Path) -> None:
    """Watermark committed at _WM_UPDATED_AT with an empty baseline inventory."""
    from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import (
        SCHEMA_SQL,
    )

    con = sqlite3.connect(path)
    con.executescript(SCHEMA_SQL)
    con.execute(
        "CREATE TABLE IF NOT EXISTS knowledge_source_watermark "
        "(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT)"
    )
    con.execute(
        "INSERT INTO knowledge_source_watermark VALUES ('committed', 'wm-checksum', ?)",
        (_WM_UPDATED_AT,),
    )
    # Baseline inventory generated before the watermark commit (empty item set)
    con.execute(
        "INSERT INTO knowledge_inventory "
        "(inventory_id, generated_at, source_db_path, source_checksum, item_count, "
        "dataset_hash) VALUES ('inv_base', '2026-07-14T00:00:00', 'x', 'wm-checksum', 0, 'h')"
    )
    con.commit()
    con.close()


def _queued_refs(db: Path, run_id: str) -> list[str]:
    con = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
    rows = con.execute(
        "SELECT evidence_ref FROM knowledge_run_items WHERE run_id=? ORDER BY position",
        (run_id,),
    ).fetchall()
    con.close()
    return [r[0] for r in rows]


def test_default_floor_off_queues_late_synced_history(tmp_path: Path) -> None:
    """Default (floor off): a late-synced historical session's new ref is queued."""
    db = tmp_path / "unified.db"
    canon = tmp_path / "canonical.db"
    _make_unified_db(db)
    _make_canonical_db(canon)

    result = prepare_production_delta(db_path=db, canonical_db=canon, **_PROVIDER)

    assert result["no_op"] is False
    assert result["extract_min_started_at"] == ""
    assert result["floor_excluded"] == 0
    assert result["extract_item_count"] == 2
    assert sorted(_queued_refs(db, result["fresh_run_id"])) == ["m_old", "m_recent"]


def test_explicit_floor_filters_and_reports_excluded(tmp_path: Path) -> None:
    """extract_since_watermark=True: the old ref is filtered and counted."""
    db = tmp_path / "unified.db"
    canon = tmp_path / "canonical.db"
    _make_unified_db(db)
    _make_canonical_db(canon)

    result = prepare_production_delta(
        db_path=db, canonical_db=canon, extract_since_watermark=True, **_PROVIDER
    )

    assert result["extract_min_started_at"] == _WM_UPDATED_AT[:10]
    assert result["floor_excluded"] == 1
    assert result["extract_item_count"] == 1
    assert _queued_refs(db, result["fresh_run_id"]) == ["m_recent"]


def test_explicit_since_floor_unchanged(tmp_path: Path) -> None:
    """Explicit --since floor keeps its behavior (wins over watermark floor)."""
    db = tmp_path / "unified.db"
    canon = tmp_path / "canonical.db"
    _make_unified_db(db)
    _make_canonical_db(canon)

    # Floor before both sessions: nothing excluded
    r1 = prepare_production_delta(
        db_path=db, canonical_db=canon, extract_min_started_at="2025-12-01", **_PROVIDER
    )
    assert r1["extract_min_started_at"] == "2025-12-01"
    assert r1["floor_excluded"] == 0
    assert r1["extract_item_count"] == 2

    # Floor between the two sessions: old one excluded
    r2 = prepare_production_delta(
        db_path=db, canonical_db=canon, extract_min_started_at="2026-07-01", **_PROVIDER
    )
    assert r2["extract_min_started_at"] == "2026-07-01"
    assert r2["floor_excluded"] == 1
    assert r2["extract_item_count"] == 1
    assert _queued_refs(db, r2["fresh_run_id"]) == ["m_recent"]
