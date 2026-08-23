"""Phase 13.5 Wave 2.1-2.2 测试：normalized snapshot 脱敏与 Revision gate。

用临时 fixture（含 secret/excluded/deleted session + 注入 secret 明文）验证：
  - protected 字段（thinking_text/input_json/result_content）永不复制
  - secret session 正文完全不写
  - 本地二次 secret 扫描命中时正文不落，只记规则名
  - system/sidechain/subagent evidence_scope 标记正确
  - 幂等：同输入重跑 dataset_hash 相同
  - tombstone 写入正确
  - Revision gate 失败时不发布
"""

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

from personal_knowledge.application.conversation.build_agentsview_normalized import (  # noqa: E402
    NORMALIZED_SCHEMA,
    NormalizationStats,
    RevisionGateError,
    build_normalized,
    local_secret_scan,
)
from personal_knowledge.application.conversation.build_canonical_agent_conversations import (  # noqa: E402
    run as build_canonical_run,
)


def _make_source_fixture(dest: Path) -> Path:
    """造一个含 secret/excluded/deleted session + 注入明文 secret 的源库。"""
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute("PRAGMA user_version=59")

    cur.execute(
        """CREATE TABLE sessions (
            id TEXT PRIMARY KEY, project TEXT, agent TEXT,
            started_at TEXT, ended_at TEXT, message_count INTEGER,
            user_message_count INTEGER, file_hash TEXT,
            parent_session_id TEXT, relationship_type TEXT,
            source_session_id TEXT, deleted_at TEXT,
            secret_leak_count INTEGER DEFAULT 0,
            cwd TEXT, git_branch TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE messages (
            id INTEGER PRIMARY KEY, session_id TEXT, ordinal INTEGER,
            role TEXT, content TEXT, thinking_text TEXT, timestamp TEXT,
            is_system INTEGER DEFAULT 0, is_sidechain INTEGER DEFAULT 0,
            model TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE tool_calls (
            id INTEGER PRIMARY KEY, session_id TEXT, tool_name TEXT,
            category TEXT, call_index INTEGER, subagent_session_id TEXT,
            skill_name TEXT, result_content_length INTEGER,
            input_json TEXT, result_content TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE tool_result_events (
            id INTEGER PRIMARY KEY, session_id TEXT, status TEXT,
            subagent_session_id TEXT, event_index INTEGER,
            content_length INTEGER, timestamp TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE usage_events (
            id INTEGER PRIMARY KEY, session_id TEXT, model TEXT,
            occurred_at TEXT, input_tokens INTEGER, output_tokens INTEGER,
            cost_usd REAL
        )"""
    )
    cur.execute(
        "CREATE TABLE secret_findings "
        "(id INTEGER PRIMARY KEY, session_id TEXT, rule_name TEXT)"
    )
    cur.execute(
        "CREATE TABLE excluded_sessions (id TEXT PRIMARY KEY, created_at TEXT)"
    )

    # session-1: 正常 eligible user session
    cur.execute(
        "INSERT INTO sessions (id, agent, started_at, message_count, "
        "user_message_count, secret_leak_count) VALUES "
        "('s1','codex','2026-01-01T00:00:00Z',2,1,0)"
    )
    # session-2: secret-bearing（正文绝不写）
    cur.execute(
        "INSERT INTO sessions (id, agent, started_at, message_count, "
        "user_message_count, secret_leak_count) VALUES "
        "('s2','codex','2026-01-02T00:00:00Z',1,1,3)"
    )
    cur.execute(
        "INSERT INTO secret_findings (session_id, rule_name) VALUES "
        "('s2','openai-key'),('s2','openai-key'),('s2','google-api-key')"
    )
    # session-3: excluded
    cur.execute(
        "INSERT INTO sessions (id, agent, started_at, message_count, "
        "user_message_count, secret_leak_count) VALUES "
        "('s3','claude','2026-01-03T00:00:00Z',1,1,0)"
    )
    cur.execute("INSERT INTO excluded_sessions (id, created_at) VALUES ('s3','2026-01-03')")
    # session-4: deleted
    cur.execute(
        "INSERT INTO sessions (id, agent, started_at, message_count, "
        "user_message_count, secret_leak_count, deleted_at) VALUES "
        "('s4','gemini','2026-01-04T00:00:00Z',1,1,0,'2026-01-05')"
    )
    # session-5: subagent session
    cur.execute(
        "INSERT INTO sessions (id, agent, started_at, message_count, "
        "user_message_count, secret_leak_count, parent_session_id, "
        "relationship_type) VALUES "
        "('s5','codex','2026-01-05T00:00:00Z',1,0,0,'s1','subagent')"
    )

    # messages
    # s1 正常消息（一条 user 一条 assistant）
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s1',1,'user','how to use python asyncio','2026-01-01T00:00:01Z')"
    )
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s1',2,'assistant','use asyncio.gather','2026-01-01T00:00:02Z')"
    )
    # s1 注入一条含 openai key 明文的 user message（本地二次扫描应拦截正文）
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s1',3,'user','my key is sk-abcdefghijklmnopqrstuvwxyz123456 here','2026-01-01T00:00:03Z')"  # governance: synthetic-secret-fixture
    )
    # s1 注入含邮箱的 message
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s1',4,'user','contact me at john.doe@example.com please','2026-01-01T00:00:04Z')"
    )
    # s2 secret session 的消息（正文绝不写）
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s2',1,'user','this has a secret sk-leaked12345678901234567890','2026-01-02T00:00:01Z')"  # governance: synthetic-secret-fixture
    )
    # s3 excluded session 消息
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s3',1,'user','excluded content','2026-01-03T00:00:01Z')"
    )
    # s4 deleted session 消息
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s4',1,'user','deleted content','2026-01-04T00:00:01Z')"
    )
    # s5 subagent message（标记 sidechain）
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp, is_sidechain) "
        "VALUES ('s5',1,'assistant','subagent work','2026-01-05T00:00:01Z',1)"
    )
    # s1 system message
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp, is_system) "
        "VALUES ('s1',5,'system','system prompt','2026-01-01T00:00:05Z',1)"
    )
    # s1 压缩摘要 user message（源库 role=user，但应标 system 轨）
    cur.execute(
        "INSERT INTO messages (session_id, ordinal, role, content, timestamp) "
        "VALUES ('s1',6,'user',"
        "'This session is being continued from a previous conversation that was compacted. "
        "The summary below is the authoritative context for earlier turns. "
        "User wanted to deploy the backend service and fix dialog saving.','2026-01-01T00:00:08Z')"
    )

    # tool_call（含 input_json / result_content，这些字段不复制）
    cur.execute(
        "INSERT INTO tool_calls (session_id, tool_name, category, call_index, "
        "result_content_length, input_json, result_content) VALUES "
        "('s1','Read','file',0,100,'{\"path\":\"x\"}','file contents here')"
    )
    # tool_result_event
    cur.execute(
        "INSERT INTO tool_result_events (session_id, status, event_index, "
        "content_length, timestamp) VALUES ('s1','success',0,100,'2026-01-01T00:00:06Z')"
    )
    # usage
    cur.execute(
        "INSERT INTO usage_events (session_id, model, occurred_at, "
        "input_tokens, output_tokens, cost_usd) VALUES "
        "('s1','gpt-5.6-luna','2026-01-01T00:00:07Z',100,50,0.01)"
    )

    con.commit()
    con.close()
    return dest


