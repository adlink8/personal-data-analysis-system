"""一次性 schema 迁移：knowledge_inventory_items 增加 role 列（Phase 41，D-05）。

- 已有 role 列 → 打印 no_op 退出 0（幂等）。
- 无 role 列 →（--write 时）ALTER TABLE ADD COLUMN role TEXT，随后按
  evidence_ref join canonical DB 的 canonical_messages.role 回填；
  回填不了的行（消息已不存在）置 'unknown' 并计数 unresolved_role_count。
- 默认 dry-run：只打印影响行数、按 role 分布计数、unresolved 计数；
  报告只含 count，不含原文（隐私安全）。

新库的建表 DDL 已自带 role 列（migrate_add_knowledge_unit_tables.SCHEMA_SQL），
本脚本只服务既有库。

用法:
    python tools/migrations/add_inventory_items_role_column.py           # dry-run（默认）
    python tools/migrations/add_inventory_items_role_column.py --write   # 实际写入（先备份）
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import (  # noqa: E402
    AGENT_CONVERSATIONS_DB,
    UNIFIED_DB,
    VAR_DIR,
)

BACKUP_DIR = VAR_DIR / "backups"


def _has_role_column(con: sqlite3.Connection) -> bool:
    cols = {r[1] for r in con.execute("PRAGMA table_info(knowledge_inventory_items)")}
    return "role" in cols


def _load_role_index(canonical_db: Path, refs: list[str]) -> dict[str, str]:
    """canonical_message_id → role（分批查询）。"""
    index: dict[str, str] = {}
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    try:
        for i in range(0, len(refs), 500):
            chunk = refs[i : i + 500]
            marks = ",".join("?" * len(chunk))
            for mid, role in con.execute(
                "SELECT canonical_message_id, role FROM canonical_messages "
                f"WHERE canonical_message_id IN ({marks})",
                chunk,
            ):
                if role:
                    index[mid] = role
    finally:
        con.close()
    return index


def _backup_unified_db(unified_db: Path) -> Path:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = BACKUP_DIR / f"personal_system_{stamp}.sqlite"
    shutil.copy2(unified_db, dest)
    return dest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="只出报告，不写（默认）")
    mode.add_argument("--write", action="store_true", help="实际写入（先备份 UNIFIED_DB）")
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    parser.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    args = parser.parse_args(argv)

    con = sqlite3.connect(str(args.db))
    try:
        tables = {
            r[0]
            for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if "knowledge_inventory_items" not in tables:
            print("no_op: knowledge_inventory_items 表不存在（新库将由 SCHEMA_SQL 建带 role 列的表）")
            return 0
        if _has_role_column(con):
            print("no_op: knowledge_inventory_items 已有 role 列")
            return 0

        refs = sorted(
            r[0]
            for r in con.execute(
                "SELECT DISTINCT evidence_ref FROM knowledge_inventory_items"
            )
        )
        row_count = con.execute(
            "SELECT COUNT(*) FROM knowledge_inventory_items"
        ).fetchone()[0]

        if args.canonical_db.exists():
            role_index = _load_role_index(args.canonical_db, refs)
        else:
            print(f"[warn] canonical DB 不存在: {args.canonical_db}（全部按 unresolved 计）")
            role_index = {}

        by_role: Counter = Counter()
        unresolved = 0
        for ref in refs:
            role = role_index.get(ref)
            if role:
                by_role[role] += 1
            else:
                unresolved += 1

        print("== add_inventory_items_role_column ==")
        print(f"  影响行数 (items 总行数): {row_count}")
        print(f"  distinct evidence_ref 数: {len(refs)}")
        print(f"  按 role 分布 (按 ref 计): {dict(by_role)}")
        print(f"  unresolved_role_count (按 ref 计): {unresolved}")

        if not args.write:
            print("\n(dry_run：未做任何修改；加 --write 执行)")
            return 0

        backup = _backup_unified_db(args.db)
        print(f"备份: {backup}")
        try:
            con.execute("BEGIN")
            con.execute("ALTER TABLE knowledge_inventory_items ADD COLUMN role TEXT")
            updated = 0
            for ref, role in role_index.items():
                updated += con.execute(
                    "UPDATE knowledge_inventory_items SET role=? "
                    "WHERE evidence_ref=? AND role IS NULL",
                    (role, ref),
                ).rowcount
            unresolved_rows = con.execute(
                "UPDATE knowledge_inventory_items SET role='unknown' WHERE role IS NULL"
            ).rowcount
            con.commit()
        except Exception:
            con.rollback()
            raise
        print(f"[ok] role 列已添加；回填行数: {updated}；置 'unknown' 行数: {unresolved_rows}")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    raise SystemExit(main())
