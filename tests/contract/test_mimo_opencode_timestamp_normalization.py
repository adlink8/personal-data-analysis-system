"""Phase 62 F12: mimo_opencode timestamp normalization (RED -> GREEN).

The mimo and opencode families share one adapter (mimo_opencode.py) and store
native timestamps on the live session/message/part rows as raw epoch
milliseconds (digit strings) or ISO strings. Before those values flow into
occurred_at / started_at / ended_at they MUST be normalized to the
canonical UTC ISO-8601 Z-suffixed shape via the shared seam
normalize_timestamp (time_utils) - both families, both schema shapes.

This contract drives the real capture seam (capture_sqlite) and the public
mimo_opencode.adapt boundary with synthetic fixtures, asserting:

  - epoch-millis digit strings -> canonical UTC ISO (Z-suffixed)
  - existing ISO Z-suffixed strings pass through unchanged (normalized equal)
  - None stays None (never the string "None")

Reference conversions computed with the shared seam on this machine:
  1775638723463 -> "2026-04-08T08:58:43.463Z"
  1775638724000 -> "2026-04-08T08:58:44Z"
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import mimo_opencode
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import EventKind

_EPOCH_MS = "1775638723463"
_EPOCH_MS_ISO = "2026-04-08T08:58:43.463Z"
_EPOCH_MS2 = "1775638724000"
_EPOCH_MS2_ISO = "2026-04-08T08:58:44Z"
_ISO1 = "2026-04-08T09:00:00Z"
_ISO2 = "2026-04-08T09:00:01Z"

_FAMILIES = ("mimo", "opencode")

_LIVE_TABLES = ("session", "message", "part")
_LIVE_COLUMNS = {
    "session": ("id", "parent_id", "title", "time_created", "time_updated",
                "time_compacting"),
    "message": ("id", "session_id", "time_created", "time_updated", "data"),
    "part": ("id", "message_id", "session_id", "time_created", "time_updated",
             "data"),
}


def _make_live_db(path: Path) -> None:
    con = sqlite3.connect(str(path))
    try:
        con.executescript(
            "CREATE TABLE session (id TEXT, parent_id TEXT, title TEXT,"
            " time_created TEXT, time_updated TEXT, time_compacting TEXT);"
            "CREATE TABLE message (id TEXT, session_id TEXT, time_created TEXT,"
            " time_updated TEXT, data TEXT);"
            "CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT,"
            " time_created TEXT, time_updated TEXT, data TEXT);"
        )
        con.executemany(
            "INSERT INTO session VALUES (?,?,?,?,?,?)",
            [
                ("s_epoch", None, "epoch session", _EPOCH_MS, _EPOCH_MS2, None),
                ("s_iso", None, "iso session", _ISO1, None, None),
                ("s_none", None, "none session", None, None, None),
            ],
        )
        con.executemany(
            "INSERT INTO message VALUES (?,?,?,?,?)",
            [
                ("m1", "s_epoch", _EPOCH_MS, None, json.dumps({"role": "user"})),
                ("m2", "s_iso", _ISO2, None, json.dumps({"role": "user"})),
                ("m3", "s_none", None, None, json.dumps({"role": "assistant"})),
            ],
        )
        con.executemany(
            "INSERT INTO part VALUES (?,?,?,?,?,?)",
            [
                ("p1", "m1", "s_epoch", _EPOCH_MS2, None,
                 json.dumps({"type": "text", "text": "hello"})),
                ("p2", "m2", "s_iso", _ISO1, None,
                 json.dumps({"type": "text", "text": "world"})),
                ("p3", "m3", "s_none", None, None,
                 json.dumps({"type": "text", "text": "none"})),
            ],
        )
        con.commit()
    finally:
        con.close()


def _adapt_live(tmp_path, family: str):
    db = tmp_path / "live.sqlite"
    _make_live_db(db)
    artifact, blob = capture_sqlite(
        db, tmp_path / "cap", allowed_tables=_LIVE_TABLES,
        allowed_columns=_LIVE_COLUMNS,
        byte_limit=1000000, count_limit=12,
    )
    return mimo_opencode.adapt(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent
    )


def _adapt_classic(tmp_path, family: str):
    """Non-live schema (sessions/messages/message_parts with created_at)."""
    db = tmp_path / "classic.sqlite"
    con = sqlite3.connect(str(db))
    try:
        con.executescript(
            "CREATE TABLE sessions (id TEXT, title TEXT, created_at TEXT);"
            "CREATE TABLE messages (id TEXT, session_id TEXT, role TEXT,"
            " content TEXT, created_at TEXT);"
            "CREATE TABLE message_parts (id TEXT, message_id TEXT,"
            " part_type TEXT, content TEXT, created_at TEXT);"
        )
        con.executemany(
            "INSERT INTO sessions VALUES (?,?,?)",
            [("s1", "classic epoch", _EPOCH_MS)],
        )
        con.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            [("m1", "s1", "user", "hi", _EPOCH_MS)],
        )
        con.executemany(
            "INSERT INTO message_parts VALUES (?,?,?,?,?)",
            [("p1", "m1", "text", "hi", _EPOCH_MS2)],
        )
        con.commit()
    finally:
        con.close()
    artifact, blob = capture_sqlite(
        db, tmp_path / "cap2",
        allowed_tables=("sessions", "messages", "message_parts"),
        allowed_columns={
            "sessions": ("id", "title", "created_at"),
            "messages": ("id", "session_id", "role", "content", "created_at"),
            "message_parts": ("id", "message_id", "part_type", "content",
                              "created_at"),
        },
        byte_limit=1000000, count_limit=4,
    )
    return mimo_opencode.adapt(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent
    )


@pytest.mark.parametrize("family", _FAMILIES)
class TestMimoOpenCodeTimestampNormalization:
    def test_epoch_millis_digit_string_normalized(self, tmp_path, family):
        # A session whose native time_created is an epoch-millis digit string
        # must surface as the canonical UTC ISO Z-shape everywhere it flows.
        result = _adapt_live(tmp_path, family)
        session = next(s for s in result.sessions
                       if s.native_session_id == "s_epoch")
        assert session.started_at == _EPOCH_MS_ISO          # time_created
        assert session.ended_at == _EPOCH_MS2_ISO           # time_updated
        life = next(e for e in result.events
                    if e.kind is EventKind.SESSION_LIFECYCLE
                    and e.provenance.native_event_id == "s_epoch")
        assert life.occurred_at == _EPOCH_MS_ISO
        msg_ev = next(e for e in result.events
                      if e.provenance.native_event_id == "m1")
        assert msg_ev.occurred_at == _EPOCH_MS_ISO
        part_ev = next(e for e in result.events
                       if e.provenance.native_event_id == "p1")
        assert part_ev.occurred_at == _EPOCH_MS2_ISO

    def test_epoch_millis_normalized_in_classic_schema(self, tmp_path, family):
        # The non-live shape (created_at columns) must be normalized the same
        # way, covering the created_at branch of every assignment.
        result = _adapt_classic(tmp_path, family)
        session = result.sessions[0]
        assert session.started_at == _EPOCH_MS_ISO
        assert session.ended_at is None                      # no updated_at
        life = next(e for e in result.events
                    if e.kind is EventKind.SESSION_LIFECYCLE)
        assert life.occurred_at == _EPOCH_MS_ISO
        msg_ev = next(e for e in result.events
                      if e.provenance.native_event_id == "m1")
        assert msg_ev.occurred_at == _EPOCH_MS_ISO

    def test_iso_passthrough_unchanged(self, tmp_path, family):
        # Existing ISO Z-suffixed strings are already canonical: normalization
        # must be equality-preserving for them.
        result = _adapt_live(tmp_path, family)
        session = next(s for s in result.sessions
                       if s.native_session_id == "s_iso")
        assert session.started_at == _ISO1
        life = next(e for e in result.events
                    if e.kind is EventKind.SESSION_LIFECYCLE
                    and e.provenance.native_event_id == "s_iso")
        assert life.occurred_at == _ISO1
        msg_ev = next(e for e in result.events
                      if e.provenance.native_event_id == "m2")
        assert msg_ev.occurred_at == _ISO2
        part_ev = next(e for e in result.events
                       if e.provenance.native_event_id == "p2")
        assert part_ev.occurred_at == _ISO1

    def test_none_stays_none(self, tmp_path, family):
        # None must remain None on sessions and events - never the string
        # "None".
        result = _adapt_live(tmp_path, family)
        session = next(s for s in result.sessions
                       if s.native_session_id == "s_none")
        assert session.started_at is None
        assert session.ended_at is None
        life = next(e for e in result.events
                    if e.kind is EventKind.SESSION_LIFECYCLE
                    and e.provenance.native_event_id == "s_none")
        assert life.occurred_at is None
        msg_ev = next(e for e in result.events
                      if e.provenance.native_event_id == "m3")
        assert msg_ev.occurred_at is None
        part_ev = next(e for e in result.events
                       if e.provenance.native_event_id == "p3")
        assert part_ev.occurred_at is None


def test_adapter_version_bumped():
    # The capability contract must advertise the new adapter version for
    # both families.
    assert mimo_opencode.capability("mimo").adapter_version == "1.4.0"
    assert mimo_opencode.capability("opencode").adapter_version == "1.4.0"
