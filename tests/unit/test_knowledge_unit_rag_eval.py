"""P0: evaluate_knowledge_unit_rag 纯函数与报告契约（不连 Chroma/embed）。"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import personal_knowledge.domains.knowledge.evaluate_knowledge_unit_rag as rag  # noqa: E402


def test_percentile_edges() -> None:
    assert rag._percentile([], 50) == 0.0
    assert rag._percentile([10.0], 50) == 10.0
    vals = [1.0, 2.0, 3.0, 4.0, 5.0]
    assert rag._percentile(vals, 50) == 3.0
    assert rag._percentile(vals, 95) == 5.0


def test_match_found_by_id() -> None:
    rank = rag._match_found(
        ids=["a", "gold1", "c"],
        documents=["", "", ""],
        metadatas=[{}, {}, {}],
        gold_refs={"gold1"},
        gold_snippets=[],
    )
    assert rank == 2


def test_match_found_by_source_message_ref() -> None:
    rank = rag._match_found(
        ids=["u1", "u2"],
        documents=["doc1", "doc2"],
        metadatas=[{"source_message_ref": "other"}, {"source_message_ref": "cm|gold"}],
        gold_refs={"cm|gold"},
        gold_snippets=[],
    )
    assert rank == 2


def test_match_found_by_content_snippet() -> None:
    snippet = "这是一段足够长的证据正文用于匹配"  # >=15 chars
    rank = rag._match_found(
        ids=["x"],
        documents=[f"prefix {snippet} suffix"],
        metadatas=[{}],
        gold_refs={"missing-id"},
        gold_snippets=[snippet],
    )
    assert rank == 1


def test_match_found_miss() -> None:
    rank = rag._match_found(
        ids=["a"],
        documents=["nope"],
        metadatas=[{}],
        gold_refs={"gold"},
        gold_snippets=["完全不相关的短文案超过十五字啊啊"],
    )
    assert rank is None


def test_eval_metrics_to_dict_and_format() -> None:
    m = rag.EvalMetrics(
        dataset="hybrid",
        collection="ku_test",
        total_queries=10,
        recall_at_5=0.65,
        mrr_at_5=0.4,
        no_answer_false_positive=0,
        deprecated_secret_hit=0,
        p50_latency_ms=12.0,
        p95_latency_ms=40.0,
        collection_count=30012,
        embedding_model="bge-small-zh-v1.5",
    )
    d = m.to_dict()
    assert d["recall_at_5"] == 0.65
    assert d["deprecated_secret_hit"] == 0
    md = rag._format_report(m)
    assert "Recall@5: 0.65" in md
    assert "deprecated/secret hit: 0" in md
    assert "must be 0" in md


def test_load_eval_dataset_missing_returns_empty(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag, "EVAL_DIR", tmp_path)
    assert rag._load_eval_dataset("frozen-test") == []
    assert rag._load_eval_dataset("dev") == []


def test_load_eval_dataset_reads_jsonl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(rag, "EVAL_DIR", tmp_path)
    path = tmp_path / "frozen_test_queries.private.jsonl"
    rows = [
        {"id": "q1", "query": "shell?", "gold_evidence_refs": ["cm|1"]},
        {"id": "q2", "query": "os?", "gold_evidence_refs": ["cm|2"], "expected_abstain": False},
    ]
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows), encoding="utf-8")
    loaded = rag._load_eval_dataset("frozen-test")
    assert len(loaded) == 2
    assert loaded[0]["id"] == "q1"


def test_run_unknown_dataset_returns_2() -> None:
    assert rag.run("not-a-dataset") == 2


def test_main_help_choices() -> None:
    with pytest.raises(SystemExit) as exc:
        rag.main(["--help"])
    assert exc.value.code == 0


# --- 证据并集匹配（_load_cu_ref_index + candidate 评分路径） ---


def _make_unified_db(path: Path) -> None:
    """构造最小 UNIFIED_DB：cu → 2 个 member unit → 各自 evidence 链接。"""
    con = sqlite3.connect(path)
    con.executescript(
        """
        CREATE TABLE canonical_unit_members(canonical_unit_id TEXT, member_unit_id TEXT);
        CREATE TABLE knowledge_units(unit_id TEXT PRIMARY KEY, source_message_ref TEXT);
        CREATE TABLE knowledge_unit_evidence(unit_id TEXT, evidence_ref TEXT,
            UNIQUE(unit_id, evidence_ref));
        """
    )
    con.executemany(
        "INSERT INTO canonical_unit_members VALUES (?, ?)",
        [("cu|aaa", "u1"), ("cu|aaa", "u2")],
    )
    con.executemany(
        "INSERT INTO knowledge_units VALUES (?, ?)",
        [("u1", "cm|anchor1"), ("u2", "cm|anchor2")],
    )
    con.executemany(
        "INSERT INTO knowledge_unit_evidence VALUES (?, ?)",
        # u2 合法持有两条 evidence ref（salvage 保留原锚点 + quote 所在 ref）
        [("u1", "cm|anchor1"), ("u2", "cm|anchor2"), ("u2", "cm|quote-hit")],
    )
    con.commit()
    con.close()


def test_load_cu_ref_index_unions_member_and_evidence_refs(tmp_path: Path) -> None:
    db = tmp_path / "unified.sqlite"
    _make_unified_db(db)
    index = rag._load_cu_ref_index(db)
    assert index["cu|aaa"] == {"cm|anchor1", "cm|anchor2", "cm|quote-hit"}


def test_load_cu_ref_index_missing_db_returns_empty(tmp_path: Path) -> None:
    assert rag._load_cu_ref_index(tmp_path / "nope.sqlite") == {}


class _FakeColl:
    def __init__(self, ids: list[str], metas: list[dict]) -> None:
        self._ids = ids
        self._metas = metas

    def count(self) -> int:
        return len(self._ids)

    def query(self, **_kwargs) -> dict:
        return {"ids": [self._ids], "metadatas": [self._metas]}


def _run_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    ids: list[str],
    metas: list[dict],
    gold_refs: list[str],
):
    """用 fake collection + 临时 UNIFIED_DB 跑 evaluate_candidate。"""
    monkeypatch.setattr(rag, "EVAL_DIR", tmp_path)
    (tmp_path / "frozen_test_queries.private.jsonl").write_text(
        json.dumps({"id": "q1", "query": "q", "gold_evidence_refs": gold_refs},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    db = tmp_path / "unified.sqlite"
    _make_unified_db(db)
    monkeypatch.setattr(rag, "UNIFIED_DB", db)
    monkeypatch.setattr(rag.local_embed, "verify_model", lambda: (True, "ok", 384))
    monkeypatch.setattr(rag.local_embed, "embed", lambda _t: [0.0] * 384)

    fake_coll = _FakeColl(ids, metas)

    class _FakeClient:
        def get_or_create_collection(self, _name: str):
            return fake_coll

    monkeypatch.setattr(rag, "ChromaClient", _FakeClient)
    return rag.evaluate_candidate("fake_coll")


def test_candidate_hit_via_evidence_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """rid= cu|aaa 在 #1，metadata ref 与 gold 不匹配，但 evidence 并集命中 gold。"""
    m = _run_candidate(
        tmp_path,
        monkeypatch,
        ids=["cu|aaa", "cu|bbb"],
        metas=[{"source_message_ref": "cm|anchor1"}, {"source_message_ref": "cm|other"}],
        gold_refs=["cm|quote-hit"],
    )
    # 旧逻辑（仅 metadata 单 ref）miss；新逻辑经 u2 的第二条 evidence ref 命中
    assert m.per_query[0]["found_rank"] == 1
    assert m.recall_at_5 == 1.0


