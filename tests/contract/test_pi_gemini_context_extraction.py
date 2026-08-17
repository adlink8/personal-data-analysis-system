"""Phase 62-02 / Agent D: Pi & Gemini context extraction (RED -> GREEN).

Asserts that the Pi and Gemini adapters surface the session-context fields
added to the public AdaptedSession contract (cwd, title, model) plus the
usage and compaction affordances:

  - Pi AdaptedSession.title from the conversation record, cwd when present
  - Pi compaction -> COMPACTION_SUMMARY event; COMPACTED_RANGE relation to the
    last event in the compacted range; RETAINED_FROM fallback when the kept
    boundary cannot be located
  - Pi / Gemini USAGE events with machine-parsable token summaries
  - Gemini AdaptedSession.model (top-level or per-message) and title from the
    first user message (first 120 chars)

Fixtures are small synthetic shapes driven through the real capture seam.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import gemini, pi
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
    RelationKind,
)

LONG_TITLE = ("gemini first user prompt about indexing and retrieval design ") * 4


def _capture(tmp_path: Path, *, relative_path: str, text: str, dest: str = "capture"):
    """Write + capture one synthetic artifact and return (artifact, root)."""
    src = tmp_path / Path(relative_path).name
    src.write_text(text, encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / dest, relative_path=relative_path,
        byte_limit=1_000_000, count_limit=10,
    )
    return artifact, blob.parent

class TestPiContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("pi-ctx")
        rows = [
            {"type": "conversation", "id": "pi_s1", "title": "pi session",
             "cwd": "/home/user/project", "git_branch": "main",
             "created_at": "2026-07-01T10:00:00Z"},
            {"type": "user_message", "conversation_id": "pi_s1", "message_id": "m1",
             "content": "pi prompt", "timestamp": "2026-07-01T10:00:01Z",
             "role": "user", "input_tokens": 123, "output_tokens": 0},
            {"type": "assistant_message", "conversation_id": "pi_s1", "message_id": "m2",
             "content": "pi answer", "timestamp": "2026-07-01T10:00:02Z",
             "role": "assistant", "usage": {"input_tokens": 100, "output_tokens": 50}},
            {"type": "compaction", "conversation_id": "pi_s1", "message_id": "m3",
             "summary": "pi compacted", "firstKeptEntryId": "m2", "tokensBefore": 1234,
             "timestamp": "2026-07-01T10:00:03Z"},
        ]
        sep = chr(10)
        text = sep.join(json.dumps(r) for r in rows) + sep
        artifact, root = _capture(tmp, relative_path="pi_session.jsonl", text=text)
        return pi.adapt(SourceArtifactSet((artifact,)), artifact_root=root)

    def test_session_title(self, adapted):
        assert len(adapted.sessions) == 1
        assert adapted.sessions[0].title == "pi session"

    def test_session_cwd(self, adapted):
        assert adapted.sessions[0].cwd == "/home/user/project"

    def test_compaction_summary_event(self, adapted):
        compacts = [e for e in adapted.events if e.kind is EventKind.COMPACTION_SUMMARY]
        assert len(compacts) == 1
        assert "pi compacted" in (compacts[0].summary or "")

    def test_compacted_range_targets_last_compacted_event(self, adapted):
        rels = [r for r in adapted.relations
                if r.relation_kind is RelationKind.COMPACTED_RANGE]
        assert len(rels) == 1
        m1 = next(e for e in adapted.events if e.provenance.native_event_id == "m1")
        assert rels[0].target_event_id == m1.event_id

    def test_usage_events(self, adapted):
        usage = {e.provenance.native_event_id: e.summary or ""
                 for e in adapted.events if e.kind is EventKind.USAGE}
        assert any("input_tokens=123" in s for s in usage.values())
        assert any("input_tokens=100" in s and "output_tokens=50" in s for s in usage.values())
        assert any("tokens_before=1234" in s for s in usage.values())

    def test_retained_from_fallback_when_boundary_missing(self, tmp_path):
        rows = [
            {"type": "conversation", "id": "pi_s2", "created_at": "t0"},
            {"type": "user_message", "conversation_id": "pi_s2", "message_id": "p1",
             "content": "u", "timestamp": "t1"},
            {"type": "compaction", "conversation_id": "pi_s2", "message_id": "c1",
             "summary": "s", "firstKeptEntryId": "no-such-id", "tokensBefore": 5,
             "timestamp": "t2"},
        ]
        sep = chr(10)
        text = sep.join(json.dumps(r) for r in rows) + sep
        artifact, root = _capture(tmp_path, relative_path="pi_fallback.jsonl", text=text)
        result = pi.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        retained = [r for r in result.relations
                    if r.relation_kind is RelationKind.RETAINED_FROM]
        assert len(retained) == 1

    def test_session_started_at_from_conversation_created_at(self, adapted):
        assert len(adapted.sessions) == 1
        # conversation record carries created_at = session start
        assert adapted.sessions[0].started_at == "2026-07-01T10:00:00Z"

    def test_session_ended_at_last_record_timestamp(self, adapted):
        # last record (compaction) timestamp is the session end
        assert adapted.sessions[0].ended_at == "2026-07-01T10:00:03Z"

    def test_session_timestamps_prefer_session_timestamp(self, tmp_path):
        rows = [
            {"type": "session", "id": "pi_ts", "timestamp": "2026-07-01T09:00:00Z",
             "cwd": "/x"},
            {"type": "message", "id": "m1", "parentId": None,
             "timestamp": "2026-07-01T09:00:01Z",
             "message": {"role": "user", "content": "u"}},
            {"type": "message", "id": "m2", "parentId": "m1",
             "timestamp": "2026-07-01T09:00:02Z",
             "message": {"role": "assistant", "content": "a"}},
        ]
        text = chr(10).join(json.dumps(r) for r in rows) + chr(10)
        artifact, root = _capture(tmp_path, relative_path="pi_ts.jsonl", text=text)
        result = pi.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        assert result.sessions[0].started_at == "2026-07-01T09:00:00Z"
        assert result.sessions[0].ended_at == "2026-07-01T09:00:02Z"



class TestPiModelAndClassification:
    """P1-2: real-wire classification + session context for Pi.

    Exercises the observed live format: session records carrying cwd,
    model_change / thinking_level_change typed records, and message records
    whose assistant content carries thinking/toolCall blocks plus a nested
    message.usage object, with toolResult role messages as the bulk of the
    stream. These previously collapsed into unknown_native (42%+).
    """
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("pi-wire")
        rows = [
            {"type": "session", "id": "pi_w1", "timestamp": "t0",
             "cwd": "/workspace/app"},
            {"type": "model_change", "id": "mc1", "parentId": None,
             "timestamp": "t1", "provider": "opencode-go",
             "modelId": "deepseek-v4-flash"},
            {"type": "thinking_level_change", "id": "tl1", "parentId": "mc1",
             "timestamp": "t2", "thinkingLevel": "high"},
            {"type": "message", "id": "m1", "parentId": "tl1", "timestamp": "t3",
             "message": {"role": "user", "content": [
                 {"type": "text", "text": "index the project"}],
                 "timestamp": 1711000000000}},
            {"type": "message", "id": "m2", "parentId": "m1", "timestamp": "t4",
             "message": {"role": "assistant",
                 "content": [
                     {"type": "thinking", "thinking": "plan the lookup steps",
                      "thinkingSignature": "reasoning_content"},
                     {"type": "text", "text": "running the search"},
                     {"type": "toolCall", "id": "call_01", "name": "bash",
                      "arguments": {"command": "ls"}},
                 ],
                 "model": "deepseek-v4-flash", "stopReason": "tool_use",
                 "usage": {"input": 120, "output": 40, "cacheRead": 8,
                           "cacheWrite": 0}, "timestamp": 1711000001000}},
            {"type": "message", "id": "m3", "parentId": "m2", "timestamp": "t5",
             "message": {"role": "toolResult", "toolName": "bash",
                 "toolCallId": "call_01",
                 "content": [{"type": "text", "text": "src\n"}],
                 "timestamp": 1711000002000}},
            {"type": "message", "id": "m4", "parentId": "m2", "timestamp": "t6",
             "message": {"role": "assistant",
                 "content": [{"type": "text", "text": "done"}],
                 "stopReason": "end_turn",
                 "usage": {"input": 60, "output": 25}, "timestamp": 1711000003000}},
        ]
        text = chr(10).join(json.dumps(r) for r in rows) + chr(10)
        artifact, root = _capture(tmp, relative_path="pi_wire.jsonl", text=text)
        return pi.adapt(SourceArtifactSet((artifact,)), artifact_root=root)

    def test_no_unknown_native_on_real_wire(self, adapted):
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in adapted.events)

    def test_session_cwd_from_session_record(self, adapted):
        assert len(adapted.sessions) == 1
        assert adapted.sessions[0].cwd == "/workspace/app"

    def test_session_model_from_model_change(self, adapted):
        assert adapted.sessions[0].model == "deepseek-v4-flash"

    def test_session_stop_reason_from_last_assistant(self, adapted):
        assert adapted.sessions[0].stop_reason == "end_turn"

    def test_session_title_derived_from_first_user_message(self, adapted):
        assert adapted.sessions[0].title is not None
        assert "index the project" in adapted.sessions[0].title

    def test_model_change_event_carries_model_id_summary(self, adapted):
        model_evts = [e for e in adapted.events
                      if e.kind is EventKind.SESSION_LIFECYCLE
                      and (e.summary or "") == "deepseek-v4-flash"]
        assert len(model_evts) == 1

    def test_thinking_level_change_classified_as_reasoning(self, adapted):
        reasons = [e for e in adapted.events if e.kind is EventKind.REASONING]
        assert any((e.summary or "") == "high" for e in reasons)

    def test_assistant_thinking_block_is_reasoning_event(self, adapted):
        thinking = [e for e in adapted.events if e.kind is EventKind.REASONING
                   and e.summary and "plan the lookup" in e.summary]
        assert len(thinking) == 1

    def test_tool_call_block_is_tool_call_event(self, adapted):
        calls = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        assert len(calls) == 1
        assert "bash" in (calls[0].summary or "")

    def test_tool_result_role_is_tool_result_event(self, adapted):
        results = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(results) == 1
        assert "bash" in (results[0].summary or "")

    def test_real_usage_uses_standard_keys(self, adapted):
        summaries = [e.summary or "" for e in adapted.events
                     if e.kind is EventKind.USAGE]
        assert any("input_tokens=120" in s and "output_tokens=40" in s
                   and "cache_read=8" in s and "cache_write=0" in s for s in summaries)
        # The Pi message.usage input/output keys are normalized away.
        assert all("input=" not in s and "output=" not in s for s in summaries)

    def test_all_events_have_unique_ids(self, adapted):
        ids = [e.event_id for e in adapted.events]
        assert len(ids) == len(set(ids))

    def test_all_relations_resolve(self, adapted):
        known = {e.event_id for e in adapted.events}
        for rel in adapted.relations:
            assert rel.source_event_id in known
            assert rel.target_event_id in known

    def test_tokens_before_only_without_input_output_pair(self, tmp_path):
        rows = [
            {"type": "session", "id": "pi_w2", "timestamp": "t0", "cwd": "/x"},
            {"type": "message", "id": "b1", "parentId": None, "timestamp": "t1",
             "message": {"role": "user", "content": "u", "timestamp": 1}},
            {"type": "compaction", "id": "cp1", "parentId": "b1",
             "timestamp": "t2", "summary": "s", "firstKeptEntryId": "b1",
             "tokensBefore": 4321},
        ]
        text = chr(10).join(json.dumps(r) for r in rows) + chr(10)
        artifact, root = _capture(tmp_path, relative_path="pi_tokens.jsonl", text=text)
        result = pi.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        summaries = [e.summary or "" for e in result.events
                     if e.kind is EventKind.USAGE]
        assert any("tokens_before=4321" in s and "input_tokens=" not in s
                   and "output_tokens=" not in s for s in summaries)

class TestGeminiContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("gem-ctx")
        doc = {
            "session_id": "gm_s1",
            "created_at": "2026-07-01T10:00:00Z",
            "messages": [
                {"role": "user", "content": LONG_TITLE,
                 "timestamp": "2026-07-01T10:00:00Z",
                 "usage": {"input_tokens": 10, "output_tokens": 0}},
                {"role": "model", "content": "gemini answer",
                 "timestamp": "2026-07-01T10:00:01Z",
                 "model": "gemini-2.5-flash",
                 "usage": {"input_tokens": 50, "output_tokens": 25}},
            ],
        }
        text = json.dumps(doc)
        artifact, root = _capture(tmp, relative_path="gemini_session.json", text=text)
        return gemini.adapt(SourceArtifactSet((artifact,)), artifact_root=root)

    def test_session_model_from_message(self, adapted):
        assert len(adapted.sessions) == 1
        assert adapted.sessions[0].model == "gemini-2.5-flash"

    def test_session_title_truncated_to_120(self, adapted):
        title = adapted.sessions[0].title
        assert title is not None
        assert len(title) <= 120
        assert title == LONG_TITLE[:120]

    def test_usage_events(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        assert len(usage) == 2
        summaries = sorted(e.summary or "" for e in usage)
        assert any("input_tokens=50" in s and "output_tokens=25" in s for s in summaries)
        assert any("input_tokens=10" in s for s in summaries)

    def test_top_level_model_takes_precedence(self, tmp_path):
        doc = {
            "session_id": "gm_s2",
            "model": "gemini-2.5-pro",
            "messages": [
                {"role": "user", "content": "u", "timestamp": "t0"},
                {"role": "model", "content": "a", "timestamp": "t1",
                 "model": "gemini-2.5-flash"},
            ],
        }
        artifact, root = _capture(tmp_path, relative_path="gemini_toplevel.json",
                                  text=json.dumps(doc))
        result = gemini.adapt(SourceArtifactSet((artifact,)), artifact_root=root)
        assert result.sessions[0].model == "gemini-2.5-pro"

    def test_all_relations_valid(self, adapted):
        known = {e.event_id for e in adapted.events}
        for rel in adapted.relations:
            assert rel.source_event_id in known
            assert rel.target_event_id in known
