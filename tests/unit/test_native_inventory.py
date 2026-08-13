from __future__ import annotations

import sqlite3
from pathlib import Path

from personal_knowledge.application.conversation.native_inventory import (
    inventory_summary, read_native_inventory, split_virtual_locator,
)


def test_virtual_sqlite_locator_resolves_existing_db(tmp_path: Path) -> None:
    source = tmp_path / "native.db"
    sqlite3.connect(source).close()
    db = tmp_path / "agentsview.db"
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE sessions "
        "(id TEXT, agent TEXT, file_path TEXT, deleted_at TEXT)"
    )
    con.execute(
        "INSERT INTO sessions VALUES (?,?,?,NULL)",
        ("s1", "mimocode", f"{source}#ses_1"),
    )
    con.commit()
    con.close()
    rows = read_native_inventory(db)
    assert rows[0].family == "mimo"
    assert rows[0].source_path == source
    assert rows[0].virtual_session_id == "ses_1"
    assert rows[0].source_exists is True
    assert inventory_summary(rows)["mimo"] == {
        "sessions": 1, "native_available_sessions": 1,
        "unique_files": 1, "missing_sessions": 0,
    }


def test_missing_native_path_is_explicit() -> None:
    assert split_virtual_locator(None) == (None, None)
