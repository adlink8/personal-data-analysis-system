"""P0: evaluate_knowledge_unit_rag 纯函数与报告契约（不连 Chroma/embed）。"""

from __future__ import annotations

import json
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
