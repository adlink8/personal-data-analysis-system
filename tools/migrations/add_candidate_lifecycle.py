"""Add ``candidate`` to knowledge_units.lifecycle (dry-run by default).

The write path rebuilds only the table whose CHECK constraint needs widening,
preserving all rows and indexes.  It is intentionally separate from normal
application startup and always snapshots the unified database first.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from personal_knowledge.core.project_paths import UNIFIED_DB


def _snapshot(db_path: Path) -> Path:
    backup_dir = db_path.parents[1] / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = backup_dir / f"{db_path.stem}_{stamp}.sqlite"
    shutil.copy2(db_path, target)
    return target


def migrate(db_path: Path = UNIFIED_DB, *, write: bool = False) -> dict:
    uri = f"file:{db_path.resolve().as_posix()}?mode={'rw' if write else 'ro'}"
    con = sqlite3.connect(uri, uri=True)
    try:
        schema_row = con.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='knowledge_units'"
        ).fetchone()
        if not schema_row or not schema_row[0]:
            raise RuntimeError("knowledge_units table not found")
        schema = schema_row[0]
        already = "'candidate'" in schema
        rows = con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0]
        candidate_rows = con.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE lifecycle='candidate'"
        ).fetchone()[0]
        result = {
            "db": str(db_path),
            "write": write,
            "already_supported": already,
            "rows_before": rows,
            "candidate_rows_before": candidate_rows,
        }
        if already or not write:
            result["action"] = "noop" if already else "would_rebuild"
            return result

        backup = _snapshot(db_path)
        indexes = [
            row[0]
            for row in con.execute(
                "SELECT sql FROM sqlite_master WHERE type='index' "
                "AND tbl_name='knowledge_units' AND sql IS NOT NULL"
            ).fetchall()
        ]
        new_schema = schema.replace(
            "CREATE TABLE knowledge_units",
            "CREATE TABLE knowledge_units_new",
            1,
        ).replace(
            "CHECK(lifecycle IN ('current','deprecated','superseded','conflict'))",
            "CHECK(lifecycle IN ('current','deprecated','superseded','conflict','candidate'))",
            1,
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(knowledge_units)")]
        quoted = ", ".join('"' + col.replace('"', '""') + '"' for col in columns)
        con.execute("BEGIN IMMEDIATE")
        con.execute("PRAGMA foreign_keys=OFF")
        # Prevent SQLite from rewriting dependent FK clauses to the temporary
        # legacy table name during ALTER TABLE RENAME.
        con.execute("PRAGMA legacy_alter_table=ON")
        con.execute("ALTER TABLE knowledge_units RENAME TO knowledge_units_legacy")
        con.execute(new_schema)
        con.execute(
            f"INSERT INTO knowledge_units ({quoted}) SELECT {quoted} FROM knowledge_units_legacy"
        )
        con.execute("DROP TABLE knowledge_units_legacy")
        for index_sql in indexes:
            con.execute(index_sql)
        con.execute("PRAGMA foreign_keys=ON")
        fk_errors = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_errors:
            raise RuntimeError(f"foreign_key_check failed after candidate migration: {fk_errors[:5]}")
        con.commit()
        result.update({
            "action": "rebuilt",
            "backup": str(backup),
            "rows_after": con.execute("SELECT COUNT(*) FROM knowledge_units").fetchone()[0],
        })
        return result
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    parser.add_argument("--write", action="store_true", help="Persist the table rebuild")
    args = parser.parse_args()
    print(json.dumps(migrate(args.db, write=args.write), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
