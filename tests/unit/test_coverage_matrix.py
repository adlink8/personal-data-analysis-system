"""Phase 41 Plan 03：覆盖矩阵（Nyquist 用例 7 + 快照分级）。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.application.knowledge.coverage_matrix import (
    compute_coverage_matrix,
)


def _make_canonical_db(path: Path, messages: list[tuple[str, str, str]]) -> Path:
    """messages: (ref, source, role)。content 自动造为 >30 字去重文本。"""
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE canonical_sessions("
        "canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER,"
        " agent TEXT, started_at TEXT)"
    )
    con.execute(
        "CREATE TABLE canonical_messages("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT,"
        " content TEXT, source TEXT, role TEXT)"
    )
    con.execute(
        "INSERT INTO canonical_sessions VALUES ('s1', 1, 'gemini', '2026-07-01T00:00:00Z')"
    )
    for i, (ref, source, role) in enumerate(messages):
        content = f"eligible message number {i} with enough content to pass the length gate"
        con.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?)",
            (ref, "s1", content, source, role),
        )
    con.commit()
    con.close()
    return path


def _make_unified_db(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE knowledge_build_runs(
            run_id TEXT PRIMARY KEY, run_type TEXT, generated_at TEXT,
            input_hash TEXT, status TEXT);
        CREATE TABLE knowledge_inventory_registry(
            inventory_id TEXT PRIMARY KEY, inventory_kind TEXT, created_at TEXT);
        CREATE TABLE knowledge_run_items(
            id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, inventory_id TEXT,
            position INTEGER, evidence_ref TEXT, status TEXT);
        CREATE TABLE knowledge_units(
            unit_id TEXT PRIMARY KEY, run_id TEXT, unit_type TEXT, subject TEXT,
            question TEXT, answer TEXT, confidence REAL, evidence_quote TEXT,
            source_message_ref TEXT, created_at TEXT);
        CREATE TABLE knowledge_unit_evidence(
            id INTEGER PRIMARY KEY AUTOINCREMENT, unit_id TEXT, evidence_ref TEXT);
        CREATE TABLE knowledge_dead_refs(
            evidence_ref TEXT, run_id TEXT, error_class TEXT, acknowledged_at TEXT,
            PRIMARY KEY (evidence_ref, run_id));
        """
    )
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES ('r1','extraction','2026-07-01','h','succeeded')"
    )
    con.execute(
        "INSERT INTO knowledge_inventory_registry VALUES ('inv1','full','2026-07-01')"
    )
    return con


def _insert_unit(con: sqlite3.Connection, unit_id: str, ref: str | None) -> None:
    con.execute(
        "INSERT INTO knowledge_units VALUES (?,?,?,?,?,?,?,?,?,?)",
        (unit_id, "r1", "preference", "s", "q", "a", 0.9, "quote", ref, "2026-07-01"),
    )


