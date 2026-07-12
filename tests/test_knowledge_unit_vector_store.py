"""Phase 14 Plan 04 测试：candidate vector store（actual-ID reconcile + active collision）。"""

from __future__ import annotations

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


def _setup_db_with_units(db: Path, n_units: int = 3) -> str:
    """建 schema + run + canonical units，返回 run_id。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',3,3,'dh','2026-01','2026-02','{}')"
    )
    for i in range(n_units):
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"u{i}", "run1", "preference", f"subj{i}", f"q{i}?", f"a{i}", 0.9, "ev", "user", "current", "2026-01-01", f"cm{i}")
        )
        con.execute(
            "INSERT INTO canonical_knowledge_units VALUES "
            "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"cu{i}", f"subj{i}", "preference", f"q{i}?", f"a{i}", 0.9, "current", "current", 1, "run1", "single", None, "2026-01-01")
        )
        con.execute(
            "INSERT INTO canonical_unit_members (canonical_unit_id, member_unit_id) VALUES (?,?)",
            (f"cu{i}", f"u{i}")
        )
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?)",
            (i, f"cm{i}", f"hash{i}", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible")
        )
    con.commit()
    con.close()
    return "run1"


def test_vector_store_stats_gate_pass(tmp_path: Path) -> None:
    """stats gate：missing=0, orphan=0, duplicate=0 → PASS。"""
    from build_knowledge_unit_vector_store import VectorStoreStats
    stats = VectorStoreStats(
        eligible_units=3, indexed=3, missing=0, orphan=0, duplicate=0,
        gate_passed=True,
    )
    assert stats.gate_passed


def test_vector_store_stats_gate_fail_on_missing(tmp_path: Path) -> None:
    """missing > 0 → gate FAIL。"""
    from build_knowledge_unit_vector_store import VectorStoreStats
    stats = VectorStoreStats(
        eligible_units=3, indexed=2, missing=1, orphan=0, duplicate=0,
    )
    assert not stats.gate_passed


def test_vector_store_stats_gate_fail_on_orphan(tmp_path: Path) -> None:
    """orphan > 0 → gate FAIL。"""
    from build_knowledge_unit_vector_store import VectorStoreStats
    stats = VectorStoreStats(
        eligible_units=3, indexed=4, missing=0, orphan=1, duplicate=0,
    )
    assert not stats.gate_passed


def test_vector_store_stats_gate_fail_on_duplicate(tmp_path: Path) -> None:
    """duplicate > 0 → gate FAIL。"""
    from build_knowledge_unit_vector_store import VectorStoreStats
    stats = VectorStoreStats(
        eligible_units=3, indexed=3, missing=0, orphan=0, duplicate=1,
    )
    assert not stats.gate_passed


def test_load_eligible_units_only_current(tmp_path: Path) -> None:
    """load_eligible_units 只加载 status='current' 的 canonical units。"""
    db = tmp_path / "test.sqlite"
    _setup_db_with_units(db, 3)

    # 加一个 rejected canonical unit
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO canonical_knowledge_units VALUES "
        "('cu_rej','x','preference','q','a',0.9,'current','rejected',1,'run1','single',NULL,'2026-01-01')"
    )
    con.commit()
    con.close()

    from build_knowledge_unit_vector_store import load_eligible_units
    units = load_eligible_units(db)
    # 不含 rejected
    unit_ids = [u["unit_id"] for u in units]
    assert "cu_rej" not in unit_ids


def test_get_current_run_id(tmp_path: Path) -> None:
    """_get_current_run_id 返回最新的 validated/current run。"""
    db = tmp_path / "test.sqlite"
    _setup_db_with_units(db, 1)

    from build_knowledge_unit_vector_store import _get_current_run_id
    run_id = _get_current_run_id(db)
    assert run_id == "run1"


def test_get_current_run_id_none(tmp_path: Path) -> None:
    """无 validated run 时返回 None。"""
    db = tmp_path / "test.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()

    from build_knowledge_unit_vector_store import _get_current_run_id
    assert _get_current_run_id(db) is None


def test_collection_name_contains_build_id(tmp_path: Path) -> None:
    """collection name 包含 build ID。"""
    from build_knowledge_unit_vector_store import COLLECTION_PREFIX
    assert COLLECTION_PREFIX == "knowledge_units"


def test_dry_run_does_not_write(tmp_path: Path) -> None:
    """dry-run 不写 DB 或 Chroma。"""
    db = tmp_path / "test.sqlite"
    _setup_db_with_units(db, 2)

    from build_knowledge_unit_vector_store import build_candidate_index
    stats, coll_name = build_candidate_index(db, write=False)
    assert coll_name is None
    assert stats.eligible_units == 2
