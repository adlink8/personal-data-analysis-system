"""P2-3: Cursor session-level started_at/ended_at extraction (RED -> GREEN).

Cursor adapts two supported native shapes: JSONL transcripts and machine-local
sqlite thread/message stores. Both must surface the session-context
timestamps added to the public AdaptedSession contract:

  - JSONL path: started_at = first row timestamp, ended_at = last row timestamp.
  - sqlite path: started_at = thread created_at, ended_at = last observed
    message created_at.

Fixtures are synthetic shapes driven through the real capture seam.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import cursor
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_file,
    capture_sqlite,
)


def _capture_jsonl(tmp_path: Path, rows: list[dict]):
    src = tmp_path / "thread.jsonl"
    src.write_text(chr(10).join(json.dumps(r) for r in rows) + chr(10), encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / "capture", relative_path="thread.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )
    return artifact, blob.parent


class TestCursorJsonlSessionTimestamps:
    def test_started_at_first_row_ended_at_last_row(self, tmp_path):
        rows = [
            {"role": "user", "message": {"content": "hello"},
             "timestamp": "2026-07-01T10:00:00Z"},
            {"role": "assistant", "message": {"content": "world"},
             "timestamp": "2026-07-01T10:00:05Z"},
        ]
        artifact, root = _capture_jsonl(tmp_path, rows)
        assert cursor.detect(artifact, artifact_root=root)
        result = cursor.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].started_at == "2026-07-01T10:00:00Z"
        assert result.sessions[0].ended_at == "2026-07-01T10:00:05Z"

    def test_no_timestamps_yield_none(self, tmp_path):
        rows = [
            {"role": "user", "message": {"content": "hello"}},
            {"role": "assistant", "message": {"content": "world"}},
        ]
        artifact, root = _capture_jsonl(tmp_path, rows)
        result = cursor.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        assert result.sessions[0].started_at is None
        assert result.sessions[0].ended_at is None


class TestCursorSqliteSessionTimestamps:
    def _adapt(self, tmp_path: Path):
        src = tmp_path / "cursor.db"
        con = sqlite3.connect(src)
        try:
            con.execute("CREATE TABLE threads (id TEXT PRIMARY KEY, title TEXT, created_at TEXT)")
            con.execute("INSERT INTO threads VALUES ('t1', 'session title', '2026-07-01T10:00:00Z')")
            con.execute("CREATE TABLE messages (id TEXT PRIMARY KEY, thread_id TEXT, role TEXT, content TEXT, created_at TEXT)")
            con.execute("INSERT INTO messages VALUES ('m1', 't1', 'user', 'u', '2026-07-01T10:00:00Z')")
            con.execute("INSERT INTO messages VALUES ('m2', 't1', 'assistant', 'a', '2026-07-01T10:00:02Z')")
            con.commit()
        finally:
            con.close()
        artifact, root = capture_sqlite(
            src, tmp_path / "capture",
            allowed_tables=("threads", "messages"),
            allowed_columns={
                "threads": ("id", "title", "created_at"),
                "messages": ("id", "thread_id", "role", "content", "created_at"),
            },
            byte_limit=1_000_000, count_limit=2,
        )
        assert cursor.detect(artifact, artifact_root=root.parent)
        return cursor.adapt(SourceArtifactSet((artifact,)), artifact_root=root.parent)

    def test_thread_started_at_from_created_at(self, tmp_path):
        result = self._adapt(tmp_path)
        assert len(result.sessions) == 1
        assert result.sessions[0].started_at == "2026-07-01T10:00:00Z"

    def test_thread_ended_at_from_last_message(self, tmp_path):
        result = self._adapt(tmp_path)
        assert result.sessions[0].ended_at == "2026-07-01T10:00:02Z"
