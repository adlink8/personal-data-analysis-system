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

from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402


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
            "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?,?)",
            (i, f"cm{i}", f"hash{i}", "cs{i}", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user")
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
    cur.execute("CREATE TABLE canonical_sessions (canonical_session_id TEXT PRIMARY KEY, agent TEXT, started_at TEXT, evidence_eligible INTEGER DEFAULT 1)")
    cur.execute(
        "CREATE TABLE canonical_messages (canonical_message_id TEXT PRIMARY KEY, "
        "canonical_session_id TEXT, role TEXT, content TEXT, source TEXT)"
    )
    cur.execute("INSERT INTO canonical_sessions VALUES ('cs1', 'codex', '2026-01-01', 1)")
    for ref in refs:
        cur.execute(
            "INSERT INTO canonical_messages VALUES (?,?,?,?,?)",
            (ref, "cs1", "user", f"content for {ref} " + "x" * 30, "agentsview")
        )
    con.commit()
    con.close()


def test_no_change_is_noop(tmp_path: Path) -> None:
    """source 未变化时为 no-op。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    _make_canonical_db(canon, ["cm0", "cm1", "cm2"])

    from personal_knowledge.application.knowledge.refresh_knowledge_units import find_affected_evidence, compute_source_checksum
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

    from personal_knowledge.application.knowledge.refresh_knowledge_units import find_affected_evidence
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

    from personal_knowledge.application.knowledge.refresh_knowledge_units import find_affected_evidence
    result = find_affected_evidence(db, canon, last_source_checksum="")
    assert result["deleted_refs_count"] >= 1


def test_large_delta_keeps_full_execution_lists_and_batched_subjects(
    tmp_path: Path,
) -> None:
    """Preview limits must never truncate execution or subject discovery."""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)

    con = sqlite3.connect(db)
    for i in range(600):
        ref = f"gone{i:03d}"
        con.execute(
            "INSERT INTO knowledge_inventory_items VALUES "
            "(NULL,'inv1',?,?,?,?,?,?,?,?,?,?,?)",
            (1000 + i, ref, f"hash-{i}", f"cs-{i}", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user"),
        )
        con.execute(
            "INSERT INTO knowledge_units "
            "(unit_id, run_id, unit_type, subject, question, answer, confidence, "
            "evidence_quote, lifecycle, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"gone-unit-{i}", "run1", "preference", f"subject-{i}",
                f"q-{i}", f"a-{i}", 0.9, "ev", "current", "user",
                "current", "2026-01-01", ref,
            ),
        )
    con.commit()
    con.close()
    _make_canonical_db(canon, ["cm0", "cm1", "cm2"])

    from personal_knowledge.application.knowledge.refresh_knowledge_units import (
        find_affected_evidence,
        refresh,
    )

    result = find_affected_evidence(db, canon, last_source_checksum="")
    assert result["deleted_refs_count"] == 600
    assert len(result["deleted_refs"]) == 600
    assert len(result["deleted_refs_preview"]) == 100
    assert result["preview_truncated"] is True
    assert len(result["affected_subjects"]) == 600

    stats, _detail = refresh(db, canon, last_source_checksum="", dry_run=False)
    assert stats.deprecated_count == 600


def test_large_new_delta_has_full_input_and_bounded_preview(tmp_path: Path) -> None:
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    refs = ["cm0", "cm1", "cm2"] + [f"cm-new-{i:03d}" for i in range(150)]
    _make_canonical_db(canon, refs)

    from personal_knowledge.application.knowledge.refresh_knowledge_units import (
        find_affected_evidence,
    )

    result = find_affected_evidence(db, canon, last_source_checksum="")
    assert result["new_refs_count"] == 150
    assert len(result["new_refs"]) == 150
    assert len(result["new_refs_preview"]) == 100
    assert result["preview_truncated"] is True


def test_deprecated_propagation(tmp_path: Path) -> None:
    """deleted refs 的 units 被标记为 deprecated。"""
    db = tmp_path / "test.sqlite"
    canon = tmp_path / "canon.sqlite"
    _setup_db(db)
    _make_canonical_db(canon, ["cm0", "cm1"])  # cm2 消失

    from personal_knowledge.application.knowledge.refresh_knowledge_units import refresh
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

    from personal_knowledge.application.knowledge.refresh_knowledge_units import compute_source_checksum
    cs1 = compute_source_checksum(canon)
    cs2 = compute_source_checksum(canon)
    assert cs1 == cs2


def test_get_committed_watermark_does_not_create_schema(tmp_path: Path) -> None:
    db = tmp_path / "empty.sqlite"
    sqlite3.connect(db).close()

    from personal_knowledge.application.knowledge.refresh_knowledge_units import (
        get_committed_watermark,
    )

    assert get_committed_watermark(db) == ""
    con = sqlite3.connect(db)
    tables = {
        row[0]
        for row in con.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    con.close()
    assert "knowledge_source_watermark" not in tables
