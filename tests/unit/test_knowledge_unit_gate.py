"""Phase 14 Plan 02 Task 3 测试：严格 extraction gate + active 隔离。"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.domains.knowledge.evaluate_knowledge_unit_extraction import evaluate_run, write_gate_to_db  # noqa: E402


def _setup_full_db(db: Path) -> str:
    """建 schema + inventory + run + items，返回 run_id。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    # inventory
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',3,3,'dh','2026-01','2026-02','{}')"
    )
    for pos in range(3):
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?,?)",
            (pos, f"cm{pos}", f"hash{pos}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user")
        )
    # run
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    # items all succeeded
    for pos in range(3):
        con.execute(
            "INSERT INTO knowledge_run_items "
            "(run_id, inventory_id, position, evidence_ref, status, attempt_count, updated_at, unit_count) "
            "VALUES ('run1','inv1',?,?,?,1,'2026-01-01',1)",
            (pos, f"cm{pos}", "succeeded"),
        )
    # units
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
        "VALUES ('u1','run1','preference','shell','q','a',0.9,'ev','user','staging','2026-01-01','cm0')"
    )
    con.execute(
        "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u1','cm0')"
    )
    con.commit()
    con.close()
    return "run1"


def test_gate_passes_on_complete_run(tmp_path: Path) -> None:
    """完整 run（all succeeded, units>0, no violations）gate passed（需 min_yield）。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "passed"
    assert all(c.passed for c in report.checks if c.name != "minimum_yield")


def test_gate_awaiting_pilot_threshold_without_min_yield(tmp_path: Path) -> None:
    """无 min_yield 时 gate = awaiting_pilot_threshold（不是 PASS）。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    report = evaluate_run(run_id, db, min_yield=None)
    assert report.gate_status == "awaiting_pilot_threshold"


def test_gate_fails_on_incomplete_items(tmp_path: Path) -> None:
    """有 pending items 时 gate FAIL。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "UPDATE knowledge_run_items SET status='pending' WHERE run_id='run1' AND position=0"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "failed"
    completeness = [c for c in report.checks if c.name == "snapshot_completeness"][0]
    assert not completeness.passed


def test_gate_fails_on_terminal_api_errors(tmp_path: Path) -> None:
    """terminal API errors 时 gate FAIL。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "UPDATE knowledge_run_items SET status='terminal_failed', last_error_class='http_500' "
        "WHERE run_id='run1' AND position=0"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "failed"
    api_check = [c for c in report.checks if c.name == "api_completion"][0]
    assert not api_check.passed


def test_gate_fails_on_zero_units(tmp_path: Path) -> None:
    """零 units 时 gate FAIL（防空 run 发布）。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute("DELETE FROM knowledge_units WHERE run_id='run1'")
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "failed"
    nonzero = [c for c in report.checks if c.name == "nonzero_output"][0]
    assert not nonzero.passed


def test_gate_fails_on_speaker_misattribution(tmp_path: Path) -> None:
    """personal_fact 有非 user evidence_scope 时 gate FAIL。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, evidence_scope, status, created_at) "
        "VALUES ('u2','run1','personal_fact','x','q','a',0.9,'ev','assistant','staging','2026-01-01')"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    speaker = [c for c in report.checks if c.name == "speaker_attribution"][0]
    assert not speaker.passed


def test_gate_fails_on_low_yield(tmp_path: Path) -> None:
    """yield 低于阈值时 gate FAIL。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    # 把 2 个 succeeded 改成 abstained，降低 yield
    con = sqlite3.connect(str(db))
    con.execute(
        "UPDATE knowledge_run_items SET status='abstained' WHERE run_id='run1' AND position IN (1,2)"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.9)  # 要求 90%，实际 33%
    yield_check = [c for c in report.checks if c.name == "minimum_yield"][0]
    assert not yield_check.passed
    assert report.gate_status == "failed"


def test_gate_writes_validated_not_current(tmp_path: Path) -> None:
    """gate passed 写 validated，不写 current（active 隔离）。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "passed"
    write_gate_to_db(report, db)

    con = sqlite3.connect(str(db))
    status = con.execute(
        "SELECT status FROM knowledge_build_runs WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert status == "validated"  # 不是 current
    con.close()


def test_gate_failed_does_not_change_status(tmp_path: Path) -> None:
    """gate failed 不改变 run status。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    # 制造 failure
    con = sqlite3.connect(str(db))
    con.execute(
        "UPDATE knowledge_run_items SET status='pending' WHERE run_id='run1' AND position=0"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    assert report.gate_status == "failed"
    write_gate_to_db(report, db)

    con = sqlite3.connect(str(db))
    status = con.execute(
        "SELECT status FROM knowledge_build_runs WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    assert status == "staging"  # 未变
    con.close()


def test_all_api_failure_does_not_pass(tmp_path: Path) -> None:
    """全部 API 失败时 gate 不能 PASS（关键安全测试）。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',2,2,'dh','2026-01','2026-02','{}')"
    )
    for pos in range(2):
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?,?)",
            (pos, f"cm{pos}", f"hash{pos}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user")
        )
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_all_fail','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    # 全部 terminal_failed（API 错误）
    for pos in range(2):
        con.execute(
            "INSERT INTO knowledge_run_items (run_id, inventory_id, position, evidence_ref, status, last_error_class) "
            "VALUES ('run_all_fail','inv1',?,?,?,?)",
            (pos, f"cm{pos}", "terminal_failed", "http_500"),
        )
    con.commit()
    con.close()

    report = evaluate_run("run_all_fail", db, min_yield=0.5)
    assert report.gate_status == "failed"
    # 多个 gate 应该 FAIL
    api_check = [c for c in report.checks if c.name == "api_completion"][0]
    nonzero = [c for c in report.checks if c.name == "nonzero_output"][0]
    assert not api_check.passed  # terminal_api_errors > 0
    assert not nonzero.passed  # units_total = 0


# --- Phase 41-04：Gate 8 双向对称（assistant 3 类型必须 scope='assistant'） ---


def test_gate_fails_on_assistant_track_misattribution(tmp_path: Path) -> None:
    """unit_type='solution' 但 evidence_scope='user' → speaker_attribution_assistant FAIL。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, evidence_scope, status, created_at) "
        "VALUES ('u2','run1','solution','x','q','a',0.9,'ev','user','staging','2026-01-01')"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    check = [c for c in report.checks if c.name == "speaker_attribution_assistant"][0]
    assert not check.passed
    assert check.value == 1


def test_gate_passes_on_assistant_track_correct_scope(tmp_path: Path) -> None:
    """unit_type='solution' 且 evidence_scope='assistant' → 对称检查通过，整体 gate 不回归。"""
    db = tmp_path / "test.sqlite"
    run_id = _setup_full_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, evidence_scope, status, created_at) "
        "VALUES ('u2','run1','decision_rationale','x','q','a',0.9,'ev','assistant','staging','2026-01-01')"
    )
    con.commit()
    con.close()

    report = evaluate_run(run_id, db, min_yield=0.5)
    check = [c for c in report.checks if c.name == "speaker_attribution_assistant"][0]
    assert check.passed
    assert check.value == 0
    # 回归：assistant 类型不被原 Gate 8（user 方向）误拦，整体仍 passed
    speaker_user = [c for c in report.checks if c.name == "speaker_attribution"][0]
    assert speaker_user.passed
    assert report.gate_status == "passed"
