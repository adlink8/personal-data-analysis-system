"""Phase 14 Wave 1.1 测试：knowledge_unit schema 契约。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import (  # noqa: E402
    SCHEMA_SQL,
    inspect,
    migrate,
)


REQUIRED_TABLES = [
    "knowledge_build_runs",
    "knowledge_units",
    "knowledge_unit_evidence",
    "canonical_knowledge_units",
    "canonical_unit_members",
    "knowledge_index_versions",
]


def test_schema_creates_all_tables(tmp_path: Path) -> None:
    """迁移在空 DB 上创建全部 6 张表。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()

    con = sqlite3.connect(str(db))
    tables = {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    con.close()
    for t in REQUIRED_TABLES:
        assert t in tables, f"missing table: {t}"


def test_migrate_idempotent(tmp_path: Path) -> None:
    """迁移幂等：跑两次不报错。"""
    db = tmp_path / "test.sqlite"
    # 先建一个空 DB
    sqlite3.connect(str(db)).close()

    r1 = migrate(db, write=True)
    assert r1["migrated"] is True
    r2 = migrate(db, write=True)
    assert "message" in r2 or r2.get("migrated") is True  # 第二次无新表或幂等


def test_knowledge_units_check_constraints(tmp_path: Path) -> None:
    """knowledge_units 的 CHECK 约束生效。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()

    # 先建一个 build_run
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'hash1','v1','v1','model',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )

    # valid unit_type
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, created_at) VALUES "
        "('u1','run1','preference','shell','用什么shell？','PowerShell',0.9,'我用PS','2026-01-01')"
    )

    # invalid unit_type → IntegrityError
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, created_at) VALUES "
            "('u2','run1','invalid_type','x','q','a',0.9,'e','2026-01-01')"
        )

    # confidence out of range
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, created_at) VALUES "
            "('u3','run1','preference','x','q','a',1.5,'e','2026-01-01')"
        )
    con.close()


def test_evidence_unique_constraint(tmp_path: Path) -> None:
    """knowledge_unit_evidence 的 UNIQUE(unit_id, evidence_ref) 生效。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
        "confidence, evidence_quote, created_at) VALUES "
        "('u1','run1','preference','x','q','a',0.9,'e','2026-01-01')"
    )
    con.execute(
        "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u1','ev1')"
    )
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u1','ev1')"
        )
    con.close()


def test_inspect_on_missing_db(tmp_path: Path) -> None:
    """inspect 对不存在的 DB 返回 db_exists=False。"""
    result = inspect(tmp_path / "nope.db")
    assert result["db_exists"] is False


def test_migrate_does_not_touch_memory_items(tmp_path: Path) -> None:
    """迁移不修改 memory_items 表。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    # 建一个 memory_items 表（模拟现有）
    con.execute("CREATE TABLE memory_items (id TEXT, content TEXT)")
    con.execute("INSERT INTO memory_items VALUES ('m1', 'test memory')")
    con.commit()
    con.close()

    migrate(db, write=True)

    con = sqlite3.connect(str(db))
    row = con.execute("SELECT * FROM memory_items").fetchone()
    con.close()
    assert row == ("m1", "test memory"), "memory_items 被修改了！"
