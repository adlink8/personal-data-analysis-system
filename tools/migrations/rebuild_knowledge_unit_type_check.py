"""Phase 41 Plan 02 Task 0（阻断前置）：unit_type CHECK 表重建迁移。

SQLite 不能 ALTER CHECK。knowledge_units 与 canonical_knowledge_units 的
unit_type CHECK 只含 6 个 user 轨类型，assistant 轨（D-01）需要
solution / decision_rationale / technical_conclusion 三个新类型——
不迁移则 as| unit 的 INSERT 必然失败。

对两表执行标准 SQLite 表重建：
  PRAGMA foreign_keys=OFF → BEGIN → CREATE TABLE <t>_new（DDL 与现表逐列
  相同，仅 unit_type CHECK 扩为 9 类型）→ INSERT SELECT * → 行数守恒断言
  （不等即 ROLLBACK 退出非零）→ DROP 旧表 → RENAME → 重建全部索引 →
  COMMIT → PRAGMA foreign_keys=ON → PRAGMA foreign_key_check 必须 0 行。

幂等：CHECK 已含 'solution' → 打印 no_op 退出 0。
默认 dry-run（只打印现状与计划，不落库）；--write 前自动备份到
var/backups/unified_db_pre_unit_type_check_<UTC>.sqlite，备份失败即中止。

用法::

    python tools/migrations/rebuild_knowledge_unit_type_check.py            # dry-run
    python tools/migrations/rebuild_knowledge_unit_type_check.py --write    # 落库
    python tools/migrations/rebuild_knowledge_unit_type_check.py --db X.sqlite --write
"""

from __future__ import annotations

import argparse
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.core.project_paths import UNIFIED_DB, VAR_DIR  # noqa: E402

TABLES = ("knowledge_units", "canonical_knowledge_units")
NEW_UNIT_TYPE_CHECK = (
    "CHECK(unit_type IN ('preference','habit','personal_fact','project_decision',"
    "'capability','tool_usage','solution','decision_rationale','technical_conclusion'))"
)
_UNIT_TYPE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*unit_type\s+IN\s*\([^)]*\)\)", re.IGNORECASE
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _table_ddl(con: sqlite3.Connection, table: str) -> str:
    row = con.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else ""


def _index_ddls(con: sqlite3.Connection, table: str) -> list[str]:
    """该表的全部显式索引 DDL（autoindex 的 sql 为 NULL，随表 DDL 自动重建）。"""
    return [
        r[0]
        for r in con.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL ORDER BY name",
            (table,),
        ).fetchall()
    ]


def _rebuilt_ddl(sql: str, table: str) -> str:
    """现表 DDL → <table>_new DDL：仅 unit_type CHECK 扩为 9 类型，其余逐列不变。"""
    new_sql, n_sub = _UNIT_TYPE_CHECK_RE.subn(NEW_UNIT_TYPE_CHECK, sql)
    if n_sub != 1:
        raise ValueError(f"{table}: 未唯一定位 unit_type CHECK（命中 {n_sub} 处）")
    new_sql, n_name = re.subn(
        rf"CREATE\s+TABLE\s+\"?{re.escape(table)}\"?\s*\(",
        f"CREATE TABLE {table}_new (",
        new_sql,
        count=1,
        flags=re.IGNORECASE,
    )
    if n_name != 1:
        raise ValueError(f"{table}: 未定位 CREATE TABLE 语句")
    return new_sql


def _check_already_migrated(con: sqlite3.Connection) -> bool:
    return all("'solution'" in _table_ddl(con, t) for t in TABLES)


def dry_run_report(con: sqlite3.Connection) -> None:
    print("[dry_run] unit_type CHECK 表重建计划（不落库）")
    for table in TABLES:
        ddl = _table_ddl(con, table)
        m = _UNIT_TYPE_CHECK_RE.search(ddl)
        count = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        indexes = _index_ddls(con, table)
        print(f"\n== {table} ==")
        print(f"  rows: {count}")
        print(f"  current CHECK: {m.group(0) if m else '(未找到!)'}")
        print(f"  new CHECK:     {NEW_UNIT_TYPE_CHECK}")
        print(f"  indexes to rebuild ({len(indexes)}):")
        for idx in indexes:
            print(f"    - {idx}")
    print("\n[dry_run] 未修改任何数据；加 --write 落库（先自动备份）。")


def rebuild(db_path: Path, *, write: bool) -> int:
    if not db_path.exists():
        print(f"[error] DB 不存在: {db_path}", file=sys.stderr)
        return 2

    probe = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    try:
        if _check_already_migrated(probe):
            print("[no_op] 两表 unit_type CHECK 已含 'solution'，无需迁移。")
            return 0
        missing = [t for t in TABLES if not _table_ddl(probe, t)]
        if missing:
            print(f"[error] 缺表: {missing}", file=sys.stderr)
            return 2
        if not write:
            dry_run_report(probe)
            return 0
    finally:
        probe.close()

    # --write：先备份，失败即中止
    backup_dir = VAR_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup_path = backup_dir / f"unified_db_pre_unit_type_check_{_utc_stamp()}.sqlite"
    try:
        shutil.copy2(db_path, backup_path)
    except OSError as e:
        print(f"[error] 备份失败，中止: {e}", file=sys.stderr)
        return 2
    print(f"[backup] {backup_path} ({backup_path.stat().st_size} bytes)")

    con = sqlite3.connect(str(db_path), isolation_level=None)
    try:
        # 重建计划（BEGIN 前读 sqlite_master）
        plans = []
        for table in TABLES:
            plans.append(
                {
                    "table": table,
                    "new_ddl": _rebuilt_ddl(_table_ddl(con, table), table),
                    "indexes": _index_ddls(con, table),
                    "rows_before": con.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0],
                }
            )

        con.execute("PRAGMA foreign_keys=OFF")
        con.execute("BEGIN")
        try:
            for plan in plans:
                table = plan["table"]
                con.execute(plan["new_ddl"])
                con.execute(
                    f"INSERT INTO {table}_new SELECT * FROM {table}"
                )
                rows_after = con.execute(
                    f"SELECT COUNT(*) FROM {table}_new"
                ).fetchone()[0]
                # 行数守恒断言：不等即 ROLLBACK 报错退出非零
                if rows_after != plan["rows_before"]:
                    raise RuntimeError(
                        f"{table}: 行数不守恒 before={plan['rows_before']} "
                        f"after={rows_after}"
                    )
                con.execute(f"DROP TABLE {table}")
                con.execute(f"ALTER TABLE {table}_new RENAME TO {table}")
                for idx_sql in plan["indexes"]:
                    con.execute(idx_sql)
                print(
                    f"[rebuilt] {table}: rows={rows_after} "
                    f"(conserved), indexes={len(plan['indexes'])}"
                )
            con.execute("COMMIT")
        except Exception:
            con.execute("ROLLBACK")
            raise
        con.execute("PRAGMA foreign_keys=ON")

        violations = con.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            print(
                f"[error] foreign_key_check 返回 {len(violations)} 行（应为 0）",
                file=sys.stderr,
            )
            return 1
        print("[ok] foreign_key_check: 0 violations")
    except Exception as e:
        print(f"[error] 重建失败（已回滚）: {e}", file=sys.stderr)
        return 1
    finally:
        con.close()

    # 写后幂等确认
    verify = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
    ok = _check_already_migrated(verify)
    verify.close()
    if not ok:
        print("[error] 写后校验失败：CHECK 仍不含 'solution'", file=sys.stderr)
        return 1
    print("[ok] unit_type CHECK 迁移完成（两表均含 9 类型）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--write", action="store_true", help="落库（默认 dry-run）")
    p.add_argument("--db", type=Path, default=UNIFIED_DB, help="unified DB 路径")
    args = p.parse_args(argv)
    return rebuild(args.db, write=args.write)


if __name__ == "__main__":
    raise SystemExit(main())
