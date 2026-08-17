"""Phase 62 v2 F11a: Codex reasoning content + honest content fidelity.

RED to GREEN for the codex adapter reasoning branches (truthful-declaration
red line): the audit found 37,135 codex reasoning events with content=NULL
(summary also NULL) while fidelity_json still claimed
content_availability=complete. Real Codex reasoning records come in three
native shapes:

  (a) {"type": "reasoning", "text": "..."}
  (b) {"type": "reasoning", "encrypted_content": "...", "summary": []}
  (c) {"type": "reasoning", "content": ..., "encrypted_content": ..., "summary": ...}

Contract:

  - plaintext (payload.text / payload.content, string or content-block
    list) is carried as event content, capped at _CONTENT_CAP; over-cap
    content is truncated with a REDACTED field disposition and
    CONTENT_AVAILABILITY=partial;
  - encrypted-only reasoning keeps content=None and truthfully declares
    CONTENT_AVAILABILITY=unavailable with an encrypted_content UNAVAILABLE
    field disposition;
  - mixed shapes take the plaintext part (content preferred over text);
  - summary keeps the existing behavior;
  - no reasoning event with content=None may ever claim complete content
    availability.

Fixtures are synthetic real-shape records (fields nested under payload) so
the contract is exercised against the wire shape Codex writes.
"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

from personal_knowledge.adapters.conversation_sources import codex
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
    FidelityDimension,
    FidelityLevel,
    FieldDisposition,
)


def _adapted(tmp_path: Path, rows: list[dict]):
    """Write synthetic real-shape rows and adapt them through the seam."""
    src = tmp_path / "session.jsonl"
    text = "\n".join(json.dumps(row) for row in rows) + "\n"
    src.write_text(text, encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / "capture", relative_path=src.name,
        byte_limit=1_000_000, count_limit=1,
    )
    assert codex.detect(artifact, artifact_root=blob.parent)
    return codex.adapt(
        SourceArtifactSet(artifacts=(artifact,)), artifact_root=blob.parent
    )


_META = {
    "type": "session_meta",
    "payload": {
        "id": "sess_reason_01",
        "timestamp": "2026-07-01T10:00:00Z",
    },
}


_CAP = 100_000


def _reasons(adapted):
    return [e for e in adapted.events if e.kind is EventKind.REASONING]


class TestCodexReasoningContentFidelity:
    """F11a: reasoning events carry plaintext content when readable and
    declare CONTENT_AVAILABILITY truthfully; encrypted-only reasoning is
    never presented as complete."""

    def test_plaintext_text_maps_to_content(self, tmp_path):
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_plain",
                "text": "thinking step one: check the docs",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "thinking step one: check the docs"
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE
        assert reasons[0].fidelity.is_complete()

    def test_plaintext_content_block_list_maps_to_content(self, tmp_path):
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_blocks",
                "content": [
                    {"type": "input_text", "text": "first"},
                    {"type": "input_text", "text": "second"},
                ],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "first second"

    def test_agent_reasoning_event_msg_text_maps_to_content(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z", "type": "agent_reasoning",
                "turn_id": "019f0000-0000-0000-0000-000000000001",
                "text": "**Identifying missing user habit memory**",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "**Identifying missing user habit memory**"
        # summary keeps the existing bounded fallback behavior.
        assert (reasons[0].summary or "").startswith("**Identifying")

    def test_reasoning_event_msg_hint_text_maps_to_content(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z", "type": "reasoning",
                "turn_id": "019f0000-0000-0000-0000-000000000002",
                "text": "plan the refactor",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "plan the refactor"

    def test_summary_keeps_existing_truncation_behavior(self, tmp_path):
        text = "long " * 1000  # 5000 chars > the 2048 summary cap
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z", "type": "agent_reasoning",
                "text": text,
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].summary == text[:2048]
        # content is under the cap so it stays complete (no REDACTED record).
        assert reasons[0].content == text
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE

    def test_plaintext_over_cap_truncates_with_redacted_partial(self, tmp_path):
        big = "x" * (_CAP + 10)
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_big", "text": big,
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert len(reasons[0].content or "") == _CAP
        assert reasons[0].content == big[:_CAP]
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.PARTIAL
        assert not reasons[0].fidelity.is_complete()
        redacted = [d for d in reasons[0].field_dispositions
                    if d.disposition is FieldDisposition.REDACTED]
        assert len(redacted) == 1
        assert redacted[0].field_name == "text"
        assert "truncated" in redacted[0].reason

    def test_exact_cap_plaintext_is_complete_not_redacted(self, tmp_path):
        exact = "y" * _CAP
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_exact", "text": exact,
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == exact
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE
        assert not any(d.disposition is FieldDisposition.REDACTED
                       for d in reasons[0].field_dispositions)

    def test_encrypted_only_response_item_content_unavailable(self, tmp_path):
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_enc",
                "encrypted_content": "0x1234abcd==",
                "summary": [],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content is None
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.UNAVAILABLE
        unavailable = [d for d in reasons[0].field_dispositions
                       if d.field_name == "encrypted_content"
                       and d.disposition is FieldDisposition.UNAVAILABLE]
        assert len(unavailable) == 1

    def test_encrypted_only_event_msg_reasoning_content_unavailable(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z", "type": "reasoning",
                "turn_id": "019f0000-0000-0000-0000-000000000003",
                "encrypted_content": "0xdeadbeef==",
                "summary": [],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content is None
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.UNAVAILABLE
        assert any(d.disposition is FieldDisposition.UNAVAILABLE
                   for d in reasons[0].field_dispositions)

    def test_mixed_shape_takes_plaintext_content_first(self, tmp_path):
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_mix",
                "content": [{"type": "input_text", "text": "readable plan"}],
                "encrypted_content": "0x1234==",
                "summary": [{"type": "summary_text", "text": "mix"}],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "readable plan"
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE

    def test_mixed_shape_null_content_falls_back_to_text(self, tmp_path):
        rows = [_META, {
            "type": "response_item",
            "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_mix2",
                "content": None, "text": "text part",
                "encrypted_content": "0x1234==",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 1
        assert reasons[0].content == "text part"
        assert reasons[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE

    def test_no_content_none_event_claims_complete(self, tmp_path):
        # the audit red line: every reasoning event with content=None must
        # never claim content_availability=complete, and encrypted-only
        # records are declared unavailable instead.
        rows = [_META,
            {"type": "response_item", "payload": {
                "timestamp": "2026-07-01T10:01:00Z",
                "type": "reasoning", "id": "rs_enc2",
                "encrypted_content": "0xabc==", "summary": []}},
            {"type": "event_msg", "payload": {
                "timestamp": "2026-07-01T10:02:00Z", "type": "agent_reasoning",
                "turn_id": "019f0000-0000-0000-0000-000000000004",
                "encrypted_content": "0xdef==", "summary": []}},
        ]
        adapted = _adapted(tmp_path, rows)
        reasons = _reasons(adapted)
        assert len(reasons) == 2
        for ev in reasons:
            assert ev.content is None
            assert not ev.fidelity.is_complete()
            assert ev.fidelity.level(
                FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.UNAVAILABLE

    def test_adapter_version_bumped_to_1_5_0(self):
        assert codex.ADAPTER_VERSION == "1.5.0"
