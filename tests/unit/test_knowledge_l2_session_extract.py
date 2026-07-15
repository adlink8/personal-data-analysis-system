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
    _best_message_for_quote,
    _evidence_supported,
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
