"""Phase 13.5 Wave 4.2 测试：cutover parity gate。

覆盖 PLAN Task 4.2：
  - overlap session parity（eligible 的 user turn 一致性）
  - secret/excluded/deleted session 可检索正文 = 0
  - canonical 覆盖 >= legacy
  - AgentView-only session 有 lineage
  - gate_passed 判定
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.domains.conversation.evaluate_agent_conversation_cutover import (  # noqa: E402
    CutoverReport,
    evaluate,
    _check_secret_searchable,
    _check_av_only_lineage,
)


def _make_canonical_for_cutover(dest: Path) -> Path:
    """造一个 canonical DB，含 merged/av-only/legacy-only/ineligible session。"""
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE canonical_sessions (
            canonical_session_id TEXT PRIMARY KEY, primary_source TEXT, agent TEXT,
            started_at TEXT, ended_at TEXT, message_count INTEGER,
            user_message_count INTEGER, file_hash TEXT, parent_canonical_id TEXT,
            relationship_type TEXT, cwd TEXT, git_branch TEXT, model TEXT,
            evidence_eligible INTEGER DEFAULT 1, evidence_scope TEXT DEFAULT 'user',
            merged INTEGER DEFAULT 0
        )"""
    )
    cur.execute(
        """CREATE TABLE canonical_messages (
            canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT,
            source TEXT, source_message_ref TEXT, ordinal INTEGER, role TEXT,
            content TEXT, content_length INTEGER, timestamp TEXT, model TEXT,
            is_system INTEGER, is_sidechain INTEGER, content_hash TEXT,
            evidence_scope TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE canonical_tool_events (
            canonical_tool_id TEXT PRIMARY KEY, canonical_session_id TEXT,
            source TEXT, source_kind TEXT, tool_name TEXT, category TEXT,
            status TEXT, call_index INTEGER, subagent_session_id TEXT,
            content_length INTEGER, timestamp TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE session_source_links (
            link_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT,
            source_session_id TEXT, source_raw_file TEXT, match_method TEXT,
            match_confidence TEXT
        )"""
    )

    # merged eligible session（AV + legacy 都有）
    cur.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs_merged','agentsview','codex','2026-01-01',NULL,2,1,'hash1',NULL,NULL,NULL,NULL,NULL,1,'user',1)"
    )
    cur.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cm1','cs_merged','agentsview','av:1',1,'user','hello',5,'2026-01-01',NULL,0,0,'h1','user'),"
        "('cm2','cs_merged','agentsview','av:2',2,'assistant','hi',2,'2026-01-01',NULL,0,0,'h2','assistant')"
    )
    cur.execute(
        "INSERT INTO session_source_links VALUES "
        "('l1','cs_merged','agentsview','agent-x',NULL,'file_hash','strong'),"
        "('l2','cs_merged','legacy','rollout-x',NULL,'file_hash','strong')"
    )

    # merged ineligible session（secret，正文不写）
    cur.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs_secret','agentsview','codex','2026-01-02',NULL,0,0,'hash2',NULL,NULL,NULL,NULL,NULL,0,'user',1)"
    )
    cur.execute(
        "INSERT INTO session_source_links VALUES "
        "('l3','cs_secret','agentsview','agent-s',NULL,'file_hash','strong'),"
        "('l4','cs_secret','legacy','rollout-s',NULL,'file_hash','strong')"
    )
    # 不写 messages（secret 屏蔽）

    # AV-only session
    cur.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs_avonly','agentsview','claude','2026-02-01',NULL,1,1,'hash3',NULL,NULL,NULL,NULL,NULL,1,'user',0)"
    )
    cur.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cm3','cs_avonly','agentsview','av:3',1,'user','new content',11,'2026-02-01',NULL,0,0,'h3','user')"
    )
    cur.execute(
        "INSERT INTO session_source_links VALUES "
        "('l5','cs_avonly','agentsview','agent-o',NULL,'single_source','strong')"
    )

    # legacy-only session
    cur.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs_legonly','legacy','Codex','2026-03-01',NULL,1,1,'hash4',NULL,NULL,NULL,NULL,NULL,1,'user',0)"
    )
    cur.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cm4','cs_legonly','legacy','legacy:1',1,'user','legacy q',8,'2026-03-01',NULL,0,0,'h4','user')"
    )
    cur.execute(
        "INSERT INTO session_source_links VALUES "
        "('l6','cs_legonly','legacy','rollout-lo',NULL,'single_source','strong')"
    )

    con.commit()
    con.close()
    return dest