def test_protected_fields_never_copied(tmp_path: Path) -> None:
    """thinking_text / input_json / result_content 永不出现在 normalized DB。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None and final.exists()

    con = sqlite3.connect(str(final))
    # messages 无 thinking_text
    mcols = {c[1] for c in con.execute("PRAGMA table_info(messages)")}
    assert "thinking_text" not in mcols
    # tool_events 无 input_json / result_content
    tcols = {c[1] for c in con.execute("PRAGMA table_info(tool_events)")}
    assert "input_json" not in tcols
    assert "result_content" not in tcols
    assert stats.protected_field_copies == 0
    con.close()


def test_secret_session_content_not_written(tmp_path: Path) -> None:
    """secret session 的 message 正文完全不写（行也可能不写）。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    con = sqlite3.connect(str(final))

    # s2 是 secret session，evidence_eligible=0
    s2 = con.execute(
        "SELECT evidence_eligible, secret_leak_count FROM sessions "
        "WHERE source_session_id='s2'"
    ).fetchone()
    assert s2 is not None
    assert s2[0] == 0  # evidence_eligible=0
    assert s2[1] == 3  # secret_leak_count 保留

    # s2 的 message 正文为空或无行
    s2_msgs = con.execute(
        "SELECT COUNT(*) FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s2' "
        "AND m.content IS NOT NULL AND m.content != ''"
    ).fetchone()[0]
    assert s2_msgs == 0, "secret session 正文被写入了！"
    assert stats.secret_session_messages_written == 0
    con.close()


