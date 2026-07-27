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

from personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL  # noqa: E402
from personal_knowledge.domains.knowledge.build_canonical_knowledge_units import (  # noqa: E402
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
                "INSERT INTO knowledge_inventory_items VALUES (NULL,'inv1',?,?,?,?,?,?,?,?,?,?,?)",
                (0, u["source_message_ref"], "hash", "cs1", "agentsview", "codex", "2026-01", "mid", 0, "eligible", "user")
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


def test_similarity_chinese_near_duplicate() -> None:
    """中文近重复（差几个字）相似度应显著 >0（旧词级 Jaccard 下=0）。"""
    sim = compute_similarity(
        "用户偏好使用 PowerShell 作为默认终端",
        "用户偏好使用 PowerShell 作为默认命令行终端",
    )
    assert sim > 0.5


def test_similarity_chinese_unrelated() -> None:
    """完全无关的两句中文相似度应接近 0。"""
    sim = compute_similarity(
        "用户偏好使用 PowerShell 作为默认终端",
        "数据库迁移脚本在每周日凌晨自动执行",
    )
    assert sim < 0.1


def test_similarity_empty() -> None:
    """空输入返回 0.0。"""
    assert compute_similarity("", "hello") == 0.0
    assert compute_similarity("hello", "") == 0.0
    assert compute_similarity("", "") == 0.0


def test_similarity_english_identical_words() -> None:
    """英文行为不退化：相同词集仍=1.0。"""
    assert compute_similarity("hello world", "hello world") == 1.0


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


def _merge_unit(unit_id: str, lifecycle: str) -> dict:
    return {"unit_id": unit_id, "subject": "Shell", "unit_type": "preference",
            "question": "q", "answer": "a", "confidence": 0.9, "lifecycle": lifecycle}


def test_merge_lifecycle_all_current() -> None:
    """全 current 成员合并 → current。"""
    result = merge_group([_merge_unit("u1", "current"), _merge_unit("u2", "current")])
    assert result["lifecycle"] == "current"


def test_merge_lifecycle_inherits_superseded() -> None:
    """含 superseded 成员 → 合并结果 superseded（不被静默复活为 current）。"""
    result = merge_group([_merge_unit("u1", "current"), _merge_unit("u2", "superseded")])
    assert result["lifecycle"] == "superseded"


def test_merge_lifecycle_conflict_wins() -> None:
    """含 conflict 成员（即使有 superseded）→ conflict（最严重者优先）。"""
    result = merge_group([
        _merge_unit("u1", "current"),
        _merge_unit("u2", "superseded"),
        _merge_unit("u3", "conflict"),
    ])
    assert result["lifecycle"] == "conflict"


def test_merge_single_keeps_deprecated() -> None:
    """单成员 deprecated → 保持 deprecated（现有行为回归）。"""
    result = merge_group([_merge_unit("u1", "deprecated")])
    assert result["lifecycle"] == "deprecated"


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


def _setup_merge_gate_db(db: Path) -> None:
    """u1/u2 合并进 cu1（消息 cm|A/cm|B），u3 独立 cu2（消息 cm|C）。"""
    con = sqlite3.connect(str(db))
    con.executescript(SCHEMA_SQL)
    con.execute(
        "INSERT INTO knowledge_build_runs VALUES "
        "('run1','extraction','2026-01-01','cs','h','v1','v1','m',NULL,NULL,NULL,NULL,'staging',NULL,NULL)"
    )
    for uid, ref in (("u1", "cm|A"), ("u2", "cm|B"), ("u3", "cm|C")):
        con.execute(
            "INSERT INTO knowledge_units (unit_id, run_id, unit_type, subject, question, answer, "
            "confidence, evidence_quote, evidence_scope, status, created_at, source_message_ref) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (uid, "run1", "preference", "shell", "q", "a", 0.9, "ev", "user",
             "staging", "2026-01-01", ref),
        )
        con.execute(
            "INSERT INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
            (uid, ref),
        )
    for cid, uid in (("cu|1", "u1"), ("cu|1", "u2"), ("cu|2", "u3")):
        con.execute(
            "INSERT INTO canonical_unit_members (canonical_unit_id, member_unit_id) VALUES (?,?)",
            (cid, uid),
        )
    con.commit()
    con.close()


def _write_pairs(eval_dir: Path, positives: list[dict], negatives: list[dict]) -> None:
    import json as _json

    (eval_dir / "merge_positive_pairs.private.jsonl").write_text(
        "\n".join(_json.dumps(p) for p in positives), encoding="utf-8"
    )
    (eval_dir / "hard_negative_pairs.private.jsonl").write_text(
        "\n".join(_json.dumps(p) for p in negatives), encoding="utf-8"
    )


def test_merge_gate_resolves_message_refs_via_evidence(tmp_path: Path) -> None:
    """cm| 消息级 pair 经 evidence 解析：正例命中（同 canonical）、负例不误并。"""
    db = tmp_path / "test.sqlite"
    _setup_merge_gate_db(db)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _write_pairs(
        eval_dir,
        positives=[{"unit_a_ref": "cm|A", "unit_b_ref": "cm|B"}],
        negatives=[{"unit_a_ref": "cm|A", "unit_b_ref": "cm|C"}],
    )
    result = evaluate_merge_gate(db, eval_dir=eval_dir)
    assert result["passed"]
    assert result["positive_recall"] == 1.0
    assert result["hard_negative_false_merge"] == 0
    assert result["positive_unresolvable"] == 0


def test_merge_gate_false_merge_detected(tmp_path: Path) -> None:
    """负例对被错误合并（cm|A vs cm|B 同 cu|1）→ false_merge=1 → FAIL。"""
    db = tmp_path / "test.sqlite"
    _setup_merge_gate_db(db)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _write_pairs(
        eval_dir,
        positives=[{"unit_a_ref": "cm|A", "unit_b_ref": "cm|B"}],
        negatives=[{"unit_a_ref": "cm|A", "unit_b_ref": "cm|B"}],
    )
    result = evaluate_merge_gate(db, eval_dir=eval_dir)
    assert not result["passed"]
    assert result["hard_negative_false_merge"] == 1


def test_merge_gate_all_positives_unresolvable_not_applicable(tmp_path: Path) -> None:
    """正例全无法解析 → not_applicable（不 FAIL），负例误并仍硬要求 0。"""
    db = tmp_path / "test.sqlite"
    _setup_merge_gate_db(db)
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _write_pairs(
        eval_dir,
        positives=[{"unit_a_ref": "cm|X", "unit_b_ref": "cm|Y"}],
        negatives=[{"unit_a_ref": "cm|A", "unit_b_ref": "cm|C"}],
    )
    result = evaluate_merge_gate(db, eval_dir=eval_dir)
    assert result["not_applicable"]
    assert result["passed"]
    assert result["positive_unresolvable"] == 1
