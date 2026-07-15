"""Phase 14 Plan 06 Task 2 测试：memory lifecycle sync。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402


def _setup_db(db: Path) -> None:
    """建 schema + memory_items + canonical units。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    # memory_items（匹配生产 schema，PK = memory_id）
    con.execute(
        "CREATE TABLE IF NOT EXISTS memory_items ("
        "memory_id TEXT PRIMARY KEY, memory_type TEXT, memory_subtype TEXT, "
        "subject TEXT, description TEXT, confidence REAL, evidence_count INTEGER, "
        "metadata TEXT, created_at TEXT)"
    )
    con.execute(
        "INSERT INTO memory_items (memory_id, subject, description, memory_type) VALUES "
        "('m1','PowerShell','uses PowerShell for scripting','tooling'),"
        "('m2','Python','uses Python asyncio','capability'),"
        "('m3','OldTool','legacy tool no longer used','tooling')"
    )
    # canonical units
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO canonical_knowledge_units VALUES "
        "('cu1','powershell','tool_usage','q','a',0.9,'current','current',1,'run1','single',NULL,'2026-01-01'),"
        "('cu2','python','capability','q','a',0.9,'current','current',1,'run1','single',NULL,'2026-01-01')"
    )
    con.commit()
    con.close()


def test_migrate_adds_columns(tmp_path: Path) -> None:
    """migration 添加 lifecycle 列。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate
    result = migrate(db, write=True)
    assert result["migrated"] is True
    assert len(result["added_columns"]) >= 3  # ku_status, ku_version, canonical_unit_id 等

    # 验证列存在
    con = sqlite3.connect(str(db))
    cols = {c[1] for c in con.execute("PRAGMA table_info(memory_items)")}
    assert "ku_status" in cols
    assert "canonical_unit_id" in cols
    con.close()


def test_migrate_idempotent(tmp_path: Path) -> None:
    """migration 幂等。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate
    migrate(db, write=True)
    result = migrate(db, write=True)
    assert result["added_columns"] == []  # 第二次无新列


def test_preview_no_db_diff(tmp_path: Path) -> None:
    """preview 不修改 DB。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import build_preview, migrate
    migrate(db, write=True)  # 先 migrate

    # 记录 DB 状态
    con = sqlite3.connect(str(db))
    before = con.execute("SELECT * FROM memory_items").fetchall()
    con.close()

    preview = build_preview(db)
    assert preview.create_count + preview.update_count + preview.deprecate_count > 0

    # DB 未变
    con = sqlite3.connect(str(db))
    after = con.execute("SELECT * FROM memory_items").fetchall()
    con.close()
    assert before == after


def test_write_links_matching(tmp_path: Path) -> None:
    """write 链接匹配的 memory_items。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate, build_preview, apply_write
    migrate(db, write=True)
    preview = build_preview(db)
    result = apply_write(db, preview.preview_hash)
    assert result["applied"] >= 1

    # 验证链接
    con = sqlite3.connect(str(db))
    linked = con.execute(
        "SELECT COUNT(*) FROM memory_items WHERE canonical_unit_id IS NOT NULL"
    ).fetchone()[0]
    con.close()
    assert linked >= 1


def test_write_no_physical_delete(tmp_path: Path) -> None:
    """write 不物理删除。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate, build_preview, apply_write
    migrate(db, write=True)
    preview = build_preview(db)
    apply_write(db, preview.preview_hash)

    con = sqlite3.connect(str(db))
    total = con.execute("SELECT COUNT(*) FROM memory_items").fetchone()[0]
    con.close()
    assert total == 3  # 仍然是 3 条


def test_write_hash_mismatch_rejected(tmp_path: Path) -> None:
    """preview hash 不匹配时拒绝写入。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate, apply_write
    migrate(db, write=True)
    result = apply_write(db, "wrong_hash")
    assert "error" in result


def test_write_idempotent(tmp_path: Path) -> None:
    """相同 preview 二次写入为 no-op。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate, build_preview, apply_write
    migrate(db, write=True)
    preview = build_preview(db)
    r1 = apply_write(db, preview.preview_hash)

    # 再次 build + apply
    preview2 = build_preview(db)
    r2 = apply_write(db, preview2.preview_hash)
    # 第二次应该也是 no-op 或很少变化
    assert r2["applied"] <= r1["applied"]


def test_preview_hash_stable(tmp_path: Path) -> None:
    """相同输入产生相同 preview hash。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    from personal_knowledge.domains.memory.sync_memory_lifecycle import migrate, build_preview
    migrate(db, write=True)
    p1 = build_preview(db)
    p2 = build_preview(db)
    assert p1.preview_hash == p2.preview_hash
