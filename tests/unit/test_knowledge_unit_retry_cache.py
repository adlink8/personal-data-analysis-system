"""Phase 14 Plan 02 Task 2 测试：retry cache + item ledger 恢复。"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.application.knowledge.build_knowledge_units_prod import (  # noqa: E402
    classify_error,
    call_llm_with_retry,
    compute_cache_key,
    get_cached_response,
    put_cached_response,
    init_run_items,
    recover_expired_leases,
    get_pending_items,
    get_run_stats,
    start_run,
    resume_run,
    _claim_item,
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
            "INSERT INTO knowledge_inventory_items VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (None, inv_id, pos, f"cm{pos}", f"hash{pos}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user")
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

def test_classify_retryable_401() -> None:
    """401 归 retryable（token 过期，call_llm_with_retry 刷新后重试）。"""
    assert classify_error(401, None) == "retryable"

def test_classify_timeout_retryable() -> None:
    assert classify_error(None, TimeoutError()) == "retryable"


# === 401 token refresh 重试 ===

class _FakeTokenProvider:
    """记录 refresh 次数的假 provider。"""

    def __init__(self) -> None:
        self.refresh_count = 0

    def get(self) -> str:
        return "fake-token"

    def refresh(self) -> str:
        self.refresh_count += 1
        return "fake-token"


def _http_error(code: int) -> urllib.error.HTTPError:
    from email.message import Message
    return urllib.error.HTTPError(
        "http://x", code, "err", hdrs=Message(), fp=io.BytesIO(b"")
    )


def _ok_response() -> io.BytesIO:
    body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "ok text"}]}}],
        "usageMetadata": {},
    }).encode()
    return io.BytesIO(body)


def test_401_refreshes_token_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """401 → token_provider.refresh() 被调用，刷新后重试成功。"""
    calls = {"n": 0}

    def fake_urlopen(req: object, timeout: int = 0) -> io.BytesIO:
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(401)
        return _ok_response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    provider = _FakeTokenProvider()
    result = call_llm_with_retry(
        "sys", "content", "model", provider,
        max_retries=2, base_backoff=0.0,
    )
    assert provider.refresh_count == 1
    assert result.get("text") == "ok text"


def test_401_bounded_retries_no_infinite_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    """连续 401 超过 max_retries 后返回 error，刷新/重试均有界，不死循环。"""
    calls = {"n": 0}

    def fake_urlopen(req: object, timeout: int = 0) -> io.BytesIO:
        calls["n"] += 1
        raise _http_error(401)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(time, "sleep", lambda s: None)

    provider = _FakeTokenProvider()
    result = call_llm_with_retry(
        "sys", "content", "model", provider,
        max_retries=2, base_backoff=0.0,
    )
    assert "error" in result
    assert calls["n"] == 3  # max_retries + 1 次尝试，有界
    assert provider.refresh_count == 2  # 每次重试前刷新一次，有界
    assert result["attempts"] == 3


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


# === Finding F-10：claim test-and-set（并发不重复认领）===

def test_claim_pending_item_succeeds(tmp_path: Path) -> None:
    """pending item 可正常 claim：置 in_flight 且 attempt_count+1。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)
    row_id = con.execute(
        "SELECT id FROM knowledge_run_items WHERE run_id='run1' AND position=0"
    ).fetchone()[0]

    assert _claim_item(con, row_id, "2026-01-02T00:00:00Z") is True
    status, attempts = con.execute(
        "SELECT status, attempt_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert (status, attempts) == ("in_flight", 1)
    con.close()


def test_claim_skips_item_already_in_flight(tmp_path: Path) -> None:
    """已被并发进程 claim 的 in_flight item 不会被重复 claim（F-10）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)
    row_id = con.execute(
        "SELECT id FROM knowledge_run_items WHERE run_id='run1' AND position=0"
    ).fetchone()[0]
    # 模拟另一个进程已 claim
    con.execute(
        "UPDATE knowledge_run_items SET status='in_flight', attempt_count=1 WHERE id=?",
        (row_id,),
    )
    con.commit()

    assert _claim_item(con, row_id, "2026-01-02T00:00:00Z") is False
    status, attempts = con.execute(
        "SELECT status, attempt_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert status == "in_flight"  # 不被改写
    assert attempts == 1  # 不双重递增
    con.close()


def test_claim_skips_succeeded_item(tmp_path: Path) -> None:
    """succeeded item 不会被重复 claim（F-10）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)
    row_id = con.execute(
        "SELECT id FROM knowledge_run_items WHERE run_id='run1' AND position=0"
    ).fetchone()[0]
    con.execute(
        "UPDATE knowledge_run_items SET status='succeeded', attempt_count=1 WHERE id=?",
        (row_id,),
    )
    con.commit()

    assert _claim_item(con, row_id, "2026-01-02T00:00:00Z") is False
    status, attempts = con.execute(
        "SELECT status, attempt_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert (status, attempts) == ("succeeded", 1)
    con.close()


def test_claim_retryable_item_succeeds(tmp_path: Path) -> None:
    """retryable item 仍可被 claim（重试路径不回归）。"""
    db = tmp_path / "test.sqlite"
    inv_id = _setup_db(db)
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()
    init_run_items(con, "run1", inv_id)
    row_id = con.execute(
        "SELECT id FROM knowledge_run_items WHERE run_id='run1' AND position=0"
    ).fetchone()[0]
    con.execute(
        "UPDATE knowledge_run_items SET status='retryable', attempt_count=2 WHERE id=?",
        (row_id,),
    )
    con.commit()

    assert _claim_item(con, row_id, "2026-01-02T00:00:00Z") is True
    status, attempts = con.execute(
        "SELECT status, attempt_count FROM knowledge_run_items WHERE id=?", (row_id,)
    ).fetchone()
    assert (status, attempts) == ("in_flight", 3)
    con.close()
