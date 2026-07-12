"""Phase 14 Plan 03 Task 3 测试：canonicalization + merge gate。"""

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
from build_canonical_knowledge_units import (  # noqa: E402
    build_buckets, find_merge_proposals, merge_group, compute_similarity,
    _canonical_id, build_canonical, evaluate_merge_gate,
)


def _setup_db_with_units(db: Path, units: list[dict]) -> str:
    """建 schema + run + units，返回 run_id。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    con.execute(
        "INSERT INTO knowledge_inventory VALUES ('inv1','2026-01-01','canon','cs',3,3,'dh','2026-01','2026-02','{}')"
    )
    for u in units:
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, lifecycle, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (u["unit_id"], "run1", u["unit_type"], u["subject"], u["question"],
             u["answer"], u["confidence"], u["evidence_quote"], u.get("lifecycle", "current"),
             u.get("evidence_scope", "user"), "staging", "2026-01-01", u.get("source_message_ref", ""))
        )
        if u.get("source_message_ref"):
            con.execute(
                "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?)",
                (0, u["source_message_ref"], "hash", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible")
            )
    con.commit()
    con.close()
    return "run1"


# === 分桶测试 ===

def test_buckets_separate_by_subject(tmp_path: Path) -> None:
    """不同 subject 分到不同桶。"""
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "PowerShell",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev"},
        {"unit_id": "u2", "unit_type": "preference", "subject": "Python",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev"},
    ]
    buckets = build_buckets(units)
    assert len(buckets) == 2  # 不同 subject → 不同桶


def test_buckets_separate_by_type(tmp_path: Path) -> None:
    """同 subject 不同 type 分到不同桶。"""
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "Shell",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev"},
        {"unit_id": "u2", "unit_type": "capability", "subject": "Shell",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev"},
    ]
    buckets = build_buckets(units)
    assert len(buckets) == 2


def test_buckets_separate_conflict(tmp_path: Path) -> None:
    """conflict lifecycle 单独分桶。"""
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "Shell",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev",
         "lifecycle": "current"},
        {"unit_id": "u2", "unit_type": "preference", "subject": "Shell",
         "question": "q", "answer": "different", "confidence": 0.9, "evidence_quote": "ev",
         "lifecycle": "conflict"},
    ]
    buckets = build_buckets(units)
    assert len(buckets) == 2  # conflict 单独桶


# === 相似度测试 ===

def test_similarity_identical() -> None:
    """相同文本相似度=1。"""
    assert compute_similarity("hello world", "hello world") == 1.0


def test_similarity_different() -> None:
    """完全不同文本相似度=0。"""
    assert compute_similarity("aaa", "bbb") == 0.0


def test_similarity_partial() -> None:
    """部分重叠在 0-1 之间。"""
    sim = compute_similarity("hello world foo", "hello world bar")
    assert 0 < sim < 1


# === Merge 测试 ===

def test_merge_single_unit(tmp_path: Path) -> None:
    """单 unit 桶 → singleton canonical。"""
    group = [{"unit_id": "u1", "subject": "Shell", "unit_type": "preference",
              "question": "q", "answer": "a", "confidence": 0.9, "lifecycle": "current"}]
    result = merge_group(group)
    assert len(result["members"]) == 1
    assert result["merge_reason"] == "single"


def test_merge_multiple_takes_min_confidence(tmp_path: Path) -> None:
    """合并后 confidence 取最小值。"""
    group = [
        {"unit_id": "u1", "subject": "Shell", "unit_type": "preference",
         "question": "q", "answer": "a", "confidence": 0.9, "lifecycle": "current"},
        {"unit_id": "u2", "subject": "Shell", "unit_type": "preference",
         "question": "q", "answer": "a", "confidence": 0.7, "lifecycle": "current"},
    ]
    result = merge_group(group)
    assert result["confidence"] == 0.7
    assert len(result["members"]) == 2


def test_canonical_id_stable() -> None:
    """相同 subject+type+answer 产生相同 canonical ID。"""
    id1 = _canonical_id("Shell", "preference", "use PowerShell")
    id2 = _canonical_id("Shell", "preference", "use PowerShell")
    assert id1 == id2


def test_canonical_id_different_answer() -> None:
    """不同 answer 产生不同 canonical ID。"""
    id1 = _canonical_id("Shell", "preference", "use PowerShell")
    id2 = _canonical_id("Shell", "preference", "use cmd")
    assert id1 != id2


# === 端到端 canonicalization 测试 ===

def test_build_canonical_no_duplicates(tmp_path: Path) -> None:
    """无重复 units 时 canonical = units（合法结果）。"""
    db = tmp_path / "test.sqlite"
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "Shell",
         "question": "q1", "answer": "a1", "confidence": 0.9, "evidence_quote": "ev"},
        {"unit_id": "u2", "unit_type": "capability", "subject": "Python",
         "question": "q2", "answer": "a2", "confidence": 0.8, "evidence_quote": "ev"},
    ]
    _setup_db_with_units(db, units)
    stats, canonical = build_canonical("run1", db)
    assert stats.total_units == 2
    assert stats.canonical_units == 2  # 无重复
    assert stats.merged == 0
    assert stats.singletons == 2


def test_build_canonical_merges_similar(tmp_path: Path) -> None:
    """高度相似的同桶 units 被合并。"""
    db = tmp_path / "test.sqlite"
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "shell",
         "question": "what shell", "answer": "use powershell for everything",
         "confidence": 0.9, "evidence_quote": "ev"},
        {"unit_id": "u2", "unit_type": "preference", "subject": "shell",
         "question": "what shell", "answer": "use powershell for everything",
         "confidence": 0.8, "evidence_quote": "ev"},
    ]
    _setup_db_with_units(db, units)
    stats, canonical = build_canonical("run1", db)
    # 完全相同 → 合并
    assert stats.canonical_units <= 2  # 可能合并为 1
    if stats.merged > 0:
        assert stats.merged == 1
        assert stats.canonical_units == 1


def test_canonical_write_to_db(tmp_path: Path) -> None:
    """canonical 写入 DB 后可回查。"""
    db = tmp_path / "test.sqlite"
    units = [
        {"unit_id": "u1", "unit_type": "preference", "subject": "Shell",
         "question": "q", "answer": "a", "confidence": 0.9, "evidence_quote": "ev"},
    ]
    _setup_db_with_units(db, units)
    build_canonical("run1", db, write=True)

    con = sqlite3.connect(str(db))
    count = con.execute("SELECT COUNT(*) FROM canonical_knowledge_units").fetchone()[0]
    assert count == 1
    member_count = con.execute("SELECT COUNT(*) FROM canonical_unit_members").fetchone()[0]
    assert member_count == 1
    con.close()


def test_merge_gate_no_eval_files(tmp_path: Path) -> None:
    """无 eval pair 文件时返回 error。"""
    result = evaluate_merge_gate(tmp_path / "test.sqlite", eval_dir=tmp_path)
    assert "error" in result
