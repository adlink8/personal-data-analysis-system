"""Phase 17-03: deterministic answer evaluation."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPTS = _ROOT / "integration" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from personal_knowledge.evaluation.answer_eval import (  # noqa: E402
    generate_answer,
    score_answer,
    cache_key,
    build_prompt,
)
from personal_knowledge.evaluation.knowledge_eval_metrics import RankedHit  # noqa: E402


def test_deterministic_answer_replay() -> None:
    ctx = [RankedHit(id="u1", snippet="用户偏好 PowerShell 作为日常 shell。", subject="shell")]
    a1 = generate_answer("用户用什么 shell？", ctx)
    a2 = generate_answer("用户用什么 shell？", ctx)
    assert a1.cache_key == a2.cache_key
    assert a1.answer == a2.answer
    assert a1.cited_ids == ["u1"]

    # cache replay
    cache = {a1.cache_key: "cached reply [[u1]]"}
    a3 = generate_answer("用户用什么 shell？", ctx, cache=cache)
    assert a3.answer.startswith("cached")
    assert a3.meta.get("replay") is True


def test_deterministic_citation_and_abstain() -> None:
    ctx = [RankedHit(id="u1", snippet="fact", subject="s")]
    ar = generate_answer("q", ctx)
    sc = score_answer(ar, ranked_ids=["u1"], gold_refs=["u1"])
    assert sc.citation_resolvable == 1.0
    assert sc.citation_precision == 1.0

    # out-of-range citation
    ar.cited_ids = ["not-in-ranked"]
    ar.answer = "x [[not-in-ranked]]"
    sc2 = score_answer(ar, ranked_ids=["u1"])
    assert sc2.citation_resolvable == 0.0

    ar_abs = generate_answer("secret?", [], expected_abstain=True)
    assert ar_abs.abstained is True
    sc3 = score_answer(ar_abs, ranked_ids=[], expected_abstain=True)
    assert sc3.abstain_correct is True


def test_deterministic_prompt_stable() -> None:
    ctx = [RankedHit(id="a", snippet="s", subject="t")]
    p1 = build_prompt("q", ctx)
    p2 = build_prompt("q", ctx)
    assert p1 == p2
    assert cache_key(p1, "m", "v") == cache_key(p2, "m", "v")
