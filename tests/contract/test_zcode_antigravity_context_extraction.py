"""Phase 62-05: ZCode / Antigravity context extraction (RED -> GREEN).

Drives the real capture seam (capture_sqlite) and each family's detect/adapt
boundary with synthetic fixtures that exercise the newly-declared context seams:

  - ZCode (live session/message/part shape): AdaptedSession title/cwd, native
    trace_id/turn_id mapped to TURN_BOUNDARY events + TURN_MEMBERSHIP relations,
    native parent_id mapped to a SUBAGENT relation, part.type=compaction mapped
    to a COMPACTION_SUMMARY event + COMPACTED_RANGE relation, and any
    token-bearing payload mapped to a USAGE event.
  - Antigravity (canonical trajectories/steps/subtrajectories shape): trajectory
    name -> session title, subtrajectories -> SUBAGENT relation + SUBAGENT_BOUNDARY
    event, and a usage-bearing step -> USAGE event.

Fixtures are hand-written synthetic shapes (62-RESEARCH format matrix); no live
bodies or credentials. Assertions are made only on the public detect/adapt seam.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import antigravity, zcode
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import EventKind, RelationKind

ZCODE_ALLOWED_TABLES = ("session", "message", "part")
ZCODE_ALLOWED_COLUMNS = {
    "session": ("id", "parent_id", "title", "time_created", "time_updated",
                "time_compacting", "trace_id", "cwd"),
    "message": ("id", "session_id", "time_created", "time_updated", "data", "sequence"),
    "part": ("id", "message_id", "session_id", "time_created", "time_updated",
             "data", "sequence"),
}

ANTIGRAVITY_ALLOWED_TABLES = ("trajectories", "steps", "subtrajectories")
ANTIGRAVITY_ALLOWED_COLUMNS = {
    "trajectories": ("id", "name", "created_at"),
    "steps": ("id", "trajectory_id", "seq", "kind", "content", "metadata", "created_at"),
    "subtrajectories": ("id", "step_id", "parent_trajectory_id", "content", "created_at"),
}


def _make_zcode_db(path: Path) -> None:
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
        con.executemany(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
            [
                ("S1", None, "Main zcode session", "2026-07-01T10:00:00Z",
                 None, None, "TR1", "/work/main"),
                ("S2", "S1", "Child session", "2026-07-01T10:05:00Z",
                 None, None, "TR2", "/work/main"),
            ],
        )
        con.executemany(
            "INSERT INTO message VALUES (?,?,?,?,?,?)",
            [
                ("m1", "S1", "2026-07-01T10:00:01Z", None,
                 json.dumps({"role": "user"}), 1),
                ("m2", "S1", "2026-07-01T10:00:02Z", None,
                 json.dumps({"role": "assistant"}), 2),
                ("mc", "S1", "2026-07-01T10:00:09Z", None,
                 json.dumps({"role": "assistant"}), 3),
            ],
        )
        con.executemany(
            "INSERT INTO part VALUES (?,?,?,?,?,?,?)",
            [
                ("p1", "m1", "S1", "2026-07-01T10:00:01Z", None,
                 json.dumps({"type": "step-start", "text": "turn start"}), 1),
                ("p2", "m1", "S1", "2026-07-01T10:00:01Z", None,
                 json.dumps({"type": "text", "text": "user zcode prompt"}), 2),
                ("p3", "m1", "S1", "2026-07-01T10:00:01Z", None,
                 json.dumps({"type": "reasoning", "text": "thinking",
                             "usage": {"input_tokens": 12, "output_tokens": 4}}), 3),
                ("p4", "m1", "S1", "2026-07-01T10:00:02Z", None,
                 json.dumps({"type": "text", "text": "assistant zcode answer"}), 4),
                ("p5", "m1", "S1", "2026-07-01T10:00:02Z", None,
                 json.dumps({"type": "step-finish", "text": "turn end"}), 5),
                ("p6", "m2", "S1", "2026-07-01T10:00:03Z", None,
                 json.dumps({"type": "text", "text": "assistant followup"}), 6),
                ("p7", "mc", "S1", "2026-07-01T10:00:09Z", None,
                 json.dumps({"type": "compaction", "text": "compacted earlier turns"}), 7),
            ],
        )
        con.commit()
    finally:
        con.close()


def _make_antigravity_db(path: Path) -> None:
    con = sqlite3.connect(path)
    try:
        con.executescript(
            """
            CREATE TABLE trajectories (
                id TEXT PRIMARY KEY, name TEXT, created_at TEXT
            );
            CREATE TABLE steps (
                id TEXT PRIMARY KEY, trajectory_id TEXT, seq INTEGER,
                kind TEXT, content TEXT, metadata TEXT, created_at TEXT
            );
            CREATE TABLE subtrajectories (
                id TEXT PRIMARY KEY, step_id TEXT, parent_trajectory_id TEXT,
                content TEXT, created_at TEXT
            );
            """
        )
        con.execute("INSERT INTO trajectories VALUES (?,?,?)",
                    ("t_1", "antigravity run", "2026-07-01T10:00:00Z"))
        con.executemany(
            "INSERT INTO steps VALUES (?,?,?,?,?,?,?)",
            [
                ("st1", "t_1", 1, "user", "antigravity prompt", None,
                 "2026-07-01T10:00:01Z"),
                ("st2", "t_1", 2, "assistant", "antigravity answer",
                 json.dumps({"usage": {"input_tokens": 30, "output_tokens": 9,
                                       "cache_read": 2, "cache_write": 1}}),
                 "2026-07-01T10:00:02Z"),
                ("st3", "t_1", 3, "tool", "antigravity tool call", None,
                 "2026-07-01T10:00:03Z"),
            ],
        )
        con.execute("INSERT INTO subtrajectories VALUES (?,?,?,?,?)",
                    ("sub1", "st3", "t_1", "nested sub trajectory",
                     "2026-07-01T10:00:04Z"))
        con.commit()
    finally:
        con.close()


def _capture(db: Path, tmp_path: Path, *, allowed_tables, allowed_columns):
    artifact, blob = capture_sqlite(
        db, tmp_path, allowed_tables=allowed_tables,
        allowed_columns=allowed_columns, byte_limit=1_000_000, count_limit=8,
    )
    return artifact, blob.parent


def _capture_zcode_custom(tmp_path: Path, *, session_title, user_text) -> zcode.AdaptationResult:
    db = tmp_path / "sess.db"
    con = sqlite3.connect(db)
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
                    ("S1", None, session_title, "2026-07-01T10:00:00Z",
                     None, None, "TR1", "/work/main"))
        con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                    ("m1", "S1", "2026-07-01T10:00:01Z", None,
                     json.dumps({"role": "user"}), 1))
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)",
                    ("p1", "m1", "S1", "2026-07-01T10:00:01Z", None,
                     json.dumps({"type": "text", "text": user_text}), 1))
        con.commit()
    finally:
        con.close()
    artifact, root = _capture(
        db, tmp_path, allowed_tables=ZCODE_ALLOWED_TABLES,
        allowed_columns=ZCODE_ALLOWED_COLUMNS,
    )
    return zcode.adapt(SourceArtifactSet(artifacts=(artifact,)), artifact_root=root)


# ----------------------------------------------------------------------------- ZCode

class TestZCodeContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("zcode-ctx")
        db = tmp / "zcode.db"
        _make_zcode_db(db)
        artifact, root = _capture(
            db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
            allowed_columns=ZCODE_ALLOWED_COLUMNS,
        )
        return zcode.adapt(SourceArtifactSet(artifacts=(artifact,)), artifact_root=root), artifact, root

    def test_sessions_carry_title_and_cwd(self, adapted):
        result, _a, _r = adapted
        by_native = {s.native_session_id: s for s in result.sessions}
        main = by_native["S1"]
        assert main.title == "Main zcode session"
        assert main.cwd == "/work/main"

    def test_ended_at_from_last_part_activity(self, adapted):
        # Session end is the last native activity: the maximum part/message
        # time_updated, falling back to time_created when time_updated is unset.
        # Fixture S1 parts end at p7 (compaction) time_created 2026-07-01T10:00:09Z.
        result, _a, _r = adapted
        by_native = {s.native_session_id: s for s in result.sessions}
        assert by_native["S1"].ended_at == "2026-07-01T10:00:09Z"
        # S2 has no parts/messages but its session row was touched later
        # (time_updated 10:05:00Z) — the session's own timestamp folds in
        # (Round-5 fix: ended_at must not under-report session activity).
        assert by_native["S2"].ended_at == "2026-07-01T10:05:00Z"

    def test_cwd_from_directory_column_and_ended_at_fallback(self, tmp_path):
        # Real zcode schema stores the working dir in directory/path, not a
        # literal cwd column; the adapter must still surface it as session.cwd,
        # and ended_at must fall back to the last part's time_created.
        db = tmp_path / "zcode_dir.db"
        con = sqlite3.connect(str(db))
        con.execute(
            "CREATE TABLE session (id TEXT, parent_id TEXT, title TEXT,"
            "time_created TEXT, time_updated TEXT, time_compacting TEXT,"
            "trace_id TEXT, directory TEXT, path TEXT)"
        )
        con.execute(
            "CREATE TABLE message (id TEXT, session_id TEXT,"
            "time_created TEXT, time_updated TEXT, data TEXT,"
            "sequence INTEGER)"
        )
        con.execute(
            "CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT,"
            "time_created TEXT, time_updated TEXT, data TEXT,"
            "sequence INTEGER)"
        )
        con.execute(
            "INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)",
            ("SD1", None, "dir session", "t0", None, None, "TRD",
             "/work/dir", "/work/dir"),
        )
        con.execute(
            "INSERT INTO message VALUES (?,?,?,?,?,?)",
            ("md1", "SD1", "t1", None, "{}", 1),
        )
        con.execute(
            "INSERT INTO part VALUES (?,?,?,?,?,?,?)",
            ("pd1", "md1", "SD1", "t2", None,
             json.dumps({"type": "text", "text": "hi"}), 1),
        )
        con.commit()
        con.close()
        # Real zcode session schema uses directory/path (no literal cwd col).
        allowed = {
            "session": ("id", "parent_id", "title", "time_created",
                        "time_updated", "time_compacting", "trace_id",
                        "directory", "path"),
            "message": ("id", "session_id", "time_created", "time_updated",
                        "data", "sequence"),
            "part": ("id", "message_id", "session_id", "time_created",
                     "time_updated", "data", "sequence"),
        }
        artifact, blob = capture_sqlite(
            db, tmp_path / "cap", allowed_tables=ZCODE_ALLOWED_TABLES,
            allowed_columns=allowed,
            byte_limit=1000000, count_limit=8,
        )
        result = zcode.adapt(
            SourceArtifactSet(artifacts=(artifact,)), artifact_root=blob.parent
        )
        session = next(s for s in result.sessions if s.native_session_id == "SD1")
        assert session.cwd == "/work/dir"
        assert session.ended_at == "t2"

    # ---- P2-1: zcode title from first real user message, not truncated/embedded ----
    def test_title_from_first_user_when_stored_title_is_placeholder(self, tmp_path):
        # stored title is the plugin/AGENTS scaffolding => title comes from the
        # first real user message and is capped at 120, never a fixed 60.
        long_user = "set up the new billing service end to end " + ("payload " * 40)
        result = _capture_zcode_custom(
            tmp_path,
            session_title="<recommended_plugins>plugin template",
            user_text=long_user,
        )
        session = result.sessions[0]
        assert session.title is not None
        assert session.title == long_user.strip()[:120]
        assert len(session.title) <= 120
        assert len(session.title) > 60  # no longer stuck at the old 60 cap

    def test_genuine_stored_title_is_preferred(self, tmp_path):
        # a real stored title is kept even when a user message exists.
        result = _capture_zcode_custom(
            tmp_path,
            session_title="Real feature title",
            user_text="real user prompt text",
        )
        assert result.sessions[0].title == "Real feature title"

    def test_stored_title_capped_at_120(self, tmp_path):
        long_title = "Long but genuinely user authored title " + ("y " * 200)
        result = _capture_zcode_custom(
            tmp_path, session_title=long_title, user_text="some prompt",
        )
        assert result.sessions[0].title == long_title[:120]
        assert len(result.sessions[0].title) <= 120

    def test_parent_id_becomes_subagent_relation(self, adapted):
        result, _a, _r = adapted
        subagent = [r for r in result.relations if r.relation_kind is RelationKind.SUBAGENT]
        assert len(subagent) == 1
        child = next(e for e in result.events
                     if e.kind is EventKind.SESSION_LIFECYCLE
                     and e.provenance.native_event_id == "S2")
        parent = next(e for e in result.events
                      if e.kind is EventKind.SESSION_LIFECYCLE
                      and e.provenance.native_event_id == "S1")
        assert subagent[0].source_event_id == child.event_id
        assert subagent[0].target_event_id == parent.event_id

    def test_turn_boundary_and_membership_from_step_parts(self, adapted):
        result, _a, _r = adapted
        boundaries = [e for e in result.events if e.kind is EventKind.TURN_BOUNDARY]
        assert len(boundaries) >= 2
        memberships = [r for r in result.relations
                       if r.relation_kind is RelationKind.TURN_MEMBERSHIP]
        assert len(memberships) >= 1

    def test_compaction_event_and_compacted_range_relation(self, adapted):
        result, _a, _r = adapted
        compact = [e for e in result.events if e.kind is EventKind.COMPACTION_SUMMARY]
        assert len(compact) == 1
        ranges = [r for r in result.relations
                  if r.relation_kind is RelationKind.COMPACTED_RANGE]
        assert len(ranges) == 1
        assert ranges[0].source_event_id == compact[0].event_id
        assert ranges[0].target_event_id != compact[0].event_id

    def test_usage_event_from_token_payload(self, adapted):
        result, _a, _r = adapted
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) >= 1
        summary = usage[0].summary or ""
        assert "input_tokens=12" in summary
        assert "output_tokens=4" in summary
        assert usage[0].content is None

    def test_tokens_aggregate_canonical_format(self, tmp_path):
        # Real ZCode stores usage as a part.data tokens aggregate
        # ({total, input, output, reasoning, cache:{read, write}}): it
        # must surface as canonical input_tokens=/output_tokens=/cache_read=.
        db = tmp_path / "zcode_tokens.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE session (id TEXT, parent_id TEXT, title TEXT,"
                    "time_created TEXT, time_updated TEXT, time_compacting TEXT,"
                    "trace_id TEXT, cwd TEXT)")
        con.execute("CREATE TABLE message (id TEXT, session_id TEXT,"
                    "time_created TEXT, time_updated TEXT, data TEXT,"
                    "sequence INTEGER)")
        con.execute("CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT,"
                    "time_created TEXT, time_updated TEXT, data TEXT,"
                    "sequence INTEGER)")
        con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?)",
                    ("ST1", None, "zcode tokens", "t0", None, None, "TRZ", "/w"))
        con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)",
                    ("mt1", "ST1", "t1", None, "{}", 1))
        tokens = {"total": 11406, "input": 11119, "output": 287,
                  "reasoning": 0, "cache": {"read": 7040, "write": 0}}
        part_data = json.dumps({"type": "reasoning", "text": "t",
                               "tokens": tokens})
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)",
                    ("pt1", "mt1", "ST1", "t1", None, part_data, 1))
        con.commit()
        con.close()
        artifact, blob = capture_sqlite(
            db, tmp_path / "cap", allowed_tables=ZCODE_ALLOWED_TABLES,
            allowed_columns=ZCODE_ALLOWED_COLUMNS,
            byte_limit=1000000, count_limit=8,
        )
        result = zcode.adapt(SourceArtifactSet(artifacts=(artifact,)), artifact_root=blob.parent)
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert usages[0].content is None
        s = usages[0].summary or ""
        assert s.startswith("input_tokens=")
        assert "input_tokens=11119" in s
        assert "output_tokens=287" in s
        assert "cache_read=7040" in s
        assert "cache_write=0" in s
        assert "reasoning=" not in s

    def test_detect_live(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("zcode-ctx-detect")
        db = tmp / "zcode.db"
        _make_zcode_db(db)
        artifact, root = _capture(
            db, tmp, allowed_tables=ZCODE_ALLOWED_TABLES,
            allowed_columns=ZCODE_ALLOWED_COLUMNS,
        )
        assert zcode.detect(artifact, artifact_root=root) is True


# ------------------------------------------------------------------------- Antigravity

class TestAntigravityContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("antigravity-ctx")
        db = tmp / "trajectory.db"
        _make_antigravity_db(db)
        artifact, root = _capture(
            db, tmp, allowed_tables=ANTIGRAVITY_ALLOWED_TABLES,
            allowed_columns=ANTIGRAVITY_ALLOWED_COLUMNS,
        )
        return antigravity.adapt(SourceArtifactSet(artifacts=(artifact,)), artifact_root=root), artifact, root

    def test_session_title_from_trajectory_name(self, adapted):
        result, _a, _r = adapted
        assert len(result.sessions) >= 1
        session = next(s for s in result.sessions if s.native_session_id == "t_1")
        assert session.title == "antigravity run"

    def test_subtrajectory_becomes_subagent_boundary_and_relation(self, adapted):
        result, _a, _r = adapted
        boundaries = [e for e in result.events
                      if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert len(boundaries) == 1
        subagents = [r for r in result.relations
                     if r.relation_kind is RelationKind.SUBAGENT]
        assert len(subagents) == 1
        assert subagents[0].source_event_id == boundaries[0].event_id

    def test_step_usage_emit(self, adapted):
        result, _a, _r = adapted
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) >= 1
        summary = next(e.summary or "" for e in usage)
        assert "input_tokens=30" in summary
        assert "output_tokens=9" in summary
        assert "cache_read=2" in summary
        assert "cache_write=1" in summary
        assert all(e.content is None for e in usage)

    def test_all_relations_reference_known_events(self, adapted):
        result, _a, _r = adapted
        known = {e.event_id for e in result.events}
        for rel in result.relations:
            assert rel.source_event_id in known
            assert rel.target_event_id in known

    def test_detect(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("antigravity-ctx-detect")
        db = tmp / "trajectory.db"
        _make_antigravity_db(db)
        artifact, root = _capture(
            db, tmp, allowed_tables=ANTIGRAVITY_ALLOWED_TABLES,
            allowed_columns=ANTIGRAVITY_ALLOWED_COLUMNS,
        )
        assert antigravity.detect(artifact, artifact_root=root) is True
