"""Phase 62-12: ZCode adapter timestamp normalization (F12 seam).

The shared seam time_utils.normalize_timestamp must run on every native
timestamp that flows into occurred_at / started_at / ended_at from the zcode
adapter (live session/message/part and canonical
conversation_traces/conversation_parts shapes), so epoch-millisecond values
never leak into ce_events / compatibility projections verbatim.

These fixtures drive the real capture seam (capture_sqlite) and the zcode
detect/adapt boundary, mirroring the style of
test_zcode_antigravity_context_extraction.py. Expected ISO values were
computed locally via normalize_timestamp before being hardcoded here:

  "1775638723463" -> "2026-04-08T08:58:43.463Z"  (reference value)
  "1775638724000" -> "2026-04-08T08:58:44Z"
  "1775638725000" -> "2026-04-08T08:58:45Z"

Also covered: pre-existing ISO "...Z" strings pass through unchanged (already
canonical), and None stays None (never the string "None").
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import zcode
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import EventKind

ZCODE_ALLOWED_TABLES = ("session", "message", "part")
ZCODE_ALLOWED_COLUMNS = {
    "session": ("id", "parent_id", "title", "time_created", "time_updated",
                "time_compacting", "trace_id", "cwd"),
    "message": ("id", "session_id", "time_created", "time_updated", "data", "sequence"),
    "part": ("id", "message_id", "session_id", "time_created", "time_updated",
             "data", "sequence"),
}

CANONICAL_ALLOWED_TABLES = ("conversation_traces", "conversation_parts")
CANONICAL_ALLOWED_COLUMNS = {
    "conversation_traces": ("trace_id", "title", "created_at"),
    "conversation_parts": ("part_id", "trace_id", "turn_id", "part_type",
                           "role", "content", "created_at"),
}

START_EPOCH = "1775638723463"
MID_EPOCH = "1775638724000"
END_EPOCH = "1775638725000"
START_ISO = "2026-04-08T08:58:43.463Z"
MID_ISO = "2026-04-08T08:58:44Z"
END_ISO = "2026-04-08T08:58:45Z"

ISO_TEST = "2026-07-01T10:00:01Z"
ISO_START = "2026-07-01T10:00:00Z"


def _capture(db: Path, tmp_path: Path, *, allowed_tables, allowed_columns):
    artifact, blob = capture_sqlite(
        db, tmp_path, allowed_tables=allowed_tables,
        allowed_columns=allowed_columns, byte_limit=1_000_000, count_limit=8,
    )
    return artifact, blob.parent


def _adapt(db: Path, tmp_path: Path, *, allowed_tables, allowed_columns) -> zcode.AdaptationResult:
    artifact, root = _capture(
        db, tmp_path, allowed_tables=allowed_tables, allowed_columns=allowed_columns,
    )
    return zcode.adapt(SourceArtifactSet(artifacts=(artifact,)), artifact_root=root)


def _events_of(result, kind):
    return [e for e in result.events if e.kind is kind]


# --------------------------------------------------------------------- live shape

def _make_live_epoch_db(path: Path) -> None:
    """Live session/message/part with TEXT epoch-millisecond digit strings."""
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE session (
                id TEXT, parent_id TEXT, title TEXT, time_created TEXT,
                time_updated TEXT, time_compacting TEXT, trace_id TEXT, cwd TEXT
            );
            CREATE TABLE message (
                id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT,
                data TEXT, sequence INTEGER
            );
            CREATE TABLE part (
                id TEXT, message_id TEXT, session_id TEXT, time_created TEXT,
                time_updated TEXT, data TEXT, sequence INTEGER
            );
            """
        )
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
                    ("S1", None, "epoch session", START_EPOCH,
                     None, None, "TR1", "/work/main"))
        con.executemany(
            "INSERT INTO message VALUES (?,?,?,?,?,?)",
            [
                # m2 carries the assistant role so p2 maps to ASSISTANT_MESSAGE.
                ("m1", "S1", START_EPOCH, None,
                 json.dumps({"role": "user"}), 1),
                ("m2", "S1", MID_EPOCH, None,
                 json.dumps({"role": "assistant"}), 2),
            ],
        )
        con.executemany(
            "INSERT INTO part VALUES (?,?,?,?,?,?,?)",
            [
                ("p1", "m1", "S1", START_EPOCH, None,
                 json.dumps({"type": "text", "text": "epoch ms user prompt"}), 1),
                # p2 has a later time_updated: the session end must fold to it.
                ("p2", "m2", "S1", MID_EPOCH, END_EPOCH,
                 json.dumps({"type": "text", "text": "epoch ms assistant answer"}), 2),
            ],
        )
        con.commit()
    finally:
        con.close()


