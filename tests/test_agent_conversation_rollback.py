"""Phase 13.5 Wave 5.2 测试：conversation source rollback。

覆盖 PLAN Task 5.2 固定流程：
  canonical shadow → promote canonical → rollback previous → switch legacy → restore canonical

每步验证：source-ref、secret eligibility、session-count smoke check。
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

from rollback_agent_conversation_source import (  # noqa: E402
    read_current_source,
    write_source_pointer,
    list_canonical_backups,
    smoke_check,
    switch_source,
    restore_backup,
)


def _make_legacy(dest: Path) -> Path:
    con = sqlite3.connect(str(dest))
    con.execute("CREATE TABLE agent_sessions_meta (session_id TEXT)")
    con.execute("CREATE TABLE agent_messages (session_id TEXT, event_index INTEGER, role TEXT, text TEXT)")
    con.execute("CREATE TABLE agent_tool_calls (session_id TEXT, call_id TEXT)")
    con.execute("INSERT INTO agent_sessions_meta VALUES ('s1'),('s2')")
    con.execute("INSERT INTO agent_messages VALUES ('s1',1,'user','hi')")
    con.commit()
    con.close()
    return dest


def _make_canonical(dest: Path, *, eligible: bool = True) -> Path:
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE canonical_sessions "
        "(canonical_session_id TEXT PRIMARY KEY, primary_source TEXT, agent TEXT, "
        "started_at TEXT, ended_at TEXT, message_count INTEGER, user_message_count INTEGER, "
        "file_hash TEXT, parent_canonical_id TEXT, relationship_type TEXT, cwd TEXT, "
        "git_branch TEXT, model TEXT, evidence_eligible INTEGER DEFAULT 1, "
        "evidence_scope TEXT DEFAULT 'user', merged INTEGER DEFAULT 0)"
    )
    cur.execute(
        "CREATE TABLE canonical_messages "
        "(canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, "
        "source_message_ref TEXT, ordinal INTEGER, role TEXT, content TEXT, "
        "content_length INTEGER, timestamp TEXT, model TEXT, is_system INTEGER, "
        "is_sidechain INTEGER, content_hash TEXT, evidence_scope TEXT)"
    )
    cur.execute(
        "CREATE TABLE canonical_tool_events "
        "(canonical_tool_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, "
        "source_kind TEXT, tool_name TEXT, category TEXT, status TEXT, call_index INTEGER, "
        "subagent_session_id TEXT, content_length INTEGER, timestamp TEXT)"
    )
    cur.execute(
        "CREATE TABLE session_source_links "
        "(link_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, "
        "source_session_id TEXT, source_raw_file TEXT, match_method TEXT, match_confidence TEXT)"
    )
    cur.execute(
        f"INSERT INTO canonical_sessions VALUES "
        f"('cs1','agentsview','codex','2026-01-01',NULL,1,1,NULL,NULL,NULL,NULL,NULL,NULL,"
        f"{1 if eligible else 0},'user',0)"
    )
    if eligible:
        cur.execute(
            "INSERT INTO canonical_messages VALUES "
            "('cm1','cs1','agentsview','av:1',1,'user','hello',5,'2026-01-01',NULL,0,0,'h','user')"
        )
    con.commit()
    con.close()
    return dest


def test_full_rollback_flow(tmp_path: Path) -> None:
    """PLAN 固定流程：shadow → promote → rollback → legacy → restore。"""
    # 用 tmp 目录隔离指针文件
    import rollback_agent_conversation_source as rb
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    rb.SOURCE_POINTER = db_dir / "conversation_source.txt"
    rb.ROLLBACK_LOG = db_dir / "rollback_log.jsonl"

    legacy = _make_legacy(tmp_path / "legacy.db")
    canonical = _make_canonical(tmp_path / "canonical.db")

    # 0. 初始：legacy
    assert read_current_source() == "legacy"

    # 1. shadow check：canonical smoke 通过
    smoke = smoke_check("canonical", legacy, canonical)
    assert smoke["ok"]
    assert smoke["session_count"] == 1

    # 2. promote canonical（--write）
    action = switch_source("canonical", write=True, legacy_db=legacy, canonical_db=canonical)
    assert action.smoke_checks["ok"]
    assert read_current_source() == "canonical"

    # 3. rollback to legacy（--write）
    action = switch_source("legacy", write=True, legacy_db=legacy, canonical_db=canonical)
    assert read_current_source() == "legacy"

    # 4. restore canonical
    action = switch_source("canonical", write=True, legacy_db=legacy, canonical_db=canonical)
    assert read_current_source() == "canonical"

    # 5. 每步都有 session-count > 0
    for src in ("legacy", "canonical"):
        s = smoke_check(src, legacy, canonical)
        assert s["ok"], f"{src} smoke failed: {s}"


def test_dry_run_no_modification(tmp_path: Path) -> None:
    """dry-run 不修改 source 指针。"""
    import rollback_agent_conversation_source as rb
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    rb.SOURCE_POINTER = db_dir / "conversation_source.txt"

    legacy = _make_legacy(tmp_path / "legacy.db")
    canonical = _make_canonical(tmp_path / "canonical.db")

    assert read_current_source() == "legacy"
    action = switch_source("canonical", write=False, legacy_db=legacy, canonical_db=canonical)
    assert not action.will_modify
    assert read_current_source() == "legacy"  # 未变


def test_switch_to_canonical_requires_db(tmp_path: Path) -> None:
    """canonical DB 不存在时不能切到 canonical。"""
    import rollback_agent_conversation_source as rb
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    rb.SOURCE_POINTER = db_dir / "conversation_source.txt"

    legacy = _make_legacy(tmp_path / "legacy.db")
    nonexistent = tmp_path / "nope.db"

    action = switch_source("canonical", write=True, legacy_db=legacy, canonical_db=nonexistent)
    assert not action.smoke_checks.get("ok")
    assert "error" in action.smoke_checks
    assert read_current_source() == "legacy"  # 未切换


def test_secret_smoke_check_detects_leak(tmp_path: Path) -> None:
    """canonical smoke 检出 secret 正文泄露。"""
    legacy = _make_legacy(tmp_path / "legacy.db")
    canonical = _make_canonical(tmp_path / "canonical.db", eligible=False)
    # 故意给 ineligible session 插正文
    con = sqlite3.connect(str(canonical))
    con.execute(
        "INSERT INTO canonical_messages VALUES "
        "('leak','cs1','agentsview','av:9',1,'user','secret content',13,NULL,NULL,0,0,'h','user')"
    )
    con.commit()
    con.close()

    smoke = smoke_check("canonical", legacy, canonical)
    assert not smoke["ok"]
    assert smoke["secret_searchable"] > 0


def test_list_backups(tmp_path: Path) -> None:
    """list_canonical_backups 返回 current + backup 文件。"""
    canonical = _make_canonical(tmp_path / "canonical.db")
    # 造一个 backup
    import shutil
    shutil.copy2(canonical, tmp_path / "canonical.backup.sqlite")
    backups = list_canonical_backups()
    # list_canonical_backups 用默认路径，这里直接验证逻辑
    # 在隔离环境下重新指向 tmp
    import rollback_agent_conversation_source as rb
    rb.AGENT_CONVERSATIONS_DB = canonical
    backups = rb.list_canonical_backups()
    assert "current" in backups


def test_rollback_log_appended(tmp_path: Path) -> None:
    """--write 操作追加到 rollback log。"""
    import rollback_agent_conversation_source as rb
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    rb.SOURCE_POINTER = db_dir / "conversation_source.txt"
    rb.ROLLBACK_LOG = db_dir / "rollback_log.jsonl"

    legacy = _make_legacy(tmp_path / "legacy.db")
    canonical = _make_canonical(tmp_path / "canonical.db")

    switch_source("canonical", write=True, legacy_db=legacy, canonical_db=canonical)
    switch_source("legacy", write=True, legacy_db=legacy, canonical_db=canonical)

    import json
    lines = rb.ROLLBACK_LOG.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        entry = json.loads(line)
        assert "action" in entry
        assert "timestamp" in entry
