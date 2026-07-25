"""Finding F-01：prod 路径 evidence gate 测试。

_commit_item_result 应对每条 unit 做 evidence 回查（≥10 字连续片段命中原文），
对不上的 unit 丢弃并计入 units_dropped_no_evidence，不影响同 item 其余 unit；
全部丢弃时 item 仍记 succeeded（unit_count=0）。
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.domains.knowledge.build_knowledge_units_prod import (  # noqa: E402
    _commit_item_result,
    _evidence_supported,
)

CLEANED = "用户明确说过：只喝无糖可乐，会议前不要安排闲聊，项目代号是灯塔计划。"


def _setup_db(db: Path) -> tuple[sqlite3.Connection, int]:
    """建 schema + 一条 in_flight run item，返回 (con, row_id)。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_run_items "
        "(run_id, inventory_id, position, evidence_ref, status, attempt_count, "
        "lease_started_at, last_error_class, cache_key, response_hash, unit_count, updated_at) "
        "VALUES ('run1','inv1',0,'cm0','in_flight',1,NULL,NULL,NULL,NULL,0,'2026-01-01')"
    )
    con.commit()
    row_id = con.execute(
        "SELECT id FROM knowledge_run_items WHERE run_id='run1'"
    ).fetchone()[0]
    return con, row_id


def _stats() -> dict:
    return {
        "processed": 0, "succeeded": 0, "abstained": 0, "failed": 0,
        "cache_hits": 0, "units": 0, "units_dropped_no_evidence": 0,
        "workers": 1, "rate_limited": 0, "stopped_reason": "",
    }


def _unit(quote: str) -> dict:
    return {
        "unit_type": "preference",
        "subject": "用户偏好",
        "question": "用户喝什么？",
        "answer": "无糖可乐",
        "confidence": 0.9,
        "evidence_quote": quote,
        "lifecycle": "current",
    }


def _work(raw_text: str) -> dict:
    return {
        "kind": "ok",
        "raw_text": raw_text,
        "cleaned": CLEANED,
        "cache_key": "ck",
        "input_hash": hashlib.sha256(CLEANED.encode()).hexdigest()[:32],
        "write_cache": False,
    }


def _commit(con: sqlite3.Connection, row_id: int, units: list[dict]) -> dict:
    stats = _stats()
    raw_text = json.dumps({"units": units, "abstain": False, "abstain_reason": ""})
    item = {"row_id": row_id, "position": 0, "evidence_ref": "cm0",
            "status": "in_flight", "attempt_count": 1}
    _commit_item_result(con, "run1", item, _work(raw_text), "m", "ph", "sh", "ch", stats)
    return stats


# === _evidence_supported 规则 ===

def test_evidence_supported_exact() -> None:
    assert _evidence_supported("只喝无糖可乐", CLEANED) is True


def test_evidence_supported_10char_window() -> None:
    """quote 非精确子串，但含 ≥10 字连续片段命中原文。"""
    assert _evidence_supported("会议前不要安排闲聊，切记切记", CLEANED) is True


def test_evidence_supported_short_quote_exact() -> None:
    """<10 字 quote 需精确出现。"""
    assert _evidence_supported("灯塔计划", CLEANED) is True
    assert _evidence_supported("灯塔项目", CLEANED) is False


def test_evidence_supported_no_match() -> None:
    assert _evidence_supported("用户喜欢喝全糖奶茶加珍珠", CLEANED) is False


# === _commit_item_result gate ===

def test_supported_unit_committed(tmp_path: Path) -> None:
    """quote 命中原文的 unit 正常入库。"""
    con, row_id = _setup_db(tmp_path / "t.sqlite")
    stats = _commit(con, row_id, [_unit("只喝无糖可乐")])

    assert stats["succeeded"] == 1
    assert stats["units"] == 1
    assert stats["units_dropped_no_evidence"] == 0
    n = con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
    assert n == 1
    status, unit_count = con.execute(
        "SELECT status, unit_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert (status, unit_count) == ("succeeded", 1)
    con.close()


def test_unsupported_unit_dropped_others_kept(tmp_path: Path) -> None:
    """对不上的 unit 丢弃并计数，同 item 其余 unit 正常写入。"""
    con, row_id = _setup_db(tmp_path / "t.sqlite")
    stats = _commit(con, row_id, [
        _unit("只喝无糖可乐"),
        _unit("完全编造的引文根本不在原文里"),
    ])

    assert stats["succeeded"] == 1
    assert stats["units"] == 1
    assert stats["units_dropped_no_evidence"] == 1
    n = con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
    assert n == 1
    unit_count = con.execute(
        "SELECT unit_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()[0]
    assert unit_count == 1
    con.close()


def test_all_dropped_item_still_succeeded(tmp_path: Path) -> None:
    """全部 unit 被丢弃时，item 仍记 succeeded（unit_count=0）。"""
    con, row_id = _setup_db(tmp_path / "t.sqlite")
    stats = _commit(con, row_id, [_unit("完全编造的引文根本不在原文里")])

    assert stats["succeeded"] == 1
    assert stats["units"] == 0
    assert stats["units_dropped_no_evidence"] == 1
    n = con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
    assert n == 0
    status, unit_count = con.execute(
        "SELECT status, unit_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert (status, unit_count) == ("succeeded", 0)
    con.close()
