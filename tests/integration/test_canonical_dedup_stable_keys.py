"""Phase 42 stable canonical session identity and deterministic rebuild tests."""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

from personal_knowledge.application.conversation.build_canonical_agent_conversations import (
    CrosswalkStats,
    _load_agentsview_sessions,
    _load_legacy_sessions,
    build_crosswalk,
    run as build_canonical_run,
)


def _make_av_db(path: Path, sessions: list[dict]) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE sessions (
          session_id TEXT PRIMARY KEY, source_session_id TEXT, agent TEXT,
          started_at TEXT, ended_at TEXT, message_count INTEGER,
          user_message_count INTEGER, file_hash TEXT, parent_session_id TEXT,
          relationship_type TEXT, source_session_ref TEXT, cwd TEXT,
          git_branch TEXT, evidence_eligible INTEGER, evidence_scope TEXT
        );
        CREATE TABLE messages (
          message_id TEXT PRIMARY KEY, session_id TEXT, source_message_id INTEGER,
          ordinal INTEGER, role TEXT, content TEXT, content_length INTEGER,
          timestamp TEXT, model TEXT, is_system INTEGER, is_sidechain INTEGER,
          content_hash TEXT, evidence_scope TEXT
        );
        CREATE TABLE tool_events (
          tool_event_id TEXT PRIMARY KEY, session_id TEXT, source_kind TEXT,
          tool_name TEXT, category TEXT, status TEXT, call_index INTEGER,
          subagent_session_id TEXT, content_length INTEGER, timestamp TEXT
        );
        """
    )
    for session in sessions:
        sid = session["sid"]
        messages = session.get("messages", [])
        con.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"n-{sid}", sid, session.get("agent", "codex"),
                session.get("started", "2026-01-01T00:00:00Z"), None,
                len(messages), sum(1 for m in messages if m["role"] == "user"),
                session.get("file_hash"), None, None, session.get("source_ref"),
                None, None, session.get("eligible", 1), "user",
            ),
        )
        for index, message in enumerate(messages, 1):
            content = message["content"]
            con.execute(
                "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"m-{sid}-{index}", f"n-{sid}", index, index,
                    message["role"], content, len(content),
                    f"2026-01-01T00:00:{index:02d}Z", None, 0, 0,
                    hashlib.sha256(content.encode()).hexdigest()[:32], "user",
                ),
            )
    con.commit()
    con.close()
    return path


def _make_legacy_db(path: Path, sessions: list[dict]) -> Path:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE agent_sessions_meta (
          session_id TEXT, source TEXT, family TEXT, raw_file TEXT,
          timestamp TEXT, cwd TEXT, model TEXT
        );
        CREATE TABLE source_files (
          sha256 TEXT, relative_path TEXT, copied_path TEXT
        );
        CREATE TABLE agent_messages (
          session_id TEXT, event_index INTEGER, timestamp TEXT,
          role TEXT, text TEXT
        );
        """
    )
    for session in sessions:
        sid = session["sid"]
        raw_file = session.get("raw_file", f"{sid}.jsonl")
        con.execute(
            "INSERT INTO agent_sessions_meta VALUES (?,?,?,?,?,?,?)",
            (sid, "codex", "codex", raw_file,
             session.get("started", "2026-01-01T00:00:00Z"), None, None),
        )
        if session.get("file_hash"):
            con.execute(
                "INSERT INTO source_files VALUES (?,?,?)",
                (session["file_hash"], raw_file, raw_file),
            )
        for index, message in enumerate(session.get("messages", []), 1):
            con.execute(
                "INSERT INTO agent_messages VALUES (?,?,?,?,?)",
                (sid, index, f"2026-01-01T00:00:{index:02d}Z", message["role"], message["content"]),
            )
    con.commit()
    con.close()
    return path


def _run(av: Path, legacy: Path, dest: Path) -> None:
    assert build_canonical_run(
        dry_run=False, write=True, av_db=av, legacy_db=legacy, dest_db=dest
    ) == 0


def _dump_hash(path: Path) -> str:
    con = sqlite3.connect(path)
    lines: list[str] = []
    for (table,) in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ):
        rows = con.execute(f'SELECT * FROM "{table}" ORDER BY rowid').fetchall()
        lines.append(f"{table}:{rows!r}")
    con.close()
    return hashlib.sha256("\n".join(lines).encode()).hexdigest()


