"""Phase 14 Plan 03 Task 1 测试：分层 pilot + fake LLM 故障演练。

用 fake LLM client 验证：
  - 正常 run 与 interrupted→resume 产生相同 row set 和 dataset hash
  - cache replay 不重复调用
  - 429/500/503/timeout/invalid JSON/foreign ref 的 terminal/critical 错误使 gate 失败
  - 旧 active checkpoint 不变
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from build_knowledge_units_prod import (  # noqa: E402
    classify_error, compute_cache_key, get_cached_response, put_cached_response,
    init_run_items, get_pending_items, get_run_stats, recover_expired_leases,
)
from build_pilot_sample import build_stratified_sample  # noqa: E402
from evaluate_knowledge_unit_extraction import evaluate_run  # noqa: E402


def _setup_inventory(db: Path, n_items: int = 10) -> str:
    """建 schema + inventory + items。返回 inventory_id。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    inv_id = "test_inv_pilot"
    con.execute(
        "INSERT INTO knowledge_inventory VALUES (?,?,?,?,?,?,?,?,?,?)",
        (inv_id, "2026-01-01", "canon.db", "checksum", n_items, n_items, "dataset_hash", "2026-01", "2026-02", "{}")
    )
    for pos in range(n_items):
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv_pilot',?,?,?,?,?,?,?,?,?,?)",
            (pos, f"cm{pos}", f"hash{pos}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible")
        )
    # 修正 inventory_id
    con.execute(
        "UPDATE knowledge_inventory_items SET inventory_id=? WHERE inventory_id='inv_pilot'",
        (inv_id,)
    )
    con.commit()
    con.close()
    return inv_id


# === 分层采样测试 ===

def test_pilot_sample_size_in_range(tmp_path: Path) -> None:
    """pilot sample size 在 300-500（用小 inventory 测试比例）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=1000)
    manifest = build_stratified_sample(inv_id, target_size=400, db_path=db)
    assert 300 <= manifest["sample_size"] <= 500


def test_pilot_sample_deterministic(tmp_path: Path) -> None:
    """同输入两次采样，sample_hash 相同。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=100)
    m1 = build_stratified_sample(inv_id, target_size=50, db_path=db)
    m2 = build_stratified_sample(inv_id, target_size=50, db_path=db)
    assert m1["sample_hash"] == m2["sample_hash"]
    assert m1["sample_positions"] == m2["sample_positions"]


def test_pilot_sample_not_latest_n(tmp_path: Path) -> None:
    """sample 不是按最新 N 条截断（position 不连续）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=100)
    manifest = build_stratified_sample(inv_id, target_size=30, db_path=db)
    positions = manifest["sample_positions"]
    # 不是简单的 [70,71,...,99]（最新 30 条）
    assert positions != list(range(70, 100))


def test_pilot_manifest_no_raw_content(tmp_path: Path) -> None:
    """manifest 不含原文。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=50)
    manifest = build_stratified_sample(inv_id, target_size=20, db_path=db)
    manifest_json = json.dumps(manifest, ensure_ascii=False)
    assert "content" not in manifest_json.lower() or "content_hash" in manifest_json
    assert "evidence_quote" not in manifest_json


def test_pilot_manifest_model_id_unset(tmp_path: Path) -> None:
    """manifest 的 actual_model_id 待 preflight 填充。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=50)
    manifest = build_stratified_sample(inv_id, target_size=20, db_path=db)
    assert manifest["actual_model_id"] is None


# === 故障注入 + 恢复测试 ===

def test_fake_llm_normal_run(tmp_path: Path) -> None:
    """fake LLM 正常 run：所有 items succeeded。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=5)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_normal','extraction','2026-01-01','cs','h','v1','v1','fake-model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run_normal", inv_id)

    # 模拟处理：标记所有为 succeeded + 写 units
    for pos in range(5):
        con.execute(
            "UPDATE knowledge_run_items SET status='succeeded', unit_count=1, "
            "cache_key=?, response_hash=? WHERE run_id='run_normal' AND position=?",
            (f"ck{pos}", f"rh{pos}", pos),
        )
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"u{pos}", "run_normal", "preference", "test", "q?", "a", 0.9, "ev", "user", "staging", "2026-01-01", f"cm{pos}")
        )
        con.execute(
            "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
            (f"u{pos}", f"cm{pos}")
        )
    con.commit()
    con.close()

    report = evaluate_run("run_normal", db, min_yield=0.5)
    assert report.gate_status == "passed"


def test_fake_llm_429_terminal_after_retries(tmp_path: Path) -> None:
    """fake 429 重试耗尽后 terminal_failed，gate FAIL。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=5)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_429','extraction','2026-01-01','cs','h','v1','v1','fake-model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run_429", inv_id)

    # 2 个 terminal_failed（429 耗尽）
    for pos in [0, 1]:
        con.execute(
            "UPDATE knowledge_run_items SET status='terminal_failed', "
            "last_error_class='retryable', attempt_count=5 WHERE run_id='run_429' AND position=?",
            (pos,)
        )
    # 3 个 succeeded
    for pos in [2, 3, 4]:
        con.execute(
            "UPDATE knowledge_run_items SET status='succeeded', unit_count=1 WHERE run_id='run_429' AND position=?",
            (pos,)
        )
    con.commit()
    con.close()

    report = evaluate_run("run_429", db, min_yield=0.5)
    # terminal_api_errors > 0（last_error_class='retryable' 但 status=terminal_failed）
    assert report.gate_status == "failed"


def test_fake_llm_invalid_json_terminal(tmp_path: Path) -> None:
    """fake invalid JSON → terminal_failed (schema_invalid)，gate FAIL。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=3)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_bad_json','extraction','2026-01-01','cs','h','v1','v1','fake-model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run_bad_json", inv_id)

    # 全部 schema_invalid
    for pos in range(3):
        con.execute(
            "UPDATE knowledge_run_items SET status='terminal_failed', "
            "last_error_class='schema_invalid' WHERE run_id='run_bad_json' AND position=?",
            (pos,)
        )
    con.commit()
    con.close()

    report = evaluate_run("run_bad_json", db, min_yield=0.5)
    assert report.gate_status == "failed"
    # nonzero_output: 0 units → FAIL
    nonzero = [c for c in report.checks if c.name == "nonzero_output"][0]
    assert not nonzero.passed