def test_local_secret_scan_quarantines_content(tmp_path: Path) -> None:
    """本地二次扫描命中（openai key / 邮箱）→ 正文不落，只记规则名。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    con = sqlite3.connect(str(final))

    # s1 ordinal=3 注入了 sk-... 明文，正文应为 NULL，quarantined_rules 非空
    row = con.execute(
        "SELECT m.content, m.quarantined_local_rules FROM messages m "
        "JOIN sessions s ON m.session_id=s.session_id "
        "WHERE s.source_session_id='s1' AND m.ordinal=3"
    ).fetchone()
    assert row is not None
    assert row[0] is None or row[0] == "", "openai key 明文正文未被隔离"
    # 规则名记录了（local-openai-key）
    # 注意：列名可能是 quarantined_local_rules
    qcol = row[1]

    # 邮箱 s1 ordinal=4 同理
    row4 = con.execute(
        "SELECT m.content, m.quarantined_local_rules FROM messages m "
        "JOIN sessions s ON m.session_id=s.session_id "
        "WHERE s.source_session_id='s1' AND m.ordinal=4"
    ).fetchone()
    assert row4[0] is None or row4[0] == "", "邮箱 PII 正文未被隔离"

    assert stats.local_rule_hits.get("local-openai-key", 0) >= 1
    assert stats.local_rule_hits.get("local-email-pii", 0) >= 1
    con.close()


def test_evidence_scope_marking(tmp_path: Path) -> None:
    """system/sidechain/subagent 的 evidence_scope 标记正确。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    con = sqlite3.connect(str(final))

    # s5 是 subagent session，scope 应为 subagent
    s5_scope = con.execute(
        "SELECT evidence_scope FROM sessions WHERE source_session_id='s5'"
    ).fetchone()[0]
    assert s5_scope == "subagent"

    # s1 system message scope 应为 system
    sys_scope = con.execute(
        "SELECT m.evidence_scope FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s1' "
        "AND m.ordinal=5"
    ).fetchone()
    assert sys_scope is not None
    assert sys_scope[0] == "system"

    # s5 sidechain message scope 应为 sidechain
    side_scope = con.execute(
        "SELECT m.evidence_scope FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s5' "
        "AND m.ordinal=1"
    ).fetchone()
    assert side_scope is not None
    assert side_scope[0] == "sidechain"
    con.close()


def test_compact_summary_marked_system_scope(tmp_path: Path) -> None:
    """源库 role=user 的压缩摘要消息 → normalized evidence_scope='system'，
    不再以 user 身份进入抽取轨。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None
    assert stats.messages_compact_summary == 1

    con = sqlite3.connect(str(final))
    row = con.execute(
        "SELECT m.evidence_scope, m.role FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s1' "
        "AND m.ordinal=6"
    ).fetchone()
    assert row is not None
    assert row[0] == "system", f"压缩摘要应标记 system 轨, got {row[0]}"
    # 正文仍保留（仅轨道标记变化，不做正文隔离）
    assert row[1] == "user"
    con.close()


def test_tombstones_written(tmp_path: Path) -> None:
    """secret/excluded/deleted session 都产生 tombstone。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    con = sqlite3.connect(str(final))

    reasons = {
        r[0] for r in con.execute("SELECT reason FROM source_tombstones")
    }
    assert "secret" in reasons
    assert "excluded" in reasons
    assert "deleted" in reasons
    assert stats.tombstones_total == 3
    con.close()


