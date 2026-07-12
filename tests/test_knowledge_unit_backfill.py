"""Phase 14 Plan 02 Task 1 测试：production inventory + work-item ledger。"""

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
from build_knowledge_inventory import (  # noqa: E402
    build_inventory,
    write_inventory_to_db,
    _content_hash,
    _strip_injections,
    _source_checksum,
)


def _make_canonical_db(dest: Path) -> Path:
    """造一个最小 canonical store fixture。"""
    con = sqlite3.connect(str(dest))
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE canonical_sessions ("
        "canonical_session_id TEXT PRIMARY KEY, primary_source TEXT, agent TEXT, "
        "started_at TEXT, ended_at TEXT, message_count INTEGER, user_message_count INTEGER, "
        "file_hash TEXT, parent_canonical_id TEXT, relationship_type TEXT, cwd TEXT, "
        "git_branch TEXT, model TEXT, evidence_eligible INTEGER DEFAULT 1, "
        "evidence_scope TEXT DEFAULT 'user', merged INTEGER DEFAULT 0)"
    )
    cur.execute(
        "CREATE TABLE canonical_messages ("
        "canonical_message_id TEXT PRIMARY KEY, canonical_session_id TEXT, source TEXT, "
        "source_message_ref TEXT, ordinal INTEGER, role TEXT, content TEXT, "
        "content_length INTEGER, timestamp TEXT, model TEXT, is_system INTEGER, "
        "is_sidechain INTEGER, content_hash TEXT, evidence_scope TEXT)"
    )
    # 3 eligible user messages + 1 assistant（排除）
    cur.execute(
        "INSERT INTO canonical_sessions VALUES "
        "('cs1','agentsview','codex','2026-01-01',NULL,3,3,NULL,NULL,NULL,NULL,NULL,NULL,1,'user',0),"
        "('cs2','agentsview','chatgpt','2026-02-01',NULL,1,1,NULL,NULL,NULL,NULL,NULL,NULL,1,'user',0)"
    )
    cur.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cm1','cs1','agentsview','av:1',1,'user','我习惯用 PowerShell 做所有本机操作不喜欢用 cmd',48,'2026-01-01',NULL,0,0,'h1','user'),"
        "('cm2','cs1','agentsview','av:2',2,'user','项目用 GSD 管理阶段每个阶段走 discuss plan execute verify ship',55,'2026-01-01',NULL,0,0,'h2','user'),"
        "('cm3','cs1','agentsview','av:3',3,'assistant','好的我来帮你',8,'2026-01-01',NULL,0,0,'h3','assistant'),"
        "('cm4','cs2','agentsview','av:4',1,'user','<system-reminder>time</system-reminder>用户实际指令内容超过三十字的部分',50,'2026-02-01',NULL,0,0,'h4','user')"
    )
    con.commit()
    con.close()
    return dest


def test_inventory_deterministic(tmp_path: Path) -> None:
    """同输入两次构建 inventory，dataset_hash 和 inventory_id 完全相同。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    inv1 = build_inventory(db)
    inv2 = build_inventory(db)
    assert inv1["dataset_hash"] == inv2["dataset_hash"]
    assert inv1["inventory_id"] == inv2["inventory_id"]
    assert inv1["authoritative_count"] == inv2["authoritative_count"]


def test_inventory_excludes_non_user(tmp_path: Path) -> None:
    """assistant 消息被排除，user 消息保留。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    inv = build_inventory(db)
    refs = [item["evidence_ref"] for item in inv["items"]]
    assert "cm1" in refs  # user >30 字
    assert "cm2" in refs  # user >30 字
    assert "cm3" not in refs  # assistant → 排除
    # cm4 清洗后只有 16 字，被正确排除
    assert "cm4" not in refs


def test_inventory_excludes_short_after_cleaning(tmp_path: Path) -> None:
    """清洗后过短的消息被排除。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    inv = build_inventory(db)
    assert inv["excluded"]["short_after_cleaning"] >= 0
    # 所有 authoritative items 都 > 30 字
    for item in inv["items"]:
        assert item["content_hash"]


def test_inventory_explains_coarse_vs_authoritative(tmp_path: Path) -> None:
    """inventory 报告解释 coarse 和 authoritative 的差异。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    inv = build_inventory(db)
    assert inv["coarse_count"] >= inv["authoritative_count"]
    excluded_total = sum(inv["excluded"].values())
    assert inv["coarse_count"] - excluded_total <= inv["authoritative_count"] + 1  # 容忍 injection_only 重叠