def test_growth_is_same_session(tmp_path: Path) -> None:
    av = tmp_path / "av.sqlite"
    legacy = tmp_path / "legacy.sqlite"
    dest = tmp_path / "canonical.sqlite"
    session = {"sid": "codex:aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", "file_hash": "H1",
               "messages": [{"role": "user", "content": "原始用户消息内容足够长用于测试。"}]}
    _make_av_db(av, [session]); _make_legacy_db(legacy, [])
    _run(av, legacy, dest)
    con = sqlite3.connect(dest)
    csid = con.execute("SELECT canonical_session_id FROM canonical_sessions").fetchone()[0]
    before = con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0]
    con.close()
    session["file_hash"] = "H2"
    session["messages"].extend([
        {"role": "assistant", "content": "新增回答内容，用于验证增长不是新会话。"},
        {"role": "user", "content": "第二条新增用户消息内容。"},
    ])
    av.unlink(); _make_av_db(av, [session]); _run(av, legacy, dest)
    con = sqlite3.connect(dest)
    assert con.execute("SELECT canonical_session_id FROM canonical_sessions").fetchone()[0] == csid
    assert con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0] == 1
    assert con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0] > before
    con.close()


def test_double_build_byte_stable(tmp_path: Path) -> None:
    av = _make_av_db(tmp_path / "av.sqlite", [{
        "sid": "codex:bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        "file_hash": "H", "messages": [{"role": "user", "content": "稳定构建测试消息。"}],
    }])
    legacy = _make_legacy_db(tmp_path / "legacy.sqlite", [])
    a, b = tmp_path / "a.sqlite", tmp_path / "b.sqlite"
    _run(av, legacy, a); _run(av, legacy, b)
    assert _dump_hash(a) == _dump_hash(b), "幂等失败：全表 dump 不一致"


def test_source_mapping_merges_legacy_twin(tmp_path: Path) -> None:
    uuid = "cccccccc-cccc-cccc-cccc-cccccccccccc"
    av = _make_av_db(tmp_path / "av.sqlite", [{
        "sid": f"codex:{uuid}", "file_hash": "AV-HASH",
        "messages": [{"role": "user", "content": "AV 版本会话消息。"}],
    }])
    legacy = _make_legacy_db(tmp_path / "legacy.sqlite", [{
        "sid": f"rollout-2026-01-01-{uuid}", "file_hash": "LEGACY-HASH",
        "raw_file": "legacy.jsonl", "messages": [{"role": "user", "content": "旧版本会话消息。"}],
    }])
    stats = CrosswalkStats()
    build_crosswalk(_load_agentsview_sessions(av), _load_legacy_sessions(legacy), legacy, stats)
    assert stats.merged_by_source_mapping == 1
    assert stats.file_hash_divergent == 1
    dest = tmp_path / "canonical.sqlite"; _run(av, legacy, dest)
    con = sqlite3.connect(dest)
    assert con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0] == 1
    assert con.execute("SELECT match_method FROM session_source_links WHERE source='legacy'").fetchone()[0] == "source_mapping"
    con.close()


def test_shared_source_session_ref_not_merged(tmp_path: Path) -> None:
    sessions = [
        {"sid": "codex:dddddddd-dddd-dddd-dddd-dddddddddddd", "source_ref": "shared", "messages": [{"role": "user", "content": "主会话内容。"}]},
        {"sid": "codex:eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee", "source_ref": "shared", "messages": [{"role": "user", "content": "子代理会话内容。"}]},
    ]
    av = _make_av_db(tmp_path / "av.sqlite", sessions); legacy = _make_legacy_db(tmp_path / "legacy.sqlite", [])
    dest = tmp_path / "canonical.sqlite"; _run(av, legacy, dest)
    con = sqlite3.connect(dest)
    assert con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0] == 2
    con.close()


def test_superseded_lifecycle_keeps_messages(tmp_path: Path) -> None:
    duplicate_hash = "WEAK-HASH"
    legacy = _make_legacy_db(tmp_path / "legacy.sqlite", [
        {"sid": "legacy-old", "file_hash": duplicate_hash, "raw_file": "old.jsonl",
         "started": "2026-01-01T00:00:00Z", "messages": [{"role": "user", "content": "旧副本消息。"}]},
        {"sid": "legacy-active", "file_hash": duplicate_hash, "raw_file": "active.jsonl",
         "started": "2026-01-02T00:00:00Z", "messages": [{"role": "user", "content": "活跃副本消息一。"}, {"role": "assistant", "content": "活跃副本消息二。"}]},
    ])
    av = _make_av_db(tmp_path / "av.sqlite", [])
    dest = tmp_path / "canonical.sqlite"; _run(av, legacy, dest)
    con = sqlite3.connect(dest)
    rows = con.execute("SELECT lifecycle, superseded_by_canonical_id, evidence_eligible FROM canonical_sessions ORDER BY canonical_session_id").fetchall()
    assert sum(row[0] == "superseded" for row in rows) == 1
    superseded = next(row for row in rows if row[0] == "superseded")
    assert superseded[1] is not None and superseded[2] == 0
    assert con.execute("SELECT COUNT(*) FROM canonical_messages").fetchone()[0] == 3
    con.close()