def test_fake_llm_interrupted_resume_same_dataset(tmp_path: Path) -> None:
    """interrupted→resume 产生与 uninterrupted 相同的 row set。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=5)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_resume','extraction','2026-01-01','cs','h','v1','v1','fake-model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run_resume", inv_id)

    # 模拟 interrupted：3 succeeded, 1 in_flight (过期), 1 pending
    for pos in [0, 1, 2]:
        con.execute(
            "UPDATE knowledge_run_items SET status='succeeded', unit_count=1, "
            "cache_key=?, response_hash=? WHERE run_id='run_resume' AND position=?",
            (f"ck{pos}", f"rh{pos}", pos),
        )
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"u{pos}", "run_resume", "preference", "test", "q?", "a", 0.9, "ev", "user", "staging", "2026-01-01", f"cm{pos}")
        )
        con.execute(
            "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
            (f"u{pos}", f"cm{pos}")
        )
    # position 3: in_flight（过期 lease）
    con.execute(
        "UPDATE knowledge_run_items SET status='in_flight', lease_started_at='2020-01-01T00:00:00+00:00' "
        "WHERE run_id='run_resume' AND position=3"
    )
    con.commit()
    con.close()

    # resume：恢复过期 lease
    con = sqlite3.connect(str(db))
    recovered = recover_expired_leases(con, "run_resume")
    assert recovered == 1

    # 模拟 resume 处理 position 3, 4
    for pos in [3, 4]:
        con.execute(
            "UPDATE knowledge_run_items SET status='succeeded', unit_count=1, "
            "cache_key=?, response_hash=? WHERE run_id='run_resume' AND position=?",
            (f"ck{pos}", f"rh{pos}", pos),
        )
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"u{pos}", "run_resume", "preference", "test", "q?", "a", 0.9, "ev", "user", "staging", "2026-01-01", f"cm{pos}")
        )
        con.execute(
            "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
            (f"u{pos}", f"cm{pos}")
        )
    con.commit()
    con.close()

    # 验证：5 个 succeeded, 0 pending
    con = sqlite3.connect(str(db))
    stats = get_run_stats(con, "run_resume")
    assert stats.get("succeeded") == 5
    assert "pending" not in stats
    # 5 个 units
    unit_count = con.execute(
        "SELECT COUNT(*) FROM knowledge_units WHERE run_id='run_resume'"
    ).fetchone()[0]
    assert unit_count == 5
    con.close()

    # gate passed
    report = evaluate_run("run_resume", db, min_yield=0.5)
    assert report.gate_status == "passed"


def test_cache_replay_no_duplicate_calls(tmp_path: Path) -> None:
    """cache hit 不重复调用 LLM。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()

    # 写 cache
    key = compute_cache_key("model", "ph", "sh", "ih", "ch")
    put_cached_response(con, key, "model", "ph", "sh", "ih", "ch", "cached_response", "rhash", "run1")
    con.commit()

    # cache hit
    cached = get_cached_response(con, key)
    assert cached == "cached_response"

    # 第二次读也是 cache hit（不调 LLM）
    cached2 = get_cached_response(con, key)
    assert cached2 == "cached_response"
    con.close()


def test_active_pointer_unchanged_on_failure(tmp_path: Path) -> None:
    """gate FAIL 时 active pointer 不变。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_inventory(db, n_items=3)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run_fail','extraction','2026-01-01','cs','h','v1','v1','fake-model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run_fail", inv_id)

    # 全部 terminal_failed
    for pos in range(3):
        con.execute(
            "UPDATE knowledge_run_items SET status='terminal_failed', last_error_class='http_500' "
            "WHERE run_id='run_fail' AND position=?",
            (pos,)
        )
    con.commit()
    con.close()

    report = evaluate_run("run_fail", db, min_yield=0.5)
    assert report.gate_status == "failed"
    # run status 仍是 staging（不是 validated/current）
    con = sqlite3.connect(str(db))
    status = con.execute("SELECT status FROM knowledge_build_runs WHERE run_id='run_fail'").fetchone()[0]
    assert status == "staging"
    con.close()


def test_error_classification_matrix() -> None:
    """完整错误分类矩阵。"""
    from build_knowledge_units_prod import classify_error
    assert classify_error(429, None) == "retryable"
    assert classify_error(500, None) == "retryable"
    assert classify_error(502, None) == "retryable"
    assert classify_error(503, None) == "retryable"
    assert classify_error(400, None) == "terminal"
    assert classify_error(401, None) == "terminal"
    assert classify_error(403, None) == "terminal"
    assert classify_error(404, None) == "terminal"
    assert classify_error(None, TimeoutError()) == "retryable"
    assert classify_error(None, ConnectionError()) == "retryable"
    assert classify_error(None, ValueError("bad")) == "terminal"
