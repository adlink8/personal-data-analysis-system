"""Phase 14 Wave 4 测试：candidate vector store + promotion + rollback。"""

from __future__ import annotations

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

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402


def _setup_db(db: Path) -> None:
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'current',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, created_at, status, source_message_ref) VALUES "
        "('u1','run1','preference','shell','用什么shell？','PowerShell',0.9,'我用PS','2026-01-01','current','cm|gold1'),"
        "('u2','run1','personal_fact','OS','用什么系统？','Windows',0.9,'我用Windows','2026-01-01','current','cm|gold2')"
    )
    con.commit()
    con.close()


# === promote / rollback 测试（不依赖 Chroma）===

def test_promote_writes_active_pointer(tmp_path: Path) -> None:
    """promote 写入 active pointer 文件。"""
    import personal_knowledge.domains.knowledge.promote_knowledge_index as pk
    db = tmp_path / "db.sqlite"
    _setup_db(db)
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"
    pk.PROMOTE_LOG = tmp_path / "knowledge_index_promote_log.jsonl"

    # 先写一条 index version
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO knowledge_index_versions VALUES "
        "('v1','run1','ku_test','run1',2,'candidate','2026-01-01',NULL,NULL)"
    )
    con.commit()
    con.close()

    result = pk.promote("ku_test", db_path=db)
    assert result["promoted"] == "ku_test"
    assert pk.read_active() == "ku_test"


def test_rollback_restores_previous(tmp_path: Path) -> None:
    """rollback 恢复上一个 active。"""
    import personal_knowledge.domains.knowledge.promote_knowledge_index as pk
    db = tmp_path / "db.sqlite"
    _setup_db(db)
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"
    pk.PROMOTE_LOG = tmp_path / "knowledge_index_promote_log.jsonl"

    con = sqlite3.connect(str(db))
    con.executescript(
        "INSERT INTO knowledge_index_versions VALUES "
        "('v1','run1','ku_old','run1',1,'candidate','2026-01-01',NULL,NULL),"
        "('v2','run1','ku_new','run1',2,'candidate','2026-01-02',NULL,NULL)"
    )
    con.commit()
    con.close()

    pk.promote("ku_old", db_path=db)
    pk.promote("ku_new", db_path=db)
    assert pk.read_active() == "ku_new"

    result = pk.rollback_to_previous(db_path=db)
    assert result["rolled_back_to"] == "ku_old"
    assert pk.read_active() == "ku_old"


def test_rollback_no_previous_errors(tmp_path: Path) -> None:
    """没有上一个可回滚时报错。"""
    import personal_knowledge.domains.knowledge.promote_knowledge_index as pk
    db = tmp_path / "db.sqlite"
    _setup_db(db)
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"
    pk.PROMOTE_LOG = tmp_path / "knowledge_index_promote_log.jsonl"

    pk.promote("ku_test", db_path=db)
    result = pk.rollback_to_previous(db_path=db)
    assert "error" in result


def test_list_versions(tmp_path: Path) -> None:
    """list_versions 返回所有 version。"""
    import personal_knowledge.domains.knowledge.promote_knowledge_index as pk
    db = tmp_path / "db.sqlite"
    _setup_db(db)
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"

    con = sqlite3.connect(str(db))
    con.executescript(
        "INSERT INTO knowledge_index_versions VALUES "
        "('v1','run1','ku_a','run1',2,'candidate','2026-01-01',NULL,NULL),"
        "('v2','run1','ku_b','run1',3,'active','2026-01-02','2026-01-02',NULL)"
    )
    con.commit()
    con.close()

    versions = pk.list_versions(db_path=db)
    assert len(versions) == 2
    active = [v for v in versions if v["status"] == "active"]
    assert len(active) == 1


def test_promote_log_appended(tmp_path: Path) -> None:
    """promote 和 rollback 都追加到 log。"""
    import personal_knowledge.domains.knowledge.promote_knowledge_index as pk
    db = tmp_path / "db.sqlite"
    _setup_db(db)
    pk.DB_DIR = tmp_path
    pk.ACTIVE_POINTER = tmp_path / "knowledge_index_active.txt"
    pk.PROMOTE_LOG = tmp_path / "knowledge_index_promote_log.jsonl"

    con = sqlite3.connect(str(db))
    con.executescript(
        "INSERT INTO knowledge_index_versions VALUES "
        "('v1','run1','ku_old','run1',1,'candidate','2026-01-01',NULL,NULL),"
        "('v2','run1','ku_new','run1',2,'candidate','2026-01-02',NULL,NULL)"
    )
    con.commit()
    con.close()

    pk.promote("ku_old", db_path=db)
    pk.promote("ku_new", db_path=db)
    pk.rollback_to_previous(db_path=db)

    lines = pk.PROMOTE_LOG.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 3  # promote + promote + rollback
    actions = [json.loads(l)["action"] for l in lines]
    assert actions == ["promote", "promote", "rollback"]