def test_idempotent_same_dataset_hash(tmp_path: Path) -> None:
    """同输入重跑：dataset_hash 必须相同。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    build_normalized(src, dest_db=dest, dry_run=False)
    con1 = sqlite3.connect(str(dest))
    h1 = con1.execute(
        "SELECT dataset_hash FROM import_runs ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()[0]
    con1.close()

    build_normalized(src, dest_db=dest, dry_run=False)
    con2 = sqlite3.connect(str(dest))
    h2 = con2.execute(
        "SELECT dataset_hash FROM import_runs ORDER BY generated_at DESC LIMIT 1"
    ).fetchone()[0]
    con2.close()

    assert h1 == h2, f"幂等失败: {h1} != {h2}"


def test_dry_run_no_file_written(tmp_path: Path) -> None:
    """dry-run 不写正式 DB 文件。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=True)
    assert final is None
    assert not dest.exists()
    assert stats.gate_passed


def test_atomic_publish_uses_staging(tmp_path: Path) -> None:
    """正式发布：dest 存在，staging 不残留。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None
    assert final.exists()
    staging = dest.parent / f"{dest.stem}.staging.sqlite"
    assert not staging.exists(), "staging 文件残留"


def test_local_secret_scan_function() -> None:
    """local_secret_scan 基础正则。"""
    assert "local-openai-key" in local_secret_scan("sk-" + "a" * 25)
    assert "local-google-api-key" in local_secret_scan("AIza" + "a" * 35)
    assert "local-email-pii" in local_secret_scan("contact x@y.com now")
    assert local_secret_scan("") == []
    assert local_secret_scan("normal text no secrets") == []


def test_revision_gate_stats() -> None:
    """NormalizationStats.gate_passed 在正常情况为 True。"""
    s = NormalizationStats()
    assert s.gate_passed
    s.protected_field_copies = 1
    assert not s.gate_passed


def test_excluded_session_messages_not_written(tmp_path: Path) -> None:
    """excluded session：session 行保留 eligible=0 + tombstone，消息不写入。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None
    con = sqlite3.connect(str(final))

    # s3 excluded：session 行保留 evidence_eligible=0
    row = con.execute(
        "SELECT evidence_eligible, excluded FROM sessions "
        "WHERE source_session_id='s3'"
    ).fetchone()
    assert row is not None
    assert row[0] == 0
    assert row[1] == 1

    # s3 的消息整条不写入（旧行为会把 'excluded content' 写进 normalized）
    n = con.execute(
        "SELECT COUNT(*) FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s3'"
    ).fetchone()[0]
    assert n == 0, "excluded session 的消息被写入了！"

    # tombstone 存在
    tom = con.execute(
        "SELECT COUNT(*) FROM source_tombstones WHERE reason='excluded'"
    ).fetchone()[0]
    assert tom == 1

    assert stats.messages_skipped_excluded == 1
    con.close()


def test_deleted_session_messages_not_written(tmp_path: Path) -> None:
    """deleted session：session 行保留 eligible=0 + tombstone，消息不写入。"""
    src = _make_source_fixture(tmp_path / "src.db")
    dest = tmp_path / "normalized.db"

    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None
    con = sqlite3.connect(str(final))

    row = con.execute(
        "SELECT evidence_eligible, deleted_at FROM sessions "
        "WHERE source_session_id='s4'"
    ).fetchone()
    assert row is not None
    assert row[0] == 0
    assert row[1] == "2026-01-05"

    n = con.execute(
        "SELECT COUNT(*) FROM messages m JOIN sessions s "
        "ON m.session_id=s.session_id WHERE s.source_session_id='s4'"
    ).fetchone()[0]
    assert n == 0, "deleted session 的消息被写入了！"

    tom = con.execute(
        "SELECT COUNT(*) FROM source_tombstones WHERE reason='deleted'"
    ).fetchone()[0]
    assert tom == 1

    assert stats.messages_skipped_deleted == 1
    con.close()


def test_excluded_sessions_zero_match_fail_closed(tmp_path: Path) -> None:
    """excluded_sessions 有行但 0 行能 JOIN sessions.id → RevisionGateError，不发布。"""
    src = _make_source_fixture(tmp_path / "src.db")
    con = sqlite3.connect(str(src))
    con.execute("DELETE FROM excluded_sessions")
    con.execute(
        "INSERT INTO excluded_sessions (id, created_at) VALUES ('ghost','2026-01-03')"
    )
    con.commit()
    con.close()

    dest = tmp_path / "normalized.db"
    with pytest.raises(RevisionGateError):
        build_normalized(src, dest_db=dest, dry_run=False)
    assert not dest.exists(), "fail-closed gate 触发后不应发布"