def _make_live_int_db(path: Path) -> None:
    """Live shape with native INTEGER epoch-millisecond values."""
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE session (
                id TEXT, parent_id TEXT, title TEXT, time_created INTEGER,
                time_updated INTEGER, time_compacting INTEGER, trace_id TEXT, cwd TEXT
            );
            CREATE TABLE message (
                id TEXT, session_id TEXT, time_created INTEGER, time_updated INTEGER,
                data TEXT, sequence INTEGER
            );
            CREATE TABLE part (
                id TEXT, message_id TEXT, session_id TEXT, time_created INTEGER,
                time_updated INTEGER, data TEXT, sequence INTEGER
            );
            """
        )
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
                    ("S1", None, "int epoch session", int(START_EPOCH),
                     None, None, "TR1", "/work/main"))
        con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                    ("m1", "S1", int(START_EPOCH), None,
                     json.dumps({"role": "user"}), 1))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)",
                    ("p1", "m1", "S1", int(START_EPOCH), None,
                     json.dumps({"type": "text", "text": "int epoch user"}), 1))
        con.commit()
    finally:
        con.close()


def _make_live_iso_db(path: Path) -> None:
    """Live shape with pre-existing canonical ISO "...Z" strings."""
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE session (
                id TEXT, parent_id TEXT, title TEXT, time_created TEXT,
                time_updated TEXT, time_compacting TEXT, trace_id TEXT, cwd TEXT
            );
            CREATE TABLE message (
                id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT,
                data TEXT, sequence INTEGER
            );
            CREATE TABLE part (
                id TEXT, message_id TEXT, session_id TEXT, time_created TEXT,
                time_updated TEXT, data TEXT, sequence INTEGER
            );
            """
        )
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
                    ("S1", None, "iso session", ISO_START,
                     None, None, "TR1", "/work/main"))
        con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                    ("m1", "S1", ISO_TEST, None,
                     json.dumps({"role": "user"}), 1))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)",
                    ("p1", "m1", "S1", ISO_TEST, None,
                     json.dumps({"type": "text", "text": "iso user"}), 1))
        con.commit()
    finally:
        con.close()


def _make_live_null_db(path: Path) -> None:
    """Live shape with NULL native timestamps (None must stay None)."""
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE session (
                id TEXT, parent_id TEXT, title TEXT, time_created TEXT,
                time_updated TEXT, time_compacting TEXT, trace_id TEXT, cwd TEXT
            );
            CREATE TABLE message (
                id TEXT, session_id TEXT, time_created TEXT, time_updated TEXT,
                data TEXT, sequence INTEGER
            );
            CREATE TABLE part (
                id TEXT, message_id TEXT, session_id TEXT, time_created TEXT,
                time_updated TEXT, data TEXT, sequence INTEGER
            );
            """
        )
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
                    ("S1", None, "null session", None,
                     None, None, "TR1", "/work/main"))
        con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                    ("m1", "S1", None, None, json.dumps({"role": "user"}), 1))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)",
                    ("p1", "m1", "S1", None, None,
                     json.dumps({"type": "text", "text": "null time user"}), 1))
        con.commit()
    finally:
        con.close()


# ---------------------------------------------------------- canonical (non-live) shape

def _make_canonical_epoch_db(path: Path) -> None:
    """Canonical conversation_traces/conversation_parts with epoch-ms strings."""
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE conversation_traces (
                trace_id TEXT, title TEXT, created_at TEXT
            );
            CREATE TABLE conversation_parts (
                part_id TEXT, trace_id TEXT, turn_id TEXT, part_type TEXT,
                role TEXT, content TEXT, created_at TEXT
            );
            """
        )
        con.execute("INSERT INTO conversation_traces VALUES (?,?,?)",
                    ("TR1", "canonical epoch session", START_EPOCH))
        con.executemany(
            "INSERT INTO conversation_parts VALUES (?,?,?,?,?,?,?)",
            [
                ("cp1", "TR1", "T1", "text", "user", "canonical prompt", START_EPOCH),
                ("cp2", "TR1", "T2", "text", "assistant", "canonical answer", MID_EPOCH),
            ],
        )
        con.commit()
    finally:
        con.close()


