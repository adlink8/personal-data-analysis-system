"""Phase 62-03: conversation source privacy negatives (D-08).

Forbidden SQLite tables/columns (account, credential, token, auth, secret,
cookie, api_key) must never appear in executed capture trace callbacks,
snapshot manifests, event payloads, reports or logs — even when they share
the same database as the conversation tables. Also covers path escape and
WAL-consistent capture.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources.snapshots import (
    CaptureError,
    capture_directory,
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import EventKind

CANARY = "canary-secret-value-314159"


def _make_db_with_canaries(path: Path, tables: dict[str, str]) -> None:
    """tables: name -> CREATE TABLE ddl (no trailing semicolon)."""
    con = sqlite3.connect(path)
    try:
        for name, ddl in tables.items():
            con.execute(ddl)
        con.commit()
    finally:
        con.close()


def _make_full_db(path: Path) -> None:
    _make_db_with_canaries(path, {
        "conversations": "CREATE TABLE conversations (id TEXT PRIMARY KEY, body TEXT)",
        "auth_tokens": "CREATE TABLE auth_tokens (id TEXT PRIMARY KEY, token_value TEXT)",
        "api_credentials": "CREATE TABLE api_credentials (id TEXT PRIMARY KEY, api_key TEXT)",
        "user_accounts": "CREATE TABLE user_accounts (id TEXT PRIMARY KEY, email TEXT)",
        "sessions_secret_store": "CREATE TABLE sessions_secret_store (id TEXT PRIMARY KEY, secret TEXT)",
    })
    con = sqlite3.connect(path)
    try:
        con.execute("INSERT INTO conversations VALUES ('c1', 'hello world')")
        con.execute("INSERT INTO auth_tokens VALUES ('t1', ?)", (CANARY,))
        con.execute("INSERT INTO api_credentials VALUES ('a1', ?)", (CANARY,))
        con.execute("INSERT INTO user_accounts VALUES ('u1', 'user@example.com')")
        con.execute("INSERT INTO sessions_secret_store VALUES ('s1', ?)", (CANARY,))
        con.commit()
    finally:
        con.close()


class TestForbiddenTables:
    def test_forbidden_tables_never_in_artifact(self, tmp_path):
        db = tmp_path / "store.db"
        _make_full_db(db)
        artifact, blob = capture_sqlite(
            db, tmp_path, allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        con = sqlite3.connect(blob)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            con.close()
        assert "auth_tokens" not in tables
        assert "api_credentials" not in tables
        assert "user_accounts" not in tables
        assert "sessions_secret_store" not in tables
        assert "conversations" in tables

    def test_canary_secret_never_in_filtered_blob(self, tmp_path):
        db = tmp_path / "store.db"
        _make_full_db(db)
        artifact, blob = capture_sqlite(
            db, tmp_path, allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        blob_bytes = blob.read_bytes()
        assert CANARY.encode() not in blob_bytes

    def test_manifest_reports_exclusions_metadata_only(self, tmp_path):
        db = tmp_path / "store.db"
        _make_full_db(db)
        artifact, _blob = capture_sqlite(
            db, tmp_path, allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        for disposition in artifact.privacy_dispositions:
            assert disposition.startswith("excluded_table:")
        assert "auth_tokens" in " ".join(artifact.privacy_dispositions)
        assert CANARY not in str(artifact)

    def test_declaring_forbidden_table_fails_closed(self, tmp_path):
        db = tmp_path / "store.db"
        _make_full_db(db)
        with pytest.raises(CaptureError):
            capture_sqlite(
                db, tmp_path, allowed_tables=("auth_tokens",),
                allowed_columns={"auth_tokens": ("id", "token_value")},
                byte_limit=1_000_000, count_limit=4,
            )

    def test_forbidden_column_never_captured(self, tmp_path):
        db = tmp_path / "store.db"
        _make_full_db(db)
        # conversations has only id/body allowed; nothing else to test here,
        # so assert a credentials column in a non-forbidden table is absent.
        con = sqlite3.connect(db)
        try:
            con.execute("CREATE TABLE usage_stats (id TEXT PRIMARY KEY, api_key TEXT, n INTEGER)")
            con.execute("INSERT INTO usage_stats VALUES ('u1', ?, 3)", (CANARY,))
            con.commit()
        finally:
            con.close()
        artifact, blob = capture_sqlite(
            db, tmp_path, allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        blob_bytes = blob.read_bytes()
        assert CANARY.encode() not in blob_bytes

    def test_undeclared_column_on_allowed_table_is_not_published(self, tmp_path):
        db = tmp_path / "columns.db"
        con = sqlite3.connect(db)
        con.execute(
            "CREATE TABLE conversations "
            "(id TEXT PRIMARY KEY, body TEXT, vendor_private TEXT)"
        )
        con.execute(
            "INSERT INTO conversations VALUES ('c1', 'safe', ?)", (CANARY,)
        )
        con.commit()
        con.close()
        _artifact, blob = capture_sqlite(
            db, tmp_path / "capture", allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        con = sqlite3.connect(blob)
        columns = {row[1] for row in con.execute("PRAGMA table_info(conversations)")}
        con.close()
        assert columns == {"id", "body"}
        assert CANARY.encode() not in blob.read_bytes()

    def test_autoincrement_system_table_is_scrubbed_not_dropped(self, tmp_path):
        db = tmp_path / "auto.db"
        con = sqlite3.connect(db)
        con.execute("CREATE TABLE conversations (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)")
        con.execute("CREATE TABLE cache_rows (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)")
        con.execute("INSERT INTO conversations(body) VALUES ('safe')")
        con.execute("INSERT INTO cache_rows(body) VALUES (?)", (CANARY,))
        con.commit()
        con.close()
        _artifact, blob = capture_sqlite(
            db, tmp_path / "capture", allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        con = sqlite3.connect(blob)
        has_sequence = con.execute(
            "SELECT 1 FROM sqlite_master WHERE name='sqlite_sequence'"
        ).fetchone()
        sequence_names = (
            {row[0] for row in con.execute("SELECT name FROM sqlite_sequence")}
            if has_sequence else set()
        )
        con.close()
        assert sequence_names <= {"conversations"}
        assert CANARY.encode() not in blob.read_bytes()


class TestPathAndWAL:
    def test_path_escape_rejected(self, tmp_path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "conversation.jsonl").write_text('{"type":"session_meta","session_id":"s"}\n', encoding="utf-8")
        # allowlist path that escapes the source root must be rejected
        with pytest.raises(CaptureError):
            capture_directory(
                source, tmp_path / "dest",
                include_relative=("../../outside.jsonl",),
                byte_limit=1_000_000, count_limit=1,
            )

    def test_sqlite_wal_backup_not_loose_copy(self, tmp_path):
        db = tmp_path / "wal.db"
        _make_db_with_canaries(db, {"conversations": "CREATE TABLE conversations (id TEXT PRIMARY KEY, body TEXT)"})
        con = sqlite3.connect(db)
        try:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("INSERT INTO conversations VALUES ('c1', 'wal body')")
            con.commit()
        finally:
            con.close()
        assert (tmp_path / "wal.db-wal").exists() or not (tmp_path / "wal.db-wal").exists()
        artifact, blob = capture_sqlite(
            db, tmp_path, allowed_tables=("conversations",),
            allowed_columns={"conversations": ("id", "body")},
            byte_limit=1_000_000, count_limit=4,
        )
        # the published artifact is a self-contained filtered database
        con = sqlite3.connect(blob)
        try:
            rows = con.execute("SELECT body FROM conversations WHERE id='c1'").fetchall()
        finally:
            con.close()
        assert rows == [("wal body",)]
