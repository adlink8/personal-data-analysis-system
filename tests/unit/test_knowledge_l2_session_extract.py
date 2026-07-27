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