def _make_legacy_for_cutover(dest: Path) -> Path:
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute("CREATE TABLE agent_sessions_meta (session_id TEXT, source TEXT)")
    cur.execute("CREATE TABLE agent_messages (session_id TEXT, event_index INTEGER, role TEXT, text TEXT)")
    cur.execute("CREATE TABLE agent_tool_calls (session_id TEXT, call_id TEXT)")
    # merged session 的 legacy 消息（user + assistant）
    cur.execute(
        "INSERT INTO agent_messages VALUES ('rollout-x',1,'user','hello'),('rollout-x',2,'assistant','hi')"
    )
    cur.execute("INSERT INTO agent_sessions_meta VALUES ('rollout-x','Codex')")
    con.commit()
    con.close()
    return dest


def test_secret_searchable_zero(tmp_path: Path) -> None:
    """secret/ineligible session 的可检索正文 = 0。"""
    canon = _make_canonical_for_cutover(tmp_path / "canon.db")
    assert _check_secret_searchable(canon) == 0


def test_secret_searchable_detects_leak(tmp_path: Path) -> None:
    """如果 ineligible session 有正文，应检出。"""
    canon = _make_canonical_for_cutover(tmp_path / "canon.db")
    con = sqlite3.connect(str(canon))
    # 故意给 secret session 插正文
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('leak','cs_secret','agentsview','av:9',1,'user','leaked secret',13,NULL,NULL,0,0,'h','user')"
    )
    con.commit()
    con.close()
    assert _check_secret_searchable(canon) == 1


def test_av_only_lineage(tmp_path: Path) -> None:
    """AV-only session 都有 lineage link。"""
    canon = _make_canonical_for_cutover(tmp_path / "canon.db")
    count, all_have = _check_av_only_lineage(canon)
    assert count == 1  # cs_avonly
    assert all_have


def test_evaluate_gate_passed(tmp_path: Path) -> None:
    """完整 evaluate：gate 通过。"""
    canon = _make_canonical_for_cutover(tmp_path / "canon.db")
    legacy = _make_legacy_for_cutover(tmp_path / "legacy.db")

    report = evaluate(legacy_db=legacy, canonical_db=canon)
    assert report.secret_searchable_content == 0
    assert report.coverage_canonical_ge_legacy
    assert report.all_av_only_have_lineage
    assert report.gate_passed


def test_gate_fails_on_secret_leak(tmp_path: Path) -> None:
    """secret 正文泄露 → gate fail。"""
    canon = _make_canonical_for_cutover(tmp_path / "canon.db")
    con = sqlite3.connect(str(canon))
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('leak','cs_secret','agentsview','av:9',1,'user','leaked',6,NULL,NULL,0,0,'h','user')"
    )
    con.commit()
    con.close()
    legacy = _make_legacy_for_cutover(tmp_path / "legacy.db")

    report = evaluate(legacy_db=legacy, canonical_db=canon)
    assert not report.gate_passed
    assert report.secret_searchable_content > 0


def test_cutover_report_serializable(tmp_path: Path) -> None:
    """CutoverReport 可序列化为 dict。"""
    import json
    r = CutoverReport(generated_at="2026-01-01T00:00:00Z")
    d = r.to_dict()
    json.dumps(d)  # 不抛异常
    assert "gate_passed" not in d  # property 不进 dict
    assert d["secret_searchable_content"] == 0
