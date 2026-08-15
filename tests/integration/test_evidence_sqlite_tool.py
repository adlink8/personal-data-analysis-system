"""Phase 61 Wave 0: bounded evidence SQLite Tool - integration tests.

HARNESS-03 / T-61-SQL-01 / T-61-AUTH-01. Uses only temporary redacted canonical
conversation fixtures and baseline fingerprints. Never touches live data/ or
var/ databases. Success, rejection and timeout must not change the database
fingerprint or the active pointer.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from pathlib import Path

import pytest

from personal_knowledge.services.evidence_sqlite_tool import (
    DATABASE_ID,
    DESCRIPTOR_VERSION,
    EVIDENCE_MESSAGES_PARAMETERS,
    EVIDENCE_SQLITE_OPERATION,
    EVIDENCE_SQLITE_RECEIPT_SCHEMA,
    EVIDENCE_SQLITE_SCHEMA,
    LEASE_SKILL_ID,
    MAX_BYTES,
    MAX_ROWS,
    PRIVACY_CEILING,
    QUERY_ID,
    TIMEOUT_MS,
    EvidenceSqliteError,
    EvidenceSqliteTool,
    database_fingerprint,
    derive_statement_display,
    knowledge_research_checksum,
    query_checksum,
)

SESSION_ID = "codex:session-123"
SENTINEL = "SENTINEL_SECRET=supersecretvalue-9f2a"


def _make_canonical_fixture(db: Path, *, message_count: int = 5) -> str:
    """Build a temporary redacted canonical conversation fixture."""
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    cur.execute("PRAGMA user_version=61")
    cur.execute(
        """CREATE TABLE canonical_sessions (
            canonical_session_id TEXT PRIMARY KEY, primary_source TEXT NOT NULL,
            agent TEXT, started_at TEXT, ended_at TEXT, message_count INTEGER,
            user_message_count INTEGER, file_hash TEXT, parent_canonical_id TEXT,
            relationship_type TEXT, cwd TEXT, git_branch TEXT, model TEXT,
            evidence_eligible INTEGER NOT NULL DEFAULT 1,
            evidence_scope TEXT NOT NULL DEFAULT 'user',
            merged INTEGER NOT NULL DEFAULT 0,
            lifecycle TEXT NOT NULL DEFAULT 'active',
            superseded_by_canonical_id TEXT)"""
    )
    cur.execute(
        """CREATE TABLE canonical_messages (
            canonical_message_id TEXT PRIMARY KEY,
            canonical_session_id TEXT NOT NULL REFERENCES canonical_sessions(canonical_session_id),
            source TEXT NOT NULL, source_message_ref TEXT, ordinal INTEGER NOT NULL,
            role TEXT NOT NULL, content TEXT, content_length INTEGER, timestamp TEXT,
            model TEXT, is_system INTEGER NOT NULL DEFAULT 0,
            is_sidechain INTEGER NOT NULL DEFAULT 0, content_hash TEXT,
            evidence_scope TEXT NOT NULL DEFAULT 'user')"""
    )
    cur.execute(
        """CREATE TABLE canonical_tool_events (
            canonical_tool_id TEXT PRIMARY KEY,
            canonical_session_id TEXT NOT NULL REFERENCES canonical_sessions(canonical_session_id),
            source TEXT NOT NULL, source_kind TEXT NOT NULL, tool_name TEXT,
            category TEXT, status TEXT, call_index INTEGER, subagent_session_id TEXT,
            content_length INTEGER, timestamp TEXT)"""
    )
    cur.execute(
        """CREATE TABLE session_source_links (
            link_id TEXT PRIMARY KEY,
            canonical_session_id TEXT NOT NULL REFERENCES canonical_sessions(canonical_session_id),
            source TEXT NOT NULL, source_session_id TEXT NOT NULL,
            source_raw_file TEXT, match_method TEXT NOT NULL,
            match_confidence TEXT NOT NULL DEFAULT 'strong')"""
    )
    cur.execute(
        "INSERT INTO canonical_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            SESSION_ID, "agentsview", "codex", "2026-08-01T00:00:00Z", "2026-08-01T01:00:00Z",
            message_count, 1, "file-hash-1", None, "main", None, None, None,
            1, "user", 0, "active", None,
        ),
    )
    for i in range(1, message_count + 1):
        ts = f"2026-08-01T00:{i:02d}:00Z"
        role = "user" if i % 2 else "assistant"
        content = f"redacted fixture message {i} {SENTINEL}"
        cur.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"msg-{i}", SESSION_ID, "agentsview", f"av:{i}", i, role, content,
             len(content), ts, "gpt-4o", 0, 0, f"hash-{i}", "user"),
        )
    cur.execute(
        "INSERT INTO canonical_tool_events VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("tool-1", SESSION_ID, "agentsview", "tool_calls", "knowledge.search",
         "retrieval", "success", 0, None, 10, "2026-08-01T00:02:00Z"),
    )
    cur.execute(
        "INSERT INTO session_source_links VALUES (?,?,?,?,?,?,?)",
        ("link-1", SESSION_ID, "agentsview", "av-session-1",
         "agentsview/sessions.db", "source_mapping", "strong"),
    )
    con.commit()
    con.close()
    return SESSION_ID


def _descriptor(**overrides: object) -> dict:
    base: dict = {
        "database_id": DATABASE_ID,
        "query_id": QUERY_ID,
        "version": DESCRIPTOR_VERSION,
        "parameters": {"session_id": SESSION_ID, "after": "2026-08-01T00:00:00Z", "limit": 50},
        "scope": {"session_id": SESSION_ID},
        "binding": "binding-integration",
        "skill_id": LEASE_SKILL_ID,
        "supporting_skills": [],
        "manifest_checksum": knowledge_research_checksum(),
        "privacy_ceiling": PRIVACY_CEILING,
    }
    base.update(overrides)
    return base


def _pointer_fingerprint(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Approved execution and receipt completeness
# ---------------------------------------------------------------------------


def test_approved_query_returns_bounded_rows_and_complete_receipt(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=5)
    tool = EvidenceSqliteTool(db_path=db)

    result = tool.invoke(_descriptor())

    assert result["schema_version"] == EVIDENCE_SQLITE_SCHEMA
    assert result["operation"] == EVIDENCE_SQLITE_OPERATION
    assert result["ok"] is True and result["status"] == "success"
    assert result["query_id"] == QUERY_ID
    assert result["descriptor_version"] == DESCRIPTOR_VERSION
    assert result["database_id"] == DATABASE_ID
    assert result["row_count"] == 5
    assert result["limit"] == MAX_ROWS
    assert result["truncated"] is False
    assert result["bytes"] > 0
    assert 0 <= result["duration_ms"] < 60_000
    # deterministic, server-derived statement_display bound by checksum
    assert result["statement_display"] == derive_statement_display(QUERY_ID, EVIDENCE_MESSAGES_PARAMETERS)
    assert result["parameter_names"] == sorted(EVIDENCE_MESSAGES_PARAMETERS)
    assert result["query_checksum"] == query_checksum(
        query_id=result["query_id"], version=result["descriptor_version"],
        parameter_names=result["parameter_names"], statement_display=result["statement_display"],
    )
    # rows are metadata-only evidence-safe projections
    assert len(result["rows"]) == 5
    row = result["rows"][0]
    assert set(row) == {"message_id", "session_id", "ordinal", "role", "timestamp", "source_ref"}
    assert all("content" not in r for r in result["rows"])
    # binding: database/source/schema/snapshot/freshness identity
    binding = result["binding"]
    assert binding["database_id"] == DATABASE_ID and binding["source"] == "canonical"
    assert len(binding["schema_checksum"]) == 16
    assert binding["snapshot_id"].startswith("snapshot:")
    assert isinstance(binding["freshness"], dict)
    # receipt carries identity/freshness/checksum/truncation
    receipt = result["receipt"]
    assert receipt["receipt_schema"] == EVIDENCE_SQLITE_RECEIPT_SCHEMA
    assert receipt["receipt_id"].startswith("evidence:")
    assert receipt["identity"] == f"{DATABASE_ID}:canonical"
    assert receipt["freshness"] == binding["freshness"]["latest_message_timestamp"]
    assert receipt["query_checksum"] == result["query_checksum"]
    assert receipt["truncated"] is False
    assert receipt["status"] == "success"


def test_active_v2_authority_denies_legacy_session_and_scopes_freshness(
    tmp_path: Path,
) -> None:
    db = tmp_path / "coexist-canonical.sqlite"
    _make_canonical_fixture(db, message_count=2)
    v2_session = "v2|gen|session"
    con = sqlite3.connect(db)
    try:
        con.execute(
            "INSERT INTO canonical_sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                v2_session, "legacy", "chatgpt", "2026-07-01", None, 1, 1,
                "v2-file", None, "main", None, None, None, 1, "user", 0,
                "active", None,
            ),
        )
        con.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                "v2|gen|message", v2_session, "legacy", "v2:1", 1, "user",
                "safe v2 body", 12, "2026-07-01T00:01:00Z", None, 0, 0,
                "v2-hash", "user",
            ),
        )
        con.execute(
            "CREATE TABLE ce_generation_authority ("
            "generation_id TEXT PRIMARY KEY, active INTEGER, updated_at TEXT)"
        )
        con.execute(
            "INSERT INTO ce_generation_authority VALUES ('gen', 1, '2026-08-15')"
        )
        con.commit()
    finally:
        con.close()
    tool = EvidenceSqliteTool(db_path=db)

    with pytest.raises(EvidenceSqliteError) as exc:
        tool.invoke(_descriptor())
    assert exc.value.code == "scope_denied"

    result = tool.invoke(_descriptor(
        parameters={"session_id": v2_session, "after": None, "limit": 5},
        scope={"session_id": v2_session},
    ))
    assert [row["message_id"] for row in result["rows"]] == ["v2|gen|message"]
    assert result["receipt"]["freshness"] == "2026-07-01T00:01:00Z"


def test_result_envelope_contains_no_physical_schema_or_sentinel(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=5)
    tool = EvidenceSqliteTool(db_path=db)

    result = tool.invoke(_descriptor())
    blob = json.dumps(result, ensure_ascii=False).lower()
    for forbidden in (
        SENTINEL.lower(), "canonical_messages", "canonical_sessions", "sqlite_master",
        "select ", "from canonical", "where", "join", "pragma",
        "codex:session-123;", "insert into", "drop table",
    ):
        assert forbidden not in blob, f"leak detected: {forbidden}"


def test_after_filter_and_limit_are_respected(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=5)
    tool = EvidenceSqliteTool(db_path=db)

    after = tool.invoke(_descriptor(parameters={
        "session_id": SESSION_ID, "after": "2026-08-01T00:03:00Z", "limit": 2,
    }))
    assert after["row_count"] == 2
    assert [r["ordinal"] for r in after["rows"]] == [3, 4]
    assert after["truncated"] is True  # more matches exist than the limit allows

    limited = tool.invoke(_descriptor(parameters={
        "session_id": SESSION_ID, "after": None, "limit": 3,
    }))
    assert limited["row_count"] == 3
    assert [r["ordinal"] for r in limited["rows"]] == [1, 2, 3]
    assert limited["truncated"] is True


# ---------------------------------------------------------------------------
# Bounds: rows / bytes / time
# ---------------------------------------------------------------------------


def test_row_ceiling_enforces_50_rows(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=60)
    tool = EvidenceSqliteTool(db_path=db)

    result = tool.invoke(_descriptor())
    assert result["row_count"] == MAX_ROWS == 50
    assert result["truncated"] is True
    assert len(result["rows"]) == 50


def test_byte_ceiling_truncates_by_bytes(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=10)
    tool = EvidenceSqliteTool(db_path=db, max_bytes=90)

    result = tool.invoke(_descriptor())
    assert result["row_count"] < 10
    assert result["truncated"] is True
    assert result["bytes"] <= 90
    assert len(result["rows"]) == result["row_count"]


def test_timeout_rejects_without_fingerprint_change(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=3)
    before = database_fingerprint(db)
    tool = EvidenceSqliteTool(db_path=db, timeout_ms=1, sleep_hook=lambda _seconds: time.sleep(0.15))

    with pytest.raises(EvidenceSqliteError) as exc:
        tool.invoke(_descriptor())
    assert exc.value.code == "query_timeout"
    assert database_fingerprint(db) == before


# ---------------------------------------------------------------------------
# Negative / fail-closed invariants at the real adapter
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"query_id": "unknown.query.v9"},
        {"query_id": "DROP TABLE canonical_messages"},
        {"database_id": "../../var/db/personal_system.sqlite"},
        {"parameters": {"session_id": SESSION_ID, "after": "x; PRAGMA journal_mode=WAL", "limit": 10}},
        {"parameters": {"session_id": SESSION_ID, "after": "2026-08-01T00:00:00Z", "limit": 51}},
        {"scope": {"project": "anything"}},
        {"skill_id": "system.diagnosis"},
        {"supporting_skills": ["knowledge.maintenance"]},
        {"manifest_checksum": "0" * 64},
        {"privacy_ceiling": "R0"},
        {"binding": None},
    ],
)
def test_negative_requests_reject_without_fingerprint_change(tmp_path: Path, overrides: dict) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=3)
    before = database_fingerprint(db)
    tool = EvidenceSqliteTool(db_path=db)

    with pytest.raises(EvidenceSqliteError):
        tool.invoke(_descriptor(**overrides))
    assert database_fingerprint(db) == before


def test_missing_database_rejects_and_leaves_everything_unchanged(tmp_path: Path) -> None:
    missing = tmp_path / "does-not-exist.sqlite"
    tool = EvidenceSqliteTool(db_path=missing)
    with pytest.raises(EvidenceSqliteError) as exc:
        tool.invoke(_descriptor())
    assert exc.value.code == "database_unavailable"
    assert not missing.exists()


def test_schema_gate_failure_rejects(tmp_path: Path) -> None:
    db = tmp_path / "broken.sqlite"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE canonical_sessions (canonical_session_id TEXT)")
    con.execute("CREATE TABLE unrelated (x TEXT)")
    con.commit()
    con.close()
    tool = EvidenceSqliteTool(db_path=db)
    before = database_fingerprint(db)
    with pytest.raises(EvidenceSqliteError) as exc:
        tool.invoke(_descriptor())
    assert exc.value.code == "schema_gate_failed"
    assert database_fingerprint(db) == before


def test_success_and_rejection_do_not_touch_active_pointer(tmp_path: Path) -> None:
    db = tmp_path / "canonical.sqlite"
    _make_canonical_fixture(db, message_count=3)
    pointer = tmp_path / "knowledge_index_active.txt"
    pointer.write_text("canonical:snapshot-abc-123", encoding="utf-8")
    before = _pointer_fingerprint(pointer)

    tool = EvidenceSqliteTool(db_path=db)
    tool.invoke(_descriptor())
    assert _pointer_fingerprint(pointer) == before

    with pytest.raises(EvidenceSqliteError):
        tool.invoke(_descriptor(query_id="unknown.query.v9"))
    assert _pointer_fingerprint(pointer) == before