def test_candidate_hit_via_member_source_ref_union(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """metadata ref 不命中，但 member unit u2 的 source_message_ref 命中 gold。"""
    m = _run_candidate(
        tmp_path,
        monkeypatch,
        ids=["cu|aaa"],
        metas=[{"source_message_ref": "cm|anchor1"}],
        gold_refs=["cm|anchor2"],
    )
    assert m.per_query[0]["found_rank"] == 1


def test_candidate_still_misses_when_no_ref_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """并集路径不误命中：gold 与任何 ref 无关时仍 miss。"""
    m = _run_candidate(
        tmp_path,
        monkeypatch,
        ids=["cu|aaa"],
        metas=[{"source_message_ref": "cm|anchor1"}],
        gold_refs=["cm|unrelated"],
    )
    assert m.per_query[0]["found_rank"] is None
    assert m.recall_at_5 == 0.0


def test_match_found_raw_mode_not_using_union() -> None:
    """raw 回归：_match_found 不接触 cu 索引，cu| rid 与 metadata 无关 ref 时仍 miss。"""
    rank = rag._match_found(
        ids=["cu|aaa"],
        documents=["doc"],
        metadatas=[{"source_message_ref": "cm|anchor1"}],
        gold_refs={"cm|quote-hit"},
        gold_snippets=[],
    )
    assert rank is None


# --- Phase 41-04 Nyquist 用例 9：assistant 轨 eval 集 ---

_USER_TRACK_TYPES = {
    "preference", "habit", "personal_fact",
    "project_decision", "capability", "tool_usage",
}

_ASSISTANT_DATASET_FIELDS = {
    "id", "split", "query", "gold_evidence_refs", "allowed_unit_types",
    "expected_abstain", "expected_conflict", "group", "agent", "started_at",
}


def test_frozen_test_assistant_dataset_loads_20_rows() -> None:
    """真实 eval 文件（integration/evals/knowledge_units/）可被加载且构成合规。"""
    ds = rag._load_eval_dataset("frozen-test-assistant")
    if not ds:
        pytest.skip("frozen_test_assistant.private.jsonl 不存在（数据集文件未随环境提供）")
    assert len(ds) == 20
    for row in ds:
        assert _ASSISTANT_DATASET_FIELDS.issubset(row.keys()), row.get("id")
        assert row["split"] == "frozen_test_assistant"
        # D-01：assistant 3 类型与 user 6 类型零交集
        assert not (set(row["allowed_unit_types"]) & _USER_TRACK_TYPES)
        assert set(row["allowed_unit_types"]) == {
            "solution", "decision_rationale", "technical_conclusion",
        }
        assert row["expected_conflict"] is False
    # 恰好 3 条 expected_abstain（驱动 no_answer_false_positive 指标）
    assert sum(1 for row in ds if row["expected_abstain"] is True) == 3


def test_frozen_test_assistant_gold_refs_exist_in_canonical_db() -> None:
    """gold_evidence_refs 逐条在真实 canonical DB 中存在（integration，缺失环境则 skip）。"""
    from personal_knowledge.core.project_paths import AGENT_CONVERSATIONS_DB

    if not AGENT_CONVERSATIONS_DB.exists():
        pytest.skip("canonical conversations DB 不存在")
    ds = rag._load_eval_dataset("frozen-test-assistant")
    if not ds:
        pytest.skip("frozen_test_assistant.private.jsonl 不存在")
    con = sqlite3.connect(f"file:{AGENT_CONVERSATIONS_DB.resolve().as_posix()}?mode=ro", uri=True)
    try:
        missing = [
            ref
            for row in ds
            for ref in row["gold_evidence_refs"]
            if con.execute(
                "SELECT 1 FROM canonical_messages WHERE canonical_message_id=?", (ref,)
            ).fetchone()
            is None
        ]
    finally:
        con.close()
    assert missing == []


def test_cli_choices_include_frozen_test_assistant(capsys: pytest.CaptureFixture) -> None:
    with pytest.raises(SystemExit) as exc:
        rag.main(["--help"])
    assert exc.value.code == 0
    assert "frozen-test-assistant" in capsys.readouterr().out
