"""Phase 14 Plan 06 Task 1 测试：incremental refresh + zero-residue。"""

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


def _setup_db(db: Path) -> None:
    """建 schema + inventory + units。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',3,3,'dh','2026-01','2026-02','{}')"
    )
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'validated',NULL,NULL)"
    )
    for i in range(3):
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?)",
            (i, f"cm{i}", f"hash{i}", "cs{i}", "agentsview", "codex", "2026-01", "mid", 0, "eligible")
        )
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, lifecycle, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (f"u{i}", "run1", "preference", f"subj{i}", f"q{i}", f"a{i}", 0.9, "ev", "current", "user", "current", "2026-01-01", f"cm{i}")
        )
    con.commit()
    con.close()


def _make_canonical_db(db: Path, refs: list[str]) -> None:
    """造 canonical store fixture。"""
    con = sqlite3.connect(str(db))
    cur = con.cursor()
    cur.execute("CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, evidence_eligible INTEGER DEFAULT 1)")
    cur.execute(
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, "
        "canonical_session_id TEXT, role TEXT, content TEXT)"
    )
    cur.execute("INSERT INTO canonical_sessions VALUES ('cs1', 1)")
    for ref in refs:
        cur.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?)",
            (ref, "cs1", "user", f"content for {ref} " + "x" * 30)
        )
    con.commit()
    con.close()


def test_no_change_is_noop(tmp_path: Path) -> None:
    """source 未变化时为 no-op。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    _make_canonical_db(canon, ["cm0", "cm1", "cm2"])

    from refresh_knowledge_units import find_affected_evidence, compute_source_checksum
    checksum = compute_source_checksum(canon)
    result = find_affected_evidence(db, canon, last_source_checksum=checksum)
    assert result["no_op"] is True
    assert result["source_changed"] is False


def test_new_evidence_detected(tmp_path: Path) -> None:
    """新增 evidence 被检测为 affected。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    # canonical 有 4 个 refs（inventory 只有 3）
    _make_canonical_db(canon, ["cm0", "cm1", "cm2", "cm_new"])

    from refresh_knowledge_units import find_affected_evidence
    result = find_affected_evidence(db, canon, last_source_checksum="")
    assert result["new_refs_count"] >= 1
    assert "cm_new" in result.get("new_refs", [])


def test_deleted_evidence_detected(tmp_path: Path) -> None:
    """消失的 evidence 被检测为 deleted。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    # canonical 只有 2 个 refs（inventory 有 3）
    _make_canonical_db(canon, ["cm0", "cm1"])

    from refresh_knowledge_units import find_affected_evidence
    result = find_affected_evidence(db, canon, last_source_checksum="")
    assert result["deleted_refs_count"] >= 1


def test_deprecated_propagation(tmp_path: Path) -> None:
    """deleted refs 的 units 被标记为 deprecated。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    _make_canonical_db(canon, ["cm0", "cm1"])  # cm2 消失

    from refresh_knowledge_units import refresh
    stats, detail = refresh(db, canon, last_source_checksum="", dry_run=False)
    assert stats.deprecated_count >= 1

    # 验证 DB
    con = sqlite3.connect(str(db))
    dep = con.execute(
        "SELECT COUNT(*) FROM knowledge_units WHERE lifecycle='deprecated'"
    ).fetchone()[0]
    con.close()
    assert dep >= 1


def test_source_checksum_stable(tmp_path: Path) -> None:
    """同 canonical DB 的 checksum 稳定。"""
    canon = tmp_path / "canon.sqlite"
    _make_canonical_db(canon, ["cm0", "cm1"])

    from refresh_knowledge_units import compute_source_checksum
    cs1 = compute_source_checksum(canon)
    cs2 = compute_source_checksum(canon)
    assert cs1 == cs2
