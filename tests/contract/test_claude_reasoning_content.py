"""Phase 62 F11b reasoning-content contracts for the Claude/Qoder DAG adapter.

RED -> GREEN: previously a 'thinking'/'reasoning' block only produced a
2048-char 'summary' while 'content' stayed None -- yet 'fidelity_json' claimed
'content_availability: complete', violating the loss-aware red line (8,930
reasoning events with content=NULL while fidelity claimed complete).

Fix: thinking/reasoning text is now mapped into 'content' (up to a high bound;
truncation is declared via CONTENT_AVAILABILITY=partial and a REDACTED field
disposition). A block with no recoverable text keeps 'content' None but
declares CONTENT_AVAILABILITY=unavailable with an UNAVAILABLE disposition, so a
missing body is never reported as complete.

Each test drives the real capture/adapt seams with a synthetic fixture; never
parser internals.
"""

from __future__ import annotations

import json
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.claude_qoder import (
    adapt as adapt_dag,
)
from personal_knowledge.adapters.conversation_sources.contracts import SourceArtifactSet
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
    FieldDisposition,
    FidelityDimension,
    FidelityLevel,
)

REASONING_CONTENT_LIMIT = 100_000


def _adapt_text(tmp_path: Path, text: str, *, byte_limit: int = 1_000_000):
    src = tmp_path / "reasoning.jsonl"
    src.write_text(text, encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / "capture", relative_path=src.name,
        byte_limit=byte_limit, count_limit=1,
    )
    return adapt_dag(
        "claude", SourceArtifactSet((artifact,)), artifact_root=blob.parent
    )


def _reasoning_record(index: int, block: dict, uuid: str) -> str:
    return json.dumps({
        "type": "assistant", "sessionId": "s", "uuid": uuid,
        "parentUuid": None, "timestamp": "t" + str(index),
        "message": {"content": [block]},
    })


class TestClaudeQoderReasoningContent:
    """F11b: thinking/reasoning text is recoverable through 'content'.

    Missing text is explicit (UNAVAILABLE), never silently complete.
    """

    def test_thinking_block_text_maps_to_content(self, tmp_path):
        body = "Let me think step by step about the pipeline."
        text = "\n".join((
            _reasoning_record(0, {"type": "thinking", "thinking": body}, "r1"),
        )) + "\n"
        result = _adapt_text(tmp_path, text)
        reasoning = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasoning) == 1
        ev = reasoning[0]
        assert ev.content == body
        assert ev.summary == body  # well under the 2048 summary bound
        assert any(
            d.field_name == "reasoning_content"
            and d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.COMPLETE

    def test_reasoning_block_text_maps_to_content(self, tmp_path):
        body = "Final answer reasoning chain."
        text = "\n".join((
            _reasoning_record(0, {"type": "reasoning", "text": body}, "r2"),
        )) + "\n"
        result = _adapt_text(tmp_path, text)
        reasoning = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasoning) == 1
        ev = reasoning[0]
        assert ev.content == body
        assert any(
            d.field_name == "reasoning_content"
            and d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.COMPLETE

    def test_reasoning_text_over_limit_truncated_with_disposition(self, tmp_path):
        body = "x" * (REASONING_CONTENT_LIMIT + 50_000)
        text = "\n".join((
            _reasoning_record(0, {"type": "thinking", "thinking": body}, "r3"),
        )) + "\n"
        result = _adapt_text(tmp_path, text, byte_limit=2_000_000)
        reasoning = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasoning) == 1
        ev = reasoning[0]
        assert ev.content is not None and len(ev.content) == REASONING_CONTENT_LIMIT
        assert ev.content == body[:REASONING_CONTENT_LIMIT]
        assert len(ev.summary) == 2048  # summary stays the bounded synopsis
        assert any(
            d.field_name == "reasoning_content"
            and d.disposition is FieldDisposition.REDACTED
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.PARTIAL

    def test_empty_thinking_block_content_none_and_unavailable(self, tmp_path):
        text = "\n".join((
            _reasoning_record(0, {"type": "thinking"}, "r4"),
        )) + "\n"
        result = _adapt_text(tmp_path, text)
        reasoning = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasoning) == 1
        ev = reasoning[0]
        assert ev.content is None
        assert ev.summary is None
        assert any(
            d.field_name == "reasoning_content"
            and d.disposition is FieldDisposition.UNAVAILABLE
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.UNAVAILABLE

    def test_fidelity_json_never_claims_complete_when_content_missing(self, tmp_path):
        # Mixed stream: a thinking block with text, a reasoning block with text,
        # and an empty thinking block (no recoverable text).
        text = "\n".join((
            _reasoning_record(0, {"type": "thinking", "thinking": "a" * 90}, "r5"),
            _reasoning_record(1, {"type": "reasoning", "text": "b" * 90}, "r6"),
            _reasoning_record(2, {"type": "thinking"}, "r7"),
        )) + "\n"
        result = _adapt_text(tmp_path, text)
        reasoning = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasoning) == 3
        for ev in reasoning:
            fidelity_json = json.dumps(
                ev.fidelity.to_dict(), ensure_ascii=False, sort_keys=True
            )
            parsed = json.loads(fidelity_json)
            if ev.content is None:
                # red line: content absent must never be reported as complete
                assert parsed["content_availability"] == "unavailable"
                assert "content_availability" in parsed
            else:
                assert parsed["content_availability"] in ("complete", "partial")
        # sanity: the mixed stream produces exactly one unavailable + two present
        assert sum(1 for e in reasoning if e.content is None) == 1

    def test_adapter_version_is_1_4_0(self, tmp_path):
        text = "\n".join((
            _reasoning_record(0, {"type": "thinking", "thinking": "x"}, "r8"),
        )) + "\n"
        result = _adapt_text(tmp_path, text)
        assert result.adapter_version == "1.4.0"