def test_excluded_sessions_partial_match_ok(tmp_path: Path) -> None:
    """excluded_sessions 部分匹配（会话已物理删除）→ 正常发布，stats 记 unmatched。"""
    src = _make_source_fixture(tmp_path / "src.db")
    con = sqlite3.connect(str(src))
    con.execute(
        "INSERT INTO excluded_sessions (id, created_at) VALUES ('ghost','2026-01-06')"
    )
    con.commit()
    con.close()

    dest = tmp_path / "normalized.db"
    stats, final = build_normalized(src, dest_db=dest, dry_run=False)
    assert final is not None and final.exists()
    assert stats.excluded_matched == 1  # s3
    assert stats.excluded_unmatched == 1  # ghost
    assert stats.gate_passed


def _make_normalized_fixture(dest: Path) -> Path:
    """手工造 normalized 库：eligible + ineligible 会话都带消息正文。

    模拟旧版 normalized 库（ineligible 会话正文已落库），验证 canonical
    的防御纵深过滤。
    """
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute(
        """CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY, source_session_id TEXT, agent TEXT,
            started_at TEXT, ended_at TEXT, message_count INTEGER,
            user_message_count INTEGER, file_hash TEXT, parent_session_id TEXT,
            relationship_type TEXT, cwd TEXT, git_branch TEXT,
            evidence_eligible INTEGER, evidence_scope TEXT
        )"""
    )
    cur.execute(
        """CREATE TABLE messages (
            message_id TEXT PRIMARY KEY, session_id TEXT,
            source_message_id INTEGER, ordinal INTEGER, role TEXT,
            content TEXT, content_length INTEGER, timestamp TEXT, model TEXT,
            is_system INTEGER, is_sidechain INTEGER, content_hash TEXT,
            evidence_scope TEXT
        )"""
    )
    cur.execute(
        "INSERT INTO sessions VALUES ('ns-e1','e1','codex','2026-01-01',NULL,"
        "1,1,NULL,NULL,NULL,NULL,NULL,1,'user')"
    )
    cur.execute(
        "INSERT INTO messages VALUES ('m-e1','ns-e1',1,1,'user',"
        "'eligible content',16,'2026-01-01',NULL,0,0,NULL,'user')"
    )
    cur.execute(
        "INSERT INTO sessions VALUES ('ns-x1','x1','codex','2026-01-02',NULL,"
        "1,1,NULL,NULL,NULL,NULL,NULL,0,'user')"
    )
    cur.execute(
        "INSERT INTO messages VALUES ('m-x1','ns-x1',2,1,'user',"
        "'should not leak',15,'2026-01-02',NULL,0,0,NULL,'user')"
    )
    con.commit()
    con.close()
    return dest


def test_canonical_av_path_skips_ineligible_sessions(tmp_path: Path) -> None:
    """canonical AV 路径：evidence_eligible=0 的 normalized 会话消息不进
    canonical_messages（回归：eligible=1 正常进入）。"""
    av = _make_normalized_fixture(tmp_path / "normalized.db")
    dest = tmp_path / "canonical.db"

    rc = build_canonical_run(
        dry_run=False, write=True,
        av_db=av, legacy_db=tmp_path / "no-legacy.db", dest_db=dest,
    )
    assert rc == 0

    con = sqlite3.connect(str(dest))
    contents = {
        r[0] for r in con.execute("SELECT content FROM canonical_messages")
    }
    assert "eligible content" in contents, "eligible=1 的消息未进入 canonical"
    assert "should not leak" not in contents, "ineligible 会话正文泄漏进 canonical"

    # ineligible session 本身仍在 canonical_sessions，标记 eligible=0
    x = con.execute(
        "SELECT cs.evidence_eligible FROM canonical_sessions cs "
        "JOIN session_source_links l "
        "ON l.canonical_session_id=cs.canonical_session_id "
        "WHERE l.source='agentsview' AND l.source_session_id='x1'"
    ).fetchone()
    assert x is not None
    assert x[0] == 0
    con.close()