class TestZCodeTimestampNormalization:
    @pytest.fixture(scope="class")
    def epoch_adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("zcode-ts")
        db = tmp / "zcode_epoch.db"
        _make_live_epoch_db(db)
        return _adapt(db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
                      allowed_columns=ZCODE_ALLOWED_COLUMNS)

    def test_epoch_ms_strings_normalize_to_iso(self, epoch_adapted):
        result = epoch_adapted
        session = next(s for s in result.sessions if s.native_session_id == "S1")
        # session lifecycle: started_at / ended_at normalized from epoch ms.
        assert session.started_at == START_ISO
        # ended_at folds the last native activity (p2 time_updated) and normalizes it.
        assert session.ended_at == END_ISO

        life = _events_of(result, EventKind.SESSION_LIFECYCLE)
        assert len(life) == 1
        assert life[0].occurred_at == START_ISO

        user = _events_of(result, EventKind.USER_MESSAGE)
        assistant = _events_of(result, EventKind.ASSISTANT_MESSAGE)
        assert len(user) == 1 and len(assistant) == 1
        assert user[0].occurred_at == START_ISO
        assert assistant[0].occurred_at == MID_ISO  # p2 time_created

    def test_int_epoch_ms_normalize_to_iso(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("zcode-ts-int")
        db = tmp / "zcode_int.db"
        _make_live_int_db(db)
        result = _adapt(db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
                        allowed_columns=ZCODE_ALLOWED_COLUMNS)
        session = result.sessions[0]
        assert session.started_at == START_ISO
        assert session.ended_at == START_ISO  # single part; folds session row
        user = _events_of(result, EventKind.USER_MESSAGE)
        assert len(user) == 1
        assert user[0].occurred_at == START_ISO

    def test_existing_iso_timestamps_pass_through_unchanged(self, tmp_path_factory):
        # The fixture shape used by the pre-existing zcode context-extraction
        # contract test: ISO "...Z" strings must survive normalization equal.
        tmp = tmp_path_factory.mktemp("zcode-ts-iso")
        db = tmp / "zcode_iso.db"
        _make_live_iso_db(db)
        result = _adapt(db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
                        allowed_columns=ZCODE_ALLOWED_COLUMNS)
        session = result.sessions[0]
        assert session.started_at == ISO_START
        assert session.ended_at == ISO_TEST
        life = _events_of(result, EventKind.SESSION_LIFECYCLE)
        assert life[0].occurred_at == ISO_START
        user = _events_of(result, EventKind.USER_MESSAGE)
        assert user[0].occurred_at == ISO_TEST

    def test_none_timestamps_stay_none(self, tmp_path_factory):
        # NULL native timestamps must remain None — never the string "None".
        tmp = tmp_path_factory.mktemp("zcode-ts-null")
        db = tmp / "zcode_null.db"
        _make_live_null_db(db)
        result = _adapt(db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
                        allowed_columns=ZCODE_ALLOWED_COLUMNS)
        session = result.sessions[0]
        assert session.started_at is None
        assert session.ended_at is None
        assert not any(
            e.occurred_at is not None for e in result.events
        ), "no event may carry a timestamp when the native value is NULL"

    def test_canonical_non_live_epoch_ms_normalize_to_iso(self, tmp_path_factory):
        # conversation_traces/conversation_parts (non-live branch): created_at
        # epoch-ms strings normalize for started_at / ended_at / occurred_at.
        tmp = tmp_path_factory.mktemp("zcode-ts-canonical")
        db = tmp / "zcode_canonical.db"
        _make_canonical_epoch_db(db)
        result = _adapt(db, tmp, allowed_tables=CANONICAL_ALLOWED_TABLES,
                        allowed_columns=CANONICAL_ALLOWED_COLUMNS)
        session = result.sessions[0]
        assert session.native_session_id == "TR1"
        assert session.started_at == START_ISO
        assert session.ended_at == MID_ISO  # last part created_at
        life = _events_of(result, EventKind.SESSION_LIFECYCLE)
        assert life[0].occurred_at == START_ISO
        user = _events_of(result, EventKind.USER_MESSAGE)
        assistant = _events_of(result, EventKind.ASSISTANT_MESSAGE)
        assert len(user) == 1 and len(assistant) == 1
        assert user[0].occurred_at == START_ISO
        assert assistant[0].occurred_at == MID_ISO
