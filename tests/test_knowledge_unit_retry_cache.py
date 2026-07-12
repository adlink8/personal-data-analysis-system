"""Phase 14 Plan 02 Task 2 测试：retry cache + item ledger 恢复。"""

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
    classify_error,
    compute_cache_key,
    get_cached_response,
    put_cached_response,
    init_run_items,
    recover_expired_leases,
    get_pending_items,
    get_run_stats,
    start_run,
    resume_run,
)


def _setup_db(db: Path) -> str:
    """建 schema + inventory，返回 inventory_id。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    # inventory
    inv_id = "test_inv_001"
    con.execute(
        "INSERT INTO knowledge_inventory VALUES (?,?,?,?,?,?,?,?,?,?)",
        (inv_id, "2026-01-01", "canon.db", "checksum", 3, 3, "dataset_hash", "2026-01", "2026-02", "{}")
    )
    for pos in range(3):
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (None, inv_id, pos, f"cm{pos}", f"hash{pos}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible")
        )
    con.commit()
    con.close()
    return inv_id


# === 错误分类测试 ===

def test_classify_retryable_429() -> None:
    assert classify_error(429, None) == "retryable"

def test_classify_retryable_500() -> None:
    assert classify_error(500, None) == "retryable"

def test_classify_retryable_503() -> None:
    assert classify_error(503, None) == "retryable"

def test_classify_terminal_400() -> None:
    assert classify_error(400, None) == "terminal"

def test_classify_terminal_401() -> None:
    assert classify_error(401, None) == "terminal"

def test_classify_timeout_retryable() -> None:
    assert classify_error(None, TimeoutError()) == "retryable"


# === Cache 测试 ===

def test_cache_key_deterministic() -> None:
    """相同输入产生相同 cache key。"""
    k1 = compute_cache_key("gemini", "ph", "sh", "ih", "ch")
    k2 = compute_cache_key("gemini", "ph", "sh", "ih", "ch")
    assert k1 == k2


def test_cache_key_changes_on_model() -> None:
    """model 变化 → cache miss。"""
    k1 = compute_cache_key("gemini", "ph", "sh", "ih", "ch")
    k2 = compute_cache_key("gpt-5.6-luna", "ph", "sh", "ih", "ch")
    assert k1 != k2


def test_cache_key_changes_on_input() -> None:
    """input 变化 → cache miss。"""
    k1 = compute_cache_key("m", "ph", "sh", "ih1", "ch")
    k2 = compute_cache_key("m", "ph", "sh", "ih2", "ch")
    assert k1 != k2


def test_cache_put_and_get(tmp_path: Path) -> None:
    """cache 写入后可读。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()

    key = compute_cache_key("m", "ph", "sh", "ih", "ch")
    put_cached_response(con, key, "m", "ph", "sh", "ih", "ch", "response", "rhash", "run1")
    con.commit()

    cached = get_cached_response(con, key)
    assert cached == "response"
    con.close()


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    """cache miss 返回 None。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()

    assert get_cached_response(con, "nonexistent") is None
    con.close()


# === Item ledger 测试 ===

def test_init_run_items_creates_pending(tmp_path: Path) -> None:
    """init_run_items 为每个 inventory item 创建 pending work-item。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)

    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()

    count = init_run_items(con, "run1", inv_id)
    assert count == 3

    items = get_pending_items(con, "run1")
    assert len(items) == 3
    assert all(item["status"] == "pending" for item in items)
    con.close()


def test_init_run_items_idempotent(tmp_path: Path) -> None:
    """init_run_items 幂等（重复调用不创建重复）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()

    init_run_items(con, "run1", inv_id)
    init_run_items(con, "run1", inv_id)  # 重复

    items = get_pending_items(con, "run1")
    assert len(items) == 3  # 不重复
    con.close()


def test_resume_does_not_delete_succeeded(tmp_path: Path) -> None:
    """resume 不删除已 succeeded 的 items。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)

    # 标记 cm0 为 succeeded
    con.execute(
        "UPDATE knowledge_run_items SET status='succeeded', unit_count=2 "
        "WHERE run_id='run1' AND position=0"
    )
    con.commit()

    # resume：恢复过期 lease
    recovered = recover_expired_leases(con, "run1")
    # 没有 in_flight，不恢复
    assert recovered == 0

    # succeeded 仍在
    stats = get_run_stats(con, "run1")
    assert stats.get("succeeded") == 1
    assert stats.get("pending") == 2
    con.close()


def test_expired_lease_recovered(tmp_path: Path) -> None:
    """过期 in_flight lease 恢复为 retryable。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)

    # 标记 cm0 为 in_flight，lease 时间为 1 小时前（已过期）
    old_time = "2020-01-01T00:00:00+00:00"
    con.execute(
        "UPDATE knowledge_run_items SET status='in_flight', lease_started_at=? "
        "WHERE run_id='run1' AND position=0",
        (old_time,),
    )
    con.commit()

    recovered = recover_expired_leases(con, "run1", lease_timeout=60)
    assert recovered == 1

    stats = get_run_stats(con, "run1")
    assert stats.get("retryable") == 1
    assert "in_flight" not in stats or stats.get("in_flight") == 0
    con.close()


def test_get_run_stats_all_statuses(tmp_path: Path) -> None:
    """get_run_stats 返回所有状态的计数。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)

    con.execute("UPDATE knowledge_run_items SET status='succeeded' WHERE run_id='run1' AND position=0")
    con.execute("UPDATE knowledge_run_items SET status='abstained' WHERE run_id='run1' AND position=1")
    con.execute("UPDATE knowledge_run_items SET status='terminal_failed' WHERE run_id='run1' AND position=2")
    con.commit()

    stats = get_run_stats(con, "run1")
    assert stats == {"succeeded": 1, "abstained": 1, "terminal_failed": 1}
    con.close()


def test_start_run_creates_manifest_and_items(tmp_path: Path) -> None:
    """start_run 创建 manifest 和 item ledger。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)

    run_id = start_run("gemini-3.5-flash", inv_id, db_path=db, limit=2)
    assert run_id

    con = sqlite3.connect(str(db))
    # manifest 存在
    run = con.execute("SELECT status FROM knowledge_build_runs WHERE run_id=?", (run_id,)).fetchone()
    assert run[0] == "staging"

    # items 创建
    stats = get_run_stats(con, run_id)
    # limit=2：前 2 个 pending，第 3 个 abstained
    assert stats.get("pending", 0) + stats.get("abstained", 0) == 3
    con.close()


def test_resume_run_recovers_and_reports(tmp_path: Path) -> None:
    """resume_run 恢复 lease 并报告状态。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    run_id = start_run("gemini-3.5-flash", inv_id, db_path=db)

    con = sqlite3.connect(str(db))
    # 标记一个 in_flight 过期
    con.execute(
        "UPDATE knowledge_run_items SET status='in_flight', lease_started_at='2020-01-01T00:00:00+00:00' "
        "WHERE run_id=? AND position=0",
        (run_id,),
    )
    con.commit()
    con.close()

    info = resume_run(run_id, "gemini-3.5-flash", db_path=db)
    assert info["recovered_leases"] == 1
    assert info["stats"].get("retryable") == 1