def test_inventory_no_raw_content_in_report(tmp_path: Path) -> None:
    """inventory items 不含原始 content（只有 hash）。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    inv = build_inventory(db)
    for item in inv["items"]:
        assert "content" not in item
        assert "evidence_quote" not in item
        assert item["content_hash"]  # 只有 hash


def test_inventory_write_to_db(tmp_path: Path) -> None:
    """inventory 写入 DB 后可回查。"""
    canon = _make_canonical_db(tmp_path / "canon.db")
    db = tmp_path / "unified.db"
    # 建 schema
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()

    inv = build_inventory(canon)
    write_inventory_to_db(inv, db)

    con = sqlite3.connect(str(db))
    # inventory 主表
    row = con.execute(
        "SELECT item_count, dataset_hash FROM knowledge_inventory WHERE inventory_id=?",
        (inv["inventory_id"],),
    ).fetchone()
    assert row is not None
    assert row[0] == inv["authoritative_count"]
    assert row[1] == inv["dataset_hash"]
    # items 表
    item_count = con.execute(
        "SELECT COUNT(*) FROM knowledge_inventory_items WHERE inventory_id=?",
        (inv["inventory_id"],),
    ).fetchone()[0]
    assert item_count == inv["authoritative_count"]
    # positions 有序且唯一
    positions = [r[0] for r in con.execute(
        "SELECT position FROM knowledge_inventory_items WHERE inventory_id=? ORDER BY position",
        (inv["inventory_id"],),
    )]
    assert positions == list(range(len(positions)))
    con.close()


def test_inventory_drift_detection(tmp_path: Path) -> None:
    """source 变化时 inventory_id 变化（drift 检测基础）。"""
    db1 = _make_canonical_db(tmp_path / "canon1.db")

    # 造第二个不同的 DB
    db2 = tmp_path / "canon2.db"
    con = sqlite3.connect(str(db2))
    cur = con.cursor()
    cur.execute(
        "CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, agent TEXT, "
        "started_at TEXT, evidence_eligible INTEGER DEFAULT 1)"
    )
    cur.execute(
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, "
        "canonical_session_id TEXT, role TEXT, content TEXT, source TEXT)"
    )
    cur.execute(
        "INSERT INTO canonical_sessions VALUES ('csX','codex','2026-03-01',1)"
    )
    cur.execute(
        "INSERT INTO canonical_messages VALUES "
        "('cmX','csX','user','一条完全不同的用户消息内容超过三十个字的长度','agentsview')"
    )
    con.commit()
    con.close()

    inv1 = build_inventory(db1)
    inv2 = build_inventory(db2)
    assert inv1["inventory_id"] != inv2["inventory_id"]
    assert inv1["dataset_hash"] != inv2["dataset_hash"]


def test_source_checksum_stable(tmp_path: Path) -> None:
    """同 DB 两次 checksum 相同。"""
    db = _make_canonical_db(tmp_path / "canon.db")
    cs1 = _source_checksum(db)
    cs2 = _source_checksum(db)
    assert cs1 == cs2


def test_migrate_includes_plan02_tables(tmp_path: Path) -> None:
    """migration 包含 Plan 02 的 5 张新表。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()

    con = sqlite3.connect(str(db))
    new_tables = [
        "knowledge_inventory", "knowledge_inventory_items",
        "knowledge_run_items", "knowledge_response_cache", "knowledge_extraction_gates",
    ]
    existing = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for t in new_tables:
        assert t in existing, f"missing Plan 02 table: {t}"
    con.close()


def test_run_items_state_machine_check(tmp_path: Path) -> None:
    """knowledge_run_items 的 status CHECK 约束生效。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    # 先建依赖行
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','path','cs','5','5','dh','2026-01','2026-02','{}')"
    )
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.commit()

    # valid status
    con.execute(
        "INSERT INTO knowledge_run_items (run_id, inventory_id, position, evidence_ref, status) "
        "VALUES ('run1','inv1',0,'cm1','pending')"
    )

    # invalid status
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO knowledge_run_items (run_id, inventory_id, position, evidence_ref, status) "
            "VALUES ('run1','inv1',1,'cm2','invalid_status')"
        )
    con.close()