def test_matrix_three_uncovered_classes_and_grandfathered(tmp_path: Path):
    conv = _make_canonical_db(
        tmp_path / "canonical.sqlite",
        [(f"cm|m{i}", "zcode", "user") for i in range(1, 7)],
    )
    db_path = tmp_path / "unified.sqlite"
    con = _make_unified_db(db_path)
    _insert_unit(con, "v1|u1", "cm|m1")  # covered via source_message_ref
    _insert_unit(con, "as|u2", None)  # covered via evidence 并集
    con.execute("INSERT INTO knowledge_unit_evidence VALUES (NULL,'as|u2','cm|m2')")
    _insert_unit(con, "ku_u3", "cm|m3")  # ku 世代（实测前缀 ku_）→ grandfathered
    # m4: 先 retryable 后 abstained —— 取最新 status
    con.execute(
        "INSERT INTO knowledge_run_items VALUES (NULL,'r1','inv1',1,'cm|m4','retryable')"
    )
    con.execute(
        "INSERT INTO knowledge_run_items VALUES (NULL,'r1','inv1',2,'cm|m4','abstained')"
    )
    # m5: terminal_failed 且未入 knowledge_dead_refs → dead_ref_missing
    con.execute(
        "INSERT INTO knowledge_run_items VALUES (NULL,'r1','inv1',3,'cm|m5','terminal_failed')"
    )
    # m6: 从未入队 → not_queued
    con.commit()
    con.close()

    matrix = compute_coverage_matrix(db_path, conv)
    assert matrix["source_checksum"]
    assert len(matrix["rows"]) == 1
    row = matrix["rows"][0]
    assert (row["source"], row["role"]) == ("zcode", "user")
    assert row["eligible_count"] == 6
    assert row["covered_count"] == 2
    assert row["grandfathered_count"] == 1
    assert row["abstained_count"] == 1
    assert row["terminal_failed_count"] == 1
    assert row["not_queued_count"] == 1
    assert row["dead_ref_missing_count"] == 1
    assert row["by_pass"] == {"v1|": 1, "as|": 1, "ku_": 1}
    # 守恒：covered + grandfathered + 三分类 == eligible_count
    assert (
        row["covered_count"]
        + row["grandfathered_count"]
        + row["abstained_count"]
        + row["terminal_failed_count"]
        + row["not_queued_count"]
        == row["eligible_count"]
    )
    # ku| 命中不计 not_queued（上面 not_queued 只有 m6 一条）且行级守恒成立


def test_matrix_levels_first_seen_info_then_warn(tmp_path: Path):
    conv = _make_canonical_db(
        tmp_path / "canonical.sqlite",
        [("cm|a1", "newsrc", "user"), ("cm|b1", "oldsrc", "assistant")],
    )
    db_path = tmp_path / "unified.sqlite"
    con = _make_unified_db(db_path)
    _insert_unit(con, "v1|u1", "cm|b1")  # oldsrc 有覆盖
    con.commit()
    con.close()

    # 无历史：所有新 source 行 level='info'
    first = compute_coverage_matrix(db_path, conv, previous_snapshot=None)
    by_key = {(r["source"], r["role"]): r for r in first["rows"]}
    assert by_key[("newsrc", "user")]["level"] == "info"
    assert by_key[("oldsrc", "assistant")]["level"] == "info"

    # 传入上次零覆盖快照：newsrc 仍零覆盖 → warn；oldsrc 有覆盖 → ok
    second = compute_coverage_matrix(db_path, conv, previous_snapshot=first)
    by_key2 = {(r["source"], r["role"]): r for r in second["rows"]}
    assert by_key2[("newsrc", "user")]["level"] == "warn"
    assert by_key2[("oldsrc", "assistant")]["level"] == "ok"
    assert second["totals"]["warn_rows"] == 1


def test_matrix_zero_coverage_row_stays_ok_when_previous_covered(tmp_path: Path):
    conv = _make_canonical_db(
        tmp_path / "canonical.sqlite", [("cm|a1", "zcode", "user")]
    )
    db_path = tmp_path / "unified.sqlite"
    con = _make_unified_db(db_path)
    con.commit()
    con.close()
    # 上次有覆盖、本次零覆盖：非"连续零覆盖"，不 WARN
    previous = {
        "rows": [
            {
                "source": "zcode",
                "role": "user",
                "eligible_count": 1,
                "covered_count": 1,
                "grandfathered_count": 0,
            }
        ]
    }
    matrix = compute_coverage_matrix(db_path, conv, previous_snapshot=previous)
    assert matrix["rows"][0]["level"] == "ok"


def test_matrix_missing_unified_db_all_not_queued(tmp_path: Path):
    conv = _make_canonical_db(
        tmp_path / "canonical.sqlite", [("cm|a1", "zcode", "user")]
    )
    matrix = compute_coverage_matrix(tmp_path / "missing.sqlite", conv)
    row = matrix["rows"][0]
    assert row["eligible_count"] == 1
    assert row["not_queued_count"] == 1
    assert row["covered_count"] == 0
