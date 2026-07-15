"""Phase 14 Wave 1.2 测试：run manifest + staging publish helper。"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL
from personal_knowledge.application.knowledge.knowledge_unit_pipeline import (
    RunManifest,
    StagingPublisher,
)


def _setup_db(db: Path) -> None:
    """在临时 DB 上建 knowledge_unit schema。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.commit()
    con.close()


def _insert_unit(con: sqlite3.Connection, unit_id: str, run_id: str,
                 status: str = "staging") -> None:
    con.execute(
        "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, "
        "question, answer, confidence, evidence_quote, created_at, status) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (unit_id, run_id, "preference", "test", "q?", "a", 0.9, "ev", "2026-01-01", status),
    )


def test_manifest_create_stable_id() -> None:
    """相同输入产生相同 run_id（幂等）。"""
    m1 = RunManifest.create("extraction", "build-1", {"a": 1}, model="gemini")
    m2 = RunManifest.create("extraction", "build-1", {"a": 1}, model="gemini")
    assert m1.run_id == m2.run_id


def test_manifest_different_input_different_id() -> None:
    """不同输入产生不同 run_id。"""
    m1 = RunManifest.create("extraction", "build-1", {"a": 1})
    m2 = RunManifest.create("extraction", "build-1", {"a": 2})
    assert m1.run_id != m2.run_id


def test_staging_begin_writes_manifest(tmp_path: Path) -> None:
    """begin_staging 在 DB 写入 status='staging' 的 manifest。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)
    manifest = RunManifest.create("extraction", "build-1", {"a": 1}, model="gemini")
    publisher = StagingPublisher(manifest, db_path=db)
    publisher.begin_staging()

    con = sqlite3.connect(str(db))
    row = con.execute(
        "SELECT status, model FROM knowledge_build_runs WHERE run_id=?",
        (manifest.run_id,),
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "staging"
    assert row[1] == "gemini"


def test_promote_upgrades_staging_to_current(tmp_path: Path) -> None:
    """promote：staging units → current，旧 current → superseded。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    # 旧 run（current）
    old_manifest = RunManifest.create("extraction", "build-0", {"old": True})
    old_pub = StagingPublisher(old_manifest, db_path=db)
    old_pub.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-old", old_manifest.run_id, status="current")
    con.commit()
    con.close()

    # 新 run（staging）
    manifest = RunManifest.create("extraction", "build-1", {"new": True})
    publisher = StagingPublisher(manifest, db_path=db)
    publisher.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-new", manifest.run_id, status="staging")
    con.commit()
    con.close()

    # promote
    publisher.promote(dataset_hash="abc123")

    con = sqlite3.connect(str(db))
    # 新 unit → current
    new_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-new'"
    ).fetchone()[0]
    assert new_status == "current"
    # 旧 unit → staging（superseded）
    old_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-old'"
    ).fetchone()[0]
    assert old_status == "staging"
    # manifest → current
    run_status = con.execute(
        "SELECT status FROM knowledge_build_runs WHERE run_id=?",
        (manifest.run_id,),
    ).fetchone()[0]
    assert run_status == "current"
    con.close()


def test_abort_does_not_clear_old_current(tmp_path: Path) -> None:
    """abort：旧 current 不被清空，新 staging → rejected。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    old_manifest = RunManifest.create("extraction", "build-0", {"old": True})
    old_pub = StagingPublisher(old_manifest, db_path=db)
    old_pub.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-old", old_manifest.run_id, status="current")
    con.commit()
    con.close()

    manifest = RunManifest.create("extraction", "build-1", {"new": True})
    publisher = StagingPublisher(manifest, db_path=db)
    publisher.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-new", manifest.run_id, status="staging")
    con.commit()
    con.close()

    publisher.abort(reason="gate failed")

    con = sqlite3.connect(str(db))
    # 旧 current 仍是 current（未被清空）
    old_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-old'"
    ).fetchone()[0]
    assert old_status == "current"
    # 新 staging → rejected
    new_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-new'"
    ).fetchone()[0]
    assert new_status == "rejected"
    # manifest → aborted
    run_status = con.execute(
        "SELECT status FROM knowledge_build_runs WHERE run_id=?",
        (manifest.run_id,),
    ).fetchone()[0]
    assert run_status == "aborted"
    con.close()


def test_checkpoint_rollback(tmp_path: Path) -> None:
    """回滚：当前 run → aborted，旧 run → current。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    old_manifest = RunManifest.create("extraction", "build-0", {"old": True})
    old_pub = StagingPublisher(old_manifest, db_path=db)
    old_pub.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-old", old_manifest.run_id, status="current")
    con.commit()
    con.close()

    manifest = RunManifest.create("extraction", "build-1", {"new": True})
    publisher = StagingPublisher(manifest, db_path=db)
    publisher.begin_staging()
    con = sqlite3.connect(str(db))
    _insert_unit(con, "u-new", manifest.run_id, status="current")
    con.commit()
    con.close()

    result = publisher.checkpoint_rollback(old_manifest.run_id)
    assert result["rolled_back_to"] == old_manifest.run_id

    con = sqlite3.connect(str(db))
    # 新 unit → rejected
    new_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-new'"
    ).fetchone()[0]
    assert new_status == "rejected"
    # 旧 unit → current
    old_status = con.execute(
        "SELECT status FROM knowledge_units WHERE unit_id='u-old'"
    ).fetchone()[0]
    assert old_status == "current"
    con.close()


def test_table_reconciliation(tmp_path: Path) -> None:
    """reconciliation 报告 staging/current/rejected 计数 + orphan evidence。"""
    db = tmp_path / "test.sqlite"
    _setup_db(db)

    manifest = RunManifest.create("extraction", "build-1", {"a": 1})
    publisher = StagingPublisher(manifest, db_path=db)
    publisher.begin_staging()

    con = sqlite3.connect(str(db))
    _insert_unit(con, "u1", manifest.run_id, status="staging")
    _insert_unit(con, "u2", manifest.run_id, status="staging")
    _insert_unit(con, "u3", manifest.run_id, status="rejected")
    con.execute(
        "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u1','ev1')"
    )
    # orphan evidence
    con.execute(
        "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES ('u-ghost','ev2')"
    )
    con.commit()
    con.close()

    counts = publisher.table_reconciliation()
    assert counts["staging"] == 2
    assert counts["current"] == 0
    assert counts["rejected"] == 1
    assert counts["orphan_evidence"] == 1
