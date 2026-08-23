"""Phase 14 Plan 05 测试：rag feedback privacy。"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL


def test_rag_feedback_tables_no_raw_query_fields(tmp_path: Path) -> None:
    """rag 表不含 raw query 字段。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()

    # 检查所有 rag 表
    for table in ("rag_runs", "rag_retrieval_items", "rag_feedback"):
        cols = {c[1] for c in con.execute(f"PRAGMA table_info({table})")}
        assert "raw_query" not in cols, f"{table} has raw_query"
        assert "query_text" not in cols, f"{table} has query_text"
        assert "evidence_quote" not in cols, f"{table} has evidence_quote"
        assert "result_text" not in cols, f"{table} has result_text"
        assert "content" not in cols, f"{table} has content"
        assert "credential" not in cols, f"{table} has credential"
        assert "token" not in cols, f"{table} has token"
        assert "secret" not in cols, f"{table} has secret"
    con.close()


def test_rag_retrieval_items_has_query_hash(tmp_path: Path) -> None:
    """rag_retrieval_items 有 query_hash 字段。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    cols = {c[1] for c in con.execute("PRAGMA table_info(rag_retrieval_items)")}
    assert "query_hash" in cols
    con.close()


def test_rag_feedback_labels_valid(tmp_path: Path) -> None:
    """rag_feedback 只接受 helpful/wrong/stale/missing labels。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute("INSERT INTO rag_runs VALUES ('r1','col1','v1','cb1','er1','canary','2026-01-01')")
    con.execute(
        "INSERT INTO rag_retrieval_items (run_id, query_hash, top_k, returned_ids, route, "
        "created_at) VALUES ('r1','hash1',5,'[]','canary','2026-01-01')"
    )
    con.commit()

    import pytest
    for label in ("helpful", "wrong", "stale", "missing"):
        con.execute(
            "INSERT INTO rag_feedback (retrieval_id, label, labeled_at) VALUES (1,?,?)", (label, "2026-01-01")
        )
        con.execute("DELETE FROM rag_feedback WHERE label=?", (label,))

    # invalid
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO rag_feedback (retrieval_id, label, labeled_at) VALUES (1,'bad','2026-01-01')"
        )
    con.close()
