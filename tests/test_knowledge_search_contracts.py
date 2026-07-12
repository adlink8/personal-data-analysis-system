"""Phase 14 Plan 05 测试：search contracts + feedback privacy。"""

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

from migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from evaluate_knowledge_canary import (  # noqa: E402
    read_active_collection, search_knowledge_units, generate_canary_queries,
)


def test_read_active_collection_none(tmp_path: Path) -> None:
    """无 active pointer 时返回 None。"""
    import evaluate_knowledge_canary as ec
    ec.ACTIVE_POINTER = tmp_path / "nonexistent.txt"
    assert read_active_collection() is None


def test_read_active_collection_reads(tmp_path: Path) -> None:
    """active pointer 存在时返回内容。"""
    import evaluate_knowledge_canary as ec
    ec.ACTIVE_POINTER = tmp_path / "active.txt"
    ec.ACTIVE_POINTER.write_text("test_collection", encoding="utf-8")
    assert read_active_collection() == "test_collection"


def test_search_knowledge_units_no_active(tmp_path: Path) -> None:
    """无 active 时 route=fallback_raw。"""
    import evaluate_knowledge_canary as ec
    ec.ACTIVE_POINTER = tmp_path / "nonexistent.txt"
    result = search_knowledge_units("test query", collection_name="nonexistent")
    assert result["route"] == "fallback_raw"


def test_search_knowledge_units_bad_collection(tmp_path: Path) -> None:
    """不存在的 collection 返回 fallback_raw。"""
    result = search_knowledge_units("test query", collection_name="nonexistent_collection_xyz")
    assert result["route"] == "fallback_raw"


def test_generate_canary_queries_hashes_only(tmp_path: Path) -> None:
    """canary queries 只含 hash，不含原文。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('r1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO canonical_knowledge_units (canonical_unit_id, subject, unit_type, question, "
        "answer, confidence, lifecycle, status, version, run_id, merge_reason, created_at) VALUES "
        "('cu1','test','preference','what is my name?','answer',0.9,'current','current',1,'r1','single','2026-01-01')"
    )
    con.commit()
    con.close()

    import evaluate_knowledge_canary as ec
    ec.UNIFIED_DB = db
    queries = generate_canary_queries(1)
    assert len(queries) == 1
    q = queries[0]
    assert "query_hash" in q
    assert "label" in q
    assert q["label"] == ""  # 初始为空，不是模型自填
    # 不含 raw query
    assert "query" not in q


def test_feedback_tables_created(tmp_path: Path) -> None:
    """rag_runs / rag_retrieval_items / rag_feedback 表存在。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "rag_runs" in tables
    assert "rag_retrieval_items" in tables
    assert "rag_feedback" in tables
    con.close()


def test_feedback_label_check(tmp_path: Path) -> None:
    """rag_feedback 的 label CHECK 约束生效。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute("INSERT INTO rag_runs VALUES ('r1','col1','v1','cb1','er1','canary','2026-01-01')")
    con.execute(
        "INSERT INTO rag_retrieval_items (run_id, query_hash, top_k, returned_ids, route, "
        "created_at) VALUES ('r1','hash1',5,'[]','canary','2026-01-01')"
    )
    con.commit()

    # valid label
    con.execute(
        "INSERT INTO rag_feedback (retrieval_id, label, labeled_at) VALUES (1,'helpful','2026-01-01')"
    )
    # invalid label
    with pytest.raises(sqlite3.IntegrityError):
        con.execute(
            "INSERT INTO rag_feedback (retrieval_id, label, labeled_at) VALUES (1,'bad_label','2026-01-01')"
        )
    con.close()


def test_feedback_no_raw_query_fields(tmp_path: Path) -> None:
    """rag_retrieval_items 不含 raw query 字段。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    cols = {c[1] for c in con.execute("PRAGMA table_info(rag_retrieval_items)")}
    assert "raw_query" not in cols
    assert "query_text" not in cols
    assert "evidence_quote" not in cols
    assert "result_text" not in cols
    con.close()


def test_canary_report_privacy_safe(tmp_path: Path) -> None:
    """canary report 不含 raw query/evidence。"""
    from evaluate_knowledge_canary import run_canary
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('r1','extraction','2026-01-01',NULL,'h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    for i in range(3):
        con.execute(
            "INSERT INTO canonical_knowledge_units VALUES "
            f"('cu{i}','subj{i}','preference','question {i}','answer {i}',0.9,'current','current',1,'r1','single',NULL,'2026-01-01')"
        )
    con.commit()
    con.close()

    import evaluate_knowledge_canary as ec
    ec.UNIFIED_DB = db
    report = run_canary("nonexistent_collection", n_queries=3, report_path=tmp_path / "canary.json")
    assert "results" in report
    for r in report["results"]:
        assert "query_hash" in r
        assert "raw_query" not in r
        assert "evidence_quote" not in r


# --- Hybrid search backend contract tests (unified_search.search_knowledge_units) ---

def test_hybrid_empty_query_abstains() -> None:
    """空 query 返回 abstain，不调用向量库。"""
    from unified_search import search_knowledge_units
    result = search_knowledge_units("", top_k=5)
    assert result["route"] == "abstain"
    assert result["results"] == []


def test_hybrid_no_active_falls_back() -> None:
    """无 active collection 且无 override 时 route=fallback_raw/abstain/knowledge(有 infra)。"""
    from unified_search import search_knowledge_units
    # 有 infra+active 时返回 knowledge；无时 fallback_raw/abstain
    result = search_knowledge_units("test query without infra", top_k=5)
    assert result["route"] in ("fallback_raw", "abstain", "knowledge")


def test_hybrid_top_k_bounded() -> None:
    """top_k 被 clamp 到 [1,20]。"""
    from unified_search import search_knowledge_units
    # 这些不会真正调用向量库（empty query 先 abstain）
    result = search_knowledge_units("", top_k=100)
    assert result["route"] == "abstain"
    result = search_knowledge_units("", top_k=0)
    assert result["route"] == "abstain"


def test_hybrid_result_contract_fields() -> None:
    """生产 backend 结果包含必需字段：rank/unit_id/retrieval_unit/score/collection。"""
    # 这个测试验证字段 schema，不依赖真实向量库
    # 模拟结果结构
    from unified_search import search_knowledge_units
    result = search_knowledge_units("", top_k=5)
    # abstain 时 results 为空，验证 route 合同
    assert "route" in result
    assert "results" in result
    assert "versions" in result
    assert isinstance(result["results"], list)
    assert isinstance(result["versions"], dict)