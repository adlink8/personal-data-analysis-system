"""L2 session-window dual-pass extraction helpers (no live LLM)."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.domains.knowledge.extract_knowledge_units_l2_session import (  # noqa: E402
    build_window,
    list_l2_sessions,
    _best_message_for_quote,
    _evidence_supported,
    _partition_chunks,
)


def test_evidence_supported_exact_and_fragment() -> None:
    src = "用户习惯使用 PowerShell 做本机操作并且喜欢 JSON 输出"
    assert _evidence_supported("习惯使用 PowerShell 做本机操作", src)
    assert not _evidence_supported("完全不相关的句子啊啊啊啊啊啊", src)


def test_best_message_for_quote() -> None:
    msgs = [
        {"message_id": "cm|a", "cleaned": "无关内容" * 5},
        {"message_id": "cm|b", "cleaned": "我决定用 SQLite 作为主库存储个人数据系统"},
    ]
    assert _best_message_for_quote("用 SQLite 作为主库", msgs) == "cm|b"
    assert _best_message_for_quote("不存在的片段zzzzzzzzzz", msgs) is None


def test_build_window_keeps_recent_under_budget() -> None:
    msgs = [
        {"message_id": f"cm|{i}", "cleaned": ("alpha " * 30) + str(i)} for i in range(8)
    ]
    selected, text = build_window(msgs, max_chars=800)
    assert selected
    assert "msg cm|" in text
    # newest should be present
    assert any(m["message_id"] == "cm|7" for m in selected)


def test_partition_chunks_respects_budget_order_and_determinism() -> None:
    msgs = [{"message_id": f"cm|{i}", "cleaned": "内容" * 500 + str(i)} for i in range(10)]
    chunks = _partition_chunks(msgs, 3500)
    assert len(chunks) == 4  # 每块至多 3 条（3*(1002+24)=3078），10 条 → 3/3/3/1
    assert [len(c) for c in chunks] == [3, 3, 3, 1]
    for ch in chunks:
        assert sum(len(m["cleaned"]) + 24 for m in ch) <= 3500
    # 时间序保持、不丢消息
    assert [m["message_id"] for c in chunks for m in c] == [m["message_id"] for m in msgs]
    # 确定性：同输入必得同分块（重跑幂等）
    assert _partition_chunks(msgs, 3500) == chunks


def test_list_l2_sessions_chunks_long_sessions(tmp_path: Path) -> None:
    import sqlite3

    canon = tmp_path / "canon.db"
    con = sqlite3.connect(canon)
    con.execute(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, "
        "agent TEXT, started_at TEXT, evidence_eligible INTEGER NOT NULL DEFAULT 1)"
    )
    con.execute(
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, "
        "canonical_session_id TEXT, source TEXT, ordinal INTEGER, role TEXT, "
        "content TEXT, timestamp TEXT)"
    )
    con.execute("INSERT INTO canonical_sessions VALUES ('long1', 'test', '2026-07-01', 1)")
    con.execute("INSERT INTO canonical_sessions VALUES ('short1', 'test', '2026-07-02', 1)")
    # 长会话：60 条 × 2000 字 = 120k > 48k → 分块
    for i in range(60):
        con.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?)",
            (f"cm|L{i}", "long1", "test", i, "user", f"第{i}条" + "材" * 2000, f"2026-07-01T{i:02d}:00:00"),
        )
    # 短会话：2 条 → 不分块
    for i in range(2):
        con.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?,?,?)",
            (f"cm|S{i}", "short1", "test", i, "user", f"短会话第{i}条内容，超过二十个字的阈值。" * 2, f"2026-07-02T10:0{i}:00"),
        )
    con.commit()
    con.close()

    sessions = list_l2_sessions(canon, min_user_msgs=2, limit=None)
    long_sessions = [s for s in sessions if s["source_session_id"] == "long1"]
    short_sessions = [s for s in sessions if s["source_session_id"] == "short1"]
    assert len(long_sessions) >= 3  # 120k/48k → ≥3 块
    assert all(s["session_id"].startswith("long1#c") for s in long_sessions)
    assert all(s["chunk_count"] == len(long_sessions) for s in long_sessions)
    # 块间消息不重叠、并集覆盖全部 60 条（单条 ≤48k，无硬截）
    ids = [mid for s in long_sessions for mid in s["message_ids"]]
    assert len(ids) == len(set(ids)) == 60
    # 短会话：id 不带后缀，行为与 v1 一致
    assert [s["session_id"] for s in short_sessions] == ["short1"]
    assert short_sessions[0]["chunk_count"] == 1


def test_dedup_key_matches_eval_metric_definition() -> None:
    """PDA-5a: dedup key must equal extraction_quality duplication() key."""
    from personal_knowledge.application.knowledge.extract_knowledge_units_l2_session import (
        _dedup_key,
    )

    assert _dedup_key("project_decision", "  项目三  ", "需要新建一个issue来记录和跟踪") == (
        "project_decision|项目三|需要新建一个issue来记录和跟踪"
    )
    # case/whitespace normalization + 120-char answer prefix (eval uses [:120])
    long_answer = "答" * 200
    assert _dedup_key("preference", "git分支", long_answer) == (
        "preference|git分支|" + "答" * 120
    )
    # 大小写/首尾空白归一化（与 eval 一致：strip + lower，不折叠内部空白）
    assert _dedup_key("preference", "Git 分支", "main") == _dedup_key(
        "preference", "  git 分支  ", " MAIN "
    )
    assert _dedup_key("preference", "git分支", "main") != _dedup_key(
        "preference", "git 分支", "main"
    )
    # unit_type is part of the key
    assert _dedup_key("preference", "s", "a") != _dedup_key("habit", "s", "a")


def test_load_session_l2_keys_only_active_same_session(tmp_path) -> None:
    import sqlite3

    from personal_knowledge.application.knowledge.extract_knowledge_units_l2_session import (
        _dedup_key,
        _load_session_l2_keys,
    )

    db = tmp_path / "ku.sqlite"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE knowledge_units (unit_id TEXT, unit_type TEXT, subject TEXT, "
        "answer TEXT, source_session_id TEXT, status TEXT)"
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?)",
        [
            ("l2|1", "project_decision", "项目三", "需要新建一个issue来记录和跟踪", "cs|s1", "current"),
            ("l2|3", "preference", "用户", "偏好图片说明", "cs|s1", "rejected"),
            ("l2|4", "project_decision", "项目三", "先建主干issue", "cs|s1", "current"),
            # 同 key 只在 cs|s2 出现：跨会话同事实是合法重复知识，不去重
            ("l2|2", "project_decision", "项目三", "需要新建一个issue来记录和跟踪", "cs|s2", "current"),
        ],
    )
    con.commit()
    keys = _load_session_l2_keys(con, "cs|s1")
    assert _dedup_key("project_decision", "项目三", "需要新建一个issue来记录和跟踪") in keys
    assert _dedup_key("project_decision", "项目三", "先建主干issue") in keys
    assert _dedup_key("preference", "用户", "偏好图片说明") not in keys
    # 去重作用域是同一真实会话：cs|s2 的同 key 单元不会出现在 cs|s1 的视图里，
    # 但独立查询 cs|s2 能看到它（各会话独立，互相不构成重复）
    keys_s2 = _load_session_l2_keys(con, "cs|s2")
    assert _dedup_key("project_decision", "项目三", "需要新建一个issue来记录和跟踪") in keys_s2
    con.close()


def test_mark_l2_duplicates_marks_second_occurrence_only(tmp_path) -> None:
    import sqlite3

    from personal_knowledge.application.knowledge.extract_knowledge_units_l2_session import (
        mark_l2_duplicates,
    )

    db = tmp_path / "ku.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE knowledge_units (unit_id TEXT PRIMARY KEY, unit_type TEXT, "
        "subject TEXT, answer TEXT, lifecycle TEXT, status TEXT, source_session_id TEXT, "
        "supersedes_id TEXT)"
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?,?,?)",
        [
            # duplicate pair (same session, cross-run like pilot+full)
            ("l2|aa", "project_decision", "项目三", "需要新建一个issue来记录和跟踪", "current", "current", "cs|s1", None),
            ("l2|bb", "project_decision", "项目三", "需要新建一个issue来记录和跟踪", "current", "current", "cs|s1", None),
            # unique unit
            ("l2|cc", "preference", "用户", "偏好图片说明", "current", "current", "cs|s2", None),
            # already-deprecated dup must not be re-marked (idempotency)
            ("l2|dd", "preference", "用户", "偏好图片说明", "deprecated", "current", "cs|s2", None),
        ],
    )
    con.commit()
    con.close()

    report = mark_l2_duplicates(db, write=True)
    assert report["duplicate_units"] == 2
    assert report["already_deprecated"] == 1
    assert report["to_mark"] == 1
    assert report["writes"] == 1

    con = sqlite3.connect(db)
    assert con.execute("SELECT lifecycle FROM knowledge_units WHERE unit_id='l2|bb'").fetchone()[0] == "deprecated"
    assert con.execute("SELECT supersedes_id FROM knowledge_units WHERE unit_id='l2|bb'").fetchone()[0] == "l2|aa"
    assert con.execute("SELECT lifecycle FROM knowledge_units WHERE unit_id='l2|aa'").fetchone()[0] == "current"
    assert con.execute("SELECT lifecycle FROM knowledge_units WHERE unit_id='l2|dd'").fetchone()[0] == "deprecated"
    con.close()


def test_mark_l2_duplicates_dry_run_no_write(tmp_path) -> None:
    import sqlite3

    from personal_knowledge.application.knowledge.extract_knowledge_units_l2_session import (
        mark_l2_duplicates,
    )

    db = tmp_path / "ku.sqlite"
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE knowledge_units (unit_id TEXT PRIMARY KEY, unit_type TEXT, "
        "subject TEXT, answer TEXT, lifecycle TEXT, status TEXT, source_session_id TEXT, "
        "supersedes_id TEXT)"
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?,?,?)",
        [
            ("l2|aa", "preference", "用户", "偏好图片说明", "current", "current", "cs|s1", None),
            ("l2|bb", "preference", "用户", "偏好图片说明", "current", "current", "cs|s1", None),
        ],
    )
    con.commit()
    con.close()
    report = mark_l2_duplicates(db, write=False)
    assert report["writes"] == 0
    con = sqlite3.connect(db)
    assert con.execute("SELECT lifecycle FROM knowledge_units WHERE unit_id='l2|bb'").fetchone()[0] == "current"
    con.close()
