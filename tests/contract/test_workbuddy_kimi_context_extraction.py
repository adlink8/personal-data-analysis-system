"""Phase 62-02 / Agent C: Workbuddy/Kimi context extraction (RED → GREEN).

Asserts that the Workbuddy and Kimi adapters surface the session-context
fields added to the public AdaptedSession contract (cwd, title) plus the
subagent and usage affordances:

  - cwd  restored from the project dir name (c-Users-li-Desktop-X → C:\\Users\\li\\Desktop\\X)
  - title from the first user message (first 120 chars)
  - SUBAGENT_BOUNDARY events + SUBAGENT relations when subagents/agent-*.jsonl
    files are present
  - USAGE events with machine-parsable token summaries

Fixtures are small synthetic shapes driven through the real capture seam.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources import workbuddy_kimi
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
    RelationKind,
)


def _capture_one(tmp_path: Path, *, relative_path: str, rows, dest: str = "capture"):
    """Write + capture a single synthetic JSONL and return (artifact, root)."""
    src = tmp_path / Path(relative_path).name
    src.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    artifact, blob = capture_file(
        src, tmp_path / dest, relative_path=relative_path,
        byte_limit=1_000_000, count_limit=10,
    )
    return artifact, blob.parent


def _project_path(name: str, filename: str) -> str:
    return f"projects/{name}/{filename}"


def _workbuddy_rows(*, long: bool = False) -> list[dict]:
    title = "set up the novel mind index and start the background worker"
    if long:
        title = "set up the novel mind index and start the background worker " * 6
    rows = [
        {"type": "message", "session_id": "wb_s1", "message_id": "m1", "role": "user",
         "content": title, "timestamp": "2026-07-01T10:00:00Z"},
        {"type": "message", "session_id": "wb_s1", "message_id": "m2", "role": "assistant",
         "content": "ok", "timestamp": "2026-07-01T10:00:01Z"},
        {"type": "function_call", "session_id": "wb_s1", "message_id": "m3", "role": "assistant",
         "name": "bash", "arguments": "ls", "call_id": "wb_call_1",
         "timestamp": "2026-07-01T10:00:02Z"},
        {"type": "function_call_result", "session_id": "wb_s1", "message_id": "m4",
         "role": "function", "call_id": "wb_call_1", "result": "ok",
         "input_tokens": 1234, "output_tokens": 456,
         "cache_read": 6, "cache_write": 7, "timestamp": "2026-07-01T10:00:03Z"},
    ]
    return rows


def _subagent_rows(name: str) -> list[dict]:
    return [
        {"type": "message", "session_id": "sub-" + name, "message_id": "s1",
         "role": "user", "content": "subagent prompt", "timestamp": "2026-07-01T10:00:00Z"},
        {"type": "message", "session_id": "sub-" + name, "message_id": "s2",
         "role": "assistant", "content": "subagent done", "timestamp": "2026-07-01T10:00:01Z"},
    ]


class TestWorkbuddyContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("wb-ctx")
        main_artifact, root = _capture_one(
            tmp, relative_path=_project_path("c-Users-li-Desktop-project", "abc123.jsonl"),
            rows=_workbuddy_rows(long=True),
        )
        sub_a, _r = _capture_one(
            tmp, relative_path=_project_path(
                "c-Users-li-Desktop-novel-mind", "subagents/agent-research.jsonl"),
            rows=_subagent_rows("research"),
        )
        sub_b, _r = _capture_one(
            tmp, relative_path=_project_path(
                "c-Users-li-Desktop-novel-mind", "subagents/agent-writer.jsonl"),
            rows=_subagent_rows("writer"),
        )
        artifact_set = SourceArtifactSet(artifacts=(main_artifact, sub_a, sub_b))
        return workbuddy_kimi.adapt("workbuddy", artifact_set, artifact_root=root)

    def test_cwd_restored_from_project_dir(self, adapted):
        assert len(adapted.sessions) == 1
        assert adapted.sessions[0].cwd == r"C:\Users\li\Desktop\project"

    def test_title_from_first_user_message(self, adapted):
        session = adapted.sessions[0]
        assert session.title is not None
        assert len(session.title) <= 120
        assert session.title.startswith("set up the novel mind index")

    # ---- P2-1: title must be the first REAL user message, not system scaffolding ----
    def test_title_skips_system_placeholder_user_message(self, tmp_path):
        # the first user record is the plugin/AGENTS template; the title must
        # come from the next real user message instead.
        rows = [
            {"type": "message", "session_id": "wb_p1", "message_id": "ms1",
             "role": "user",
             "content": "<recommended_plugins>agents scaffold",
             "timestamp": "2026-07-01T10:00:00Z"},
            {"type": "message", "session_id": "wb_p1", "message_id": "ms2",
             "role": "user",
             "content": "Now actually fix the report rendering",
             "timestamp": "2026-07-01T10:00:01Z"},
            {"type": "message", "session_id": "wb_p1", "message_id": "ms3",
             "role": "assistant", "content": "ok",
             "timestamp": "2026-07-01T10:00:02Z"},
        ]
        artifact, root = _capture_one(
            tmp_path, relative_path=_project_path("c-Users-li-Desktop-project", "sess.jsonl"),
            rows=rows,
        )
        result = workbuddy_kimi.adapt(
            "workbuddy", SourceArtifactSet((artifact,)), artifact_root=root)
        session = result.sessions[0]
        assert session.title is not None
        assert session.title.startswith("Now actually fix the report rendering")
        assert len(session.title) <= 120
        assert "recommended_plugins" not in session.title

    def test_title_none_when_all_user_messages_are_system(self, tmp_path):
        rows = [
            {"type": "message", "session_id": "wb_p2", "message_id": "ns1",
             "role": "user",
             "content": "instructions for the AGENTS files here",
             "timestamp": "2026-07-01T10:00:00Z"},
            {"type": "message", "session_id": "wb_p2", "message_id": "ns2",
             "role": "assistant", "content": "ok",
             "timestamp": "2026-07-01T10:00:01Z"},
        ]
        artifact, root = _capture_one(
            tmp_path, relative_path=_project_path("c-Users-li-Desktop-project", "s2.jsonl"),
            rows=rows,
        )
        result = workbuddy_kimi.adapt(
            "workbuddy", SourceArtifactSet((artifact,)), artifact_root=root)
        assert result.sessions[0].title is None

    def test_subagent_boundary_events(self, adapted):
        sub = [e for e in adapted.events if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert len(sub) == 2
        summaries = sorted(e.summary or "" for e in sub)
        assert "agent-research.jsonl" in summaries
        assert "agent-writer.jsonl" in summaries

    def test_subagent_relations(self, adapted):
        rels = [r for r in adapted.relations if r.relation_kind is RelationKind.SUBAGENT]
        assert len(rels) == 2
        parent_lifecycle = next(
            e.event_id for e in adapted.events
            if e.kind is EventKind.SESSION_LIFECYCLE
            and e.provenance.native_session_id == "wb_s1"
        )
        for rel in rels:
            assert rel.target_event_id == parent_lifecycle
        # every subagent relation points at a child session_lifecycle source
        child_lifecycles = {
            e.event_id for e in adapted.events
            if e.kind is EventKind.SESSION_LIFECYCLE
        }
        for rel in rels:
            assert rel.source_event_id in child_lifecycles

    def test_usage_event_tokens(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        s = usage[0].summary or ""
        assert "input_tokens=1234" in s
        assert "output_tokens=456" in s

    def test_all_relations_valid(self, adapted):
        known = {e.event_id for e in adapted.events}
        for rel in adapted.relations:
            assert rel.source_event_id in known
            assert rel.target_event_id in known

    def test_replay_digest_stable(self, tmp_path):
        main_artifact, root = _capture_one(
            tmp_path, relative_path=_project_path("c-Users-li-Desktop-project", "abc123.jsonl"),
            rows=_workbuddy_rows(),
        )
        sub_a, _r = _capture_one(
            tmp_path, relative_path=_project_path(
                "c-Users-li-Desktop-novel-mind", "subagents/agent-research.jsonl"),
            rows=_subagent_rows("research"),
        )
        artifact_set = SourceArtifactSet(artifacts=(main_artifact, sub_a))
        first = workbuddy_kimi.adapt("workbuddy", artifact_set, artifact_root=root)
        second = workbuddy_kimi.adapt("workbuddy", artifact_set, artifact_root=root)
        assert first.dataset_digest == second.dataset_digest


class TestWorkbuddyUsageAndSessionFields:
    """RED for P1-1: real Workbuddy puts token counts in message.usage /
    providerData.usage (both snake_case and camelCase), and session.start
    must come from the first record's timestamp."""

    def _adapt(self, tmp_path, rows):
        artifact, root = _capture_one(
            tmp_path, relative_path=_project_path("c-Users-li-Desktop-proj", "sess.jsonl"),
            rows=rows,
        )
        return workbuddy_kimi.adapt(
            "workbuddy", SourceArtifactSet((artifact,)), artifact_root=root,
        )

    def test_usage_from_message_snake_usage(self, tmp_path):
        rows = [
            {"type": "message", "session_id": "wb_u1", "message_id": "m1",
             "role": "user", "content": "hi", "timestamp": 1778639294000},
            {"type": "function_call", "session_id": "wb_u1", "message_id": "m2",
             "role": "assistant", "name": "bash", "call_id": "Bash:0",
             "arguments": "ls", "timestamp": 1778639295000,
             "message": {"usage": {"input_tokens": 33521, "output_tokens": 183,
                                    "total_tokens": 33704}}},
            {"type": "function_call_result", "session_id": "wb_u1", "message_id": "m3",
             "role": "function", "call_id": "Bash:0", "result": "ok",
             "timestamp": 1778639296000},
        ]
        result = self._adapt(tmp_path, rows)
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        s = usage[0].summary or ""
        assert "input_tokens=33521" in s
        assert "output_tokens=183" in s

    def test_usage_from_provider_data_camelcase(self, tmp_path):
        rows = [
            {"type": "message", "session_id": "wb_u2", "message_id": "m1",
             "role": "assistant", "content": "ok", "timestamp": 1778639294000,
             "providerData": {"usage": {"inputTokens": 99, "outputTokens": 42,
                                        "totalTokens": 141}}},
        ]
        result = self._adapt(tmp_path, rows)
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        s = usage[0].summary or ""
        assert "input_tokens=99" in s
        assert "output_tokens=42" in s

    def test_started_at_from_first_record(self, tmp_path):
        rows = [
            {"type": "message", "session_id": "wb_s", "message_id": "m1",
             "role": "user", "content": "go", "timestamp": 1778639294000},
            {"type": "message", "session_id": "wb_s", "message_id": "m2",
             "role": "assistant", "content": "ok", "timestamp": 1778639295000},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].started_at is not None
        # 1778639294000 ms epoch -> UTC ISO via _timestamp
        assert result.sessions[0].started_at == "2026-05-13T02:28:14+00:00"

    def test_ended_at_from_last_record(self, tmp_path):
        rows = [
            {"type": "message", "session_id": "wb_e", "message_id": "m1",
             "role": "user", "content": "go", "timestamp": 1778639294000},
            {"type": "message", "session_id": "wb_e", "message_id": "m2",
             "role": "assistant", "content": "ok", "timestamp": 1778639299000},
        ]
        result = self._adapt(tmp_path, rows)
        # 1778639299000 ms epoch -> UTC ISO via _timestamp
        assert result.sessions[0].ended_at == "2026-05-13T02:28:19+00:00"
        assert result.sessions[0].started_at == "2026-05-13T02:28:14+00:00"


    def test_no_turn_boundary_without_markers(self, tmp_path):
        # Real Workbuddy exports have no explicit turn markers; the adapter must
        # NOT fabricate TURN_BOUNDARY events.
        rows = [
            {"type": "message", "session_id": "wb_t", "message_id": "m1",
             "role": "user", "content": "hi", "timestamp": "t0"},
            {"type": "function_call_result", "session_id": "wb_t", "message_id": "m2",
             "role": "function", "call_id": "c1", "result": "ok",
             "timestamp": "t1"},
        ]
        result = self._adapt(tmp_path, rows)
        bound = [e for e in result.events if e.kind is EventKind.TURN_BOUNDARY]
        assert bound == []


class TestKimiUsageAndContext:
    def test_usage_record_summary(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "turn.prompt", "time": "t1", "content": "prompt",
             "session_id": "kimi_s1"},
            {"type": "usage.record", "time": "t2", "session_id": "kimi_s1",
             "input_tokens": 99, "output_tokens": 42, "cache_read": 3},
        ]
        artifact, root = _capture_one(
            tmp_path, relative_path="projects/kimi-demo/wire.jsonl", rows=rows,
        )
        result = workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        s = usage[0].summary or ""
        assert "input_tokens=99" in s
        assert "output_tokens=42" in s
        assert "cache_read=3" in s

    def test_usage_record_real_wire_camel_case(self, tmp_path):
        # Real Kimi usage.record carries {inputOther, output, inputCacheRead,
        # inputCacheCreation} under "usage"; they map to canonical keys.
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "turn.prompt", "time": "t1", "content": "prompt",
             "session_id": "kimi_s2"},
            {"type": "usage.record", "time": "t2", "session_id": "kimi_s2",
             "model": "kimi-code/k3", "usageScope": "turn",
             "usage": {"inputOther": 6425, "output": 114,
                       "inputCacheRead": 19456, "inputCacheCreation": 0}},
        ]
        artifact, root = _capture_one(
            tmp_path, relative_path="projects/kimi-demo/wire2.jsonl", rows=rows,
        )
        result = workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        assert usage[0].content is None
        s = usage[0].summary or ""
        assert "input_tokens=6425" in s
        assert "output_tokens=114" in s
        assert "cache_read=19456" in s
        assert s.startswith("input_tokens=")

    def test_step_end_usage_emits_usage_event(self, tmp_path):
        # Real Kimi loop protocol records step end with event.usage
        # ({inputOther, output, inputCacheRead}): must surface a USAGE event
        # in canonical input_tokens= form (not an empty summary).
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "turn.prompt", "time": "t1", "content": "prompt",
             "session_id": "kimi_s3"},
            {"type": "context.append_loop_event", "time": "t2",
             "session_id": "kimi_s3",
             "event": {"type": "step.end", "uuid": "s1", "turnId": "0",
                       "step": 1, "finishReason": "tool_use",
                       "usage": {"inputOther": 22854, "output": 199,
                                 "inputCacheRead": 24832,
                                 "inputCacheCreation": 0}}},
        ]
        artifact, root = _capture_one(
            tmp_path, relative_path="projects/kimi-demo/loop.jsonl", rows=rows,
        )
        result = workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) == 1
        assert usage[0].content is None
        s = usage[0].summary or ""
        assert s.startswith("input_tokens=")
        assert "input_tokens=22854" in s
        assert "output_tokens=199" in s
        assert "cache_read=24832" in s
class TestKimiCallResultRelations:
    """Kimi nested loop-event tool.call/tool.result must pair into CALL_RESULT."""

    def _adapt(self, tmp_path, rows):
        artifact, root = _capture_one(
            tmp_path,
            relative_path="projects/kimi-demo/livewire.jsonl",
            rows=rows,
        )
        return workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )

    def test_matched_pair_yields_call_result(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "turn.prompt", "time": "t1", "content": "prompt",
             "session_id": "kimi_s1"},
            {"type": "context.append_loop_event", "time": "t2",
             "session_id": "kimi_s1",
             "event": {"type": "tool.call", "uuid": "tool_A", "turnId": "0",
                       "step": 1, "stepUuid": "step-1", "toolCallId": "tool_A",
                       "name": "bash", "arguments": "ls"}},
            {"type": "context.append_loop_event", "time": "t3",
             "session_id": "kimi_s1",
             "event": {"type": "tool.result", "parentUuid": "tool_A",
                       "toolCallId": "tool_A",
                       "result": {"output": "ok"}}},
        ]
        result = self._adapt(tmp_path, rows)
        calls = [e for e in result.events if e.kind is EventKind.TOOL_CALL]
        res = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(calls) == 1
        assert len(res) == 1

        rels = [r for r in result.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rels) == 1
        rel = rels[0]
        assert rel.source_event_id == calls[0].event_id
        assert rel.target_event_id == res[0].event_id

    def test_matched_pair_returns_same_relation_on_replay(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "context.append_loop_event", "time": "t2",
             "session_id": "kimi_s1",
             "event": {"type": "tool.call", "uuid": "tool_B", "turnId": "0",
                       "step": 1, "stepUuid": "step-1", "toolCallId": "tool_B",
                       "name": "bash", "arguments": "ls"}},
            {"type": "context.append_loop_event", "time": "t3",
             "session_id": "kimi_s1",
             "event": {"type": "tool.result", "parentUuid": "tool_B",
                       "toolCallId": "tool_B",
                       "result": {"output": "ok"}}},
        ]
        first = self._adapt(tmp_path, rows)
        second = self._adapt(tmp_path, rows)
        rel1 = [r for r in first.relations if r.relation_kind is RelationKind.CALL_RESULT]
        rel2 = [r for r in second.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rel1) == 1 and len(rel2) == 1
        assert rel1[0].relation_id == rel2[0].relation_id

    def test_unpaired_result_yields_no_orphan_relation(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "context.append_loop_event", "time": "t3",
             "session_id": "kimi_s1",
             "event": {"type": "tool.result", "parentUuid": "missing_tool",
                       "toolCallId": "missing_tool",
                       "result": {"output": "ok"}}},
        ]
        result = self._adapt(tmp_path, rows)
        rels = [r for r in result.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert rels == []
        # the result event is still preserved, just not linked
        res = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1

    def test_orphan_relation_warning_emitted(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": "t0", "protocol_version": 1},
            {"type": "context.append_loop_event", "time": "t3",
             "session_id": "kimi_s1",
             "event": {"type": "tool.result", "parentUuid": "x",
                       "toolCallId": "x", "result": {"output": "ok"}}},
        ]
        result = self._adapt(tmp_path, rows)
        assert any("missing" in w for w in result.warnings) or any(
            "partial" in w for w in result.warnings
        )

class TestKimiEnvelopeContext:
    """DEEP-1: new-format kimi event stream records
    ({"kind":"event","seq":N,"envelope":{"type":...,"payload":{...}}}).

    These records have no top-level 'type'; the adapter must classify from the
    envelope and surface tool CALL_RESULT pairing, turn boundaries, subagent
    events+relations, session.meta.updated title extraction, context.spliced as
    FILE_CONTEXT, and USAGE from turn.step.completed.usage.
    """

    def _adapt(self, tmp_path, rows, name="envelope.jsonl"):
        artifact, root = _capture_one(
            tmp_path,
            relative_path=_project_path("c-Users-li-Desktop-proj", name),
            rows=[{"kind": "journal_header", "version": 1}] + rows,
        )
        return workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )

    # ---- tool pairing -> CALL_RESULT ----
    def test_tool_pairing_yields_call_result(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "tool.call.started", "seq": 1,
                "session_id": "env_s1", "timestamp": "t1",
                "payload": {"type": "tool.call.started", "turnId": 0,
                            "toolCallId": "tool_A", "name": "Bash",
                            "args": {"command": "ls"}}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "tool.result", "seq": 2,
                "session_id": "env_s1", "timestamp": "t2",
                "payload": {"type": "tool.result", "turnId": 0,
                            "toolCallId": "tool_A", "output": "result ok"}}},
        ]
        result = self._adapt(tmp_path, rows)
        calls = [e for e in result.events if e.kind is EventKind.TOOL_CALL]
        res = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(calls) == 1
        assert len(res) == 1
        rels = [r for r in result.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rels) == 1
        assert rels[0].source_event_id == calls[0].event_id
        assert rels[0].target_event_id == res[0].event_id
        # no unknown_native for the paired tool records
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in result.events)

    def test_tool_pairing_returns_same_relation_on_replay(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "tool.call.started", "seq": 1,
                "session_id": "env_s1", "timestamp": "t1",
                "payload": {"type": "tool.call.started", "toolCallId": "tool_B",
                            "name": "Bash"}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "tool.result", "seq": 2,
                "session_id": "env_s1", "timestamp": "t2",
                "payload": {"type": "tool.result", "toolCallId": "tool_B",
                            "output": "ok"}}},
        ]
        first = self._adapt(tmp_path, rows)
        second = self._adapt(tmp_path, rows)
        rel1 = [r for r in first.relations if r.relation_kind is RelationKind.CALL_RESULT]
        rel2 = [r for r in second.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rel1) == 1 and len(rel2) == 1
        assert rel1[0].relation_id == rel2[0].relation_id

    def test_unpaired_tool_result_yields_no_relation(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "tool.result", "seq": 1,
                "session_id": "env_s2", "timestamp": "t1",
                "payload": {"type": "tool.result", "toolCallId": "orphan",
                            "output": "ok"}}},
        ]
        result = self._adapt(tmp_path, rows)
        rels = [r for r in result.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert rels == []
        res = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1

    # ---- turn boundaries ----
    def test_turn_boundaries_mapped(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "turn.started", "seq": 1,
                "session_id": "env_s3", "timestamp": "t1",
                "payload": {"type": "turn.started", "turnId": 0}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "turn.step.started", "seq": 2,
                "session_id": "env_s3", "timestamp": "t2",
                "payload": {"type": "turn.step.started", "turnId": 0, "step": 1}}},
            {"kind": "event", "seq": 3, "envelope": {
                "type": "turn.step.completed", "seq": 3,
                "session_id": "env_s3", "timestamp": "t3",
                "payload": {"type": "turn.step.completed", "turnId": 0, "step": 1}}},
            {"kind": "event", "seq": 4, "envelope": {
                "type": "turn.ended", "seq": 4,
                "session_id": "env_s3", "timestamp": "t4",
                "payload": {"type": "turn.ended", "turnId": 0, "reason": "done"}}},
        ]
        result = self._adapt(tmp_path, rows)
        bounds = [e for e in result.events if e.kind is EventKind.TURN_BOUNDARY]
        assert len(bounds) == 4
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in result.events)

    # ---- subagent events + relations ----
    def test_subagent_events_and_relation(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "agent.created", "seq": 1,
                "session_id": "env_s4", "timestamp": "t1",
                "payload": {"type": "agent.created", "agentId": "main"}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "subagent.spawned", "seq": 2,
                "session_id": "env_s4", "timestamp": "t2",
                "payload": {"type": "subagent.spawned", "subagentId": "agent-1",
                            "parentAgentId": "main", "callerAgentId": "main",
                            "description": "explore"}}},
            {"kind": "event", "seq": 3, "envelope": {
                "type": "subagent.started", "seq": 3,
                "session_id": "env_s4", "timestamp": "t3",
                "payload": {"type": "subagent.started", "subagentId": "agent-1"}}},
            {"kind": "event", "seq": 4, "envelope": {
                "type": "subagent.completed", "seq": 4,
                "session_id": "env_s4", "timestamp": "t4",
                "payload": {"type": "subagent.completed", "subagentId": "agent-1",
                            "resultSummary": "done"}}},
        ]
        result = self._adapt(tmp_path, rows)
        subs = [e for e in result.events if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert len(subs) >= 1
        assert all((e.summary or "") in ("agent-1", "") for e in subs)
        assert any((e.summary or "") == "agent-1" for e in subs)
        rels = [r for r in result.relations if r.relation_kind is RelationKind.SUBAGENT]
        assert len(rels) >= 1
        # child -> parent: source is a subagent boundary, target is main lifecycle
        parent_lifecycle = next(
            e.event_id for e in result.events
            if e.kind is EventKind.SESSION_LIFECYCLE
        )
        for rel in rels:
            assert rel.target_event_id == parent_lifecycle
        # every SUBAGENT relation endpoint resolves to a known event
        known = {e.event_id for e in result.events}
        assert all(r.source_event_id in known and r.target_event_id in known
                   for r in result.relations)

    # ---- title extraction from session.meta.updated ----
    def test_title_from_session_meta_updated(self, tmp_path):
        title = "重构 Phase 26+ 统一执行基线并执行 GSD 规划"
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "event.session.created", "seq": 1,
                "session_id": "env_s5", "timestamp": "t1",
                "payload": {"type": "event.session.created"}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "session.meta.updated", "seq": 2,
                "session_id": "env_s5", "timestamp": "t2",
                "payload": {"type": "session.meta.updated", "title": title,
                            "patch": {"title": title}}}},
        ]
        result = self._adapt(tmp_path, rows)
        session = result.sessions[0]
        assert session.title is not None
        assert session.title.startswith("重构 Phase 26+")
        assert len(session.title) <= 120

    def test_native_session_id_from_envelope(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "turn.started", "seq": 1,
                "session_id": "env_real_sid", "timestamp": "t1",
                "payload": {"type": "turn.started"}}},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].native_session_id == "env_real_sid"

    # ---- context.spliced -> FILE_CONTEXT ----
    def test_context_spliced_maps_to_file_context(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "context.spliced", "seq": 1,
                "session_id": "env_s7", "timestamp": "t1",
                "payload": {"type": "context.spliced", "start": 0,
                            "messages": [
                                {"role": "user",
                                 "content": [{"type": "text",
                                              "text": "build the index"}]},
                                {"role": "assistant",
                                 "content": [{"type": "text",
                                              "text": "ok"}]},
                            ]}}},
        ]
        result = self._adapt(tmp_path, rows)
        fc = [e for e in result.events if e.kind is EventKind.FILE_CONTEXT]
        assert len(fc) == 1
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in result.events)

    # ---- USAGE from turn.step.completed.usage ----
    def test_usage_from_step_completed(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "turn.step.completed", "seq": 1,
                "session_id": "env_s8", "timestamp": "t1",
                "payload": {"type": "turn.step.completed", "turnId": 0, "step": 1,
                            "usage": {"inputOther": 22854, "output": 199,
                                      "inputCacheRead": 24832,
                                      "inputCacheCreation": 0}}}},
        ]
        result = self._adapt(tmp_path, rows)
        usage = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usage) >= 1
        s = usage[0].summary or ""
        assert "input_tokens=22854" in s
        assert "output_tokens=199" in s

    # ---- compaction -> COMPACTION_SUMMARY ----
    def test_compaction_maps_to_summary(self, tmp_path):
        rows = [
            {"kind": "event", "seq": 1, "envelope": {
                "type": "compaction.started", "seq": 1,
                "session_id": "env_s9", "timestamp": "t1",
                "payload": {"type": "compaction.started", "trigger": "auto"}}},
            {"kind": "event", "seq": 2, "envelope": {
                "type": "compaction.completed", "seq": 2,
                "session_id": "env_s9", "timestamp": "t2",
                "payload": {"type": "compaction.completed",
                            "result": {"summary": "compacted context here"}}}},
        ]
        result = self._adapt(tmp_path, rows)
        cs = [e for e in result.events if e.kind is EventKind.COMPACTION_SUMMARY]
        assert len(cs) >= 1
        assert any((e.summary or "") == "compacted context here" for e in cs)
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in result.events)

class TestKimiOldFormatTimestampsModelCwd:
    """P0-F2: old-format kimi records lose their timestamp and session context.

    The old-format (top-level 'type') wire records carry a millisecond-epoch
    'time' field (some also 'timestamp') and the metadata header uses
    'created_at'; these must surface as event.occurred_at and session
    started_at/ended_at instead of NULL. Model comes from usage.record / llm.request
    / config.update; cwd is only derivable when the relative path carries it.
    """

    def _adapt(self, tmp_path, rows, name="wire.jsonl"):
        artifact, root = _capture_one(
            tmp_path, relative_path="projects/kimi-demo/" + name, rows=rows,
        )
        return workbuddy_kimi.adapt(
            "kimi", SourceArtifactSet((artifact,)), artifact_root=root,
        )

    def test_old_format_time_field_populates_occurred_at(self, tmp_path):
        rows = [
            {"type": "usage.record", "time": 1785812149225, "session_id": "k_old1",
             "model": "kimi-code/k3"},
            {"type": "context.append_loop_event", "time": 1785812150000,
             "session_id": "k_old1",
             "event": {"type": "step.end", "uuid": "s1", "finishReason": "end_turn"}},
        ]
        result = self._adapt(tmp_path, rows)
        assert all(e.occurred_at is not None for e in result.events)
        # epoch-ms 1785812149225 -> UTC ISO
        assert result.sessions[0].started_at == "2026-08-04T02:55:49.225000+00:00"

    def test_old_format_timestamp_field_populates_occurred_at(self, tmp_path):
        rows = [
            {"type": "context.append_loop_event", "timestamp": 1785812149225,
             "session_id": "k_old2",
             "event": {"type": "step.begin", "uuid": "s1"}},
        ]
        result = self._adapt(tmp_path, rows)
        assert all(e.occurred_at is not None for e in result.events)

    def test_old_format_occurred_at_epoch_to_iso(self, tmp_path):
        rows = [
            {"type": "turn.prompt", "time": 1785812149225, "session_id": "k_old3",
             "input": [{"type": "text", "text": "hello"}]},
        ]
        result = self._adapt(tmp_path, rows)
        prompts = [e for e in result.events if e.kind is EventKind.USER_MESSAGE]
        assert prompts
        assert prompts[0].occurred_at == "2026-08-04T02:55:49.225000+00:00"

    def test_old_format_model_from_usage_record(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": 1785812149000, "protocol_version": 1},
            {"type": "usage.record", "time": 1785812149225, "session_id": "k_m1",
             "model": "kimi-code/k3"},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].model == "kimi-code/k3"

    def test_old_format_model_from_config_model_alias(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": 1785812149000, "protocol_version": 1},
            {"type": "config.update", "time": 1785812149225, "session_id": "k_m2",
             "modelAlias": "kimi-code/kimi-for-coding"},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].model == "kimi-code/kimi-for-coding"

    def test_old_format_last_model_wins(self, tmp_path):
        rows = [
            {"type": "config.update", "time": 1785812149000, "session_id": "k_m3",
             "modelAlias": "kimi-code/kimi-for-coding"},
            {"type": "usage.record", "time": 1785812149225, "session_id": "k_m3",
             "model": "kimi-code/k3"},
        ]
        result = self._adapt(tmp_path, rows)
        # the later real usage model overrides the earlier default
        assert result.sessions[0].model == "kimi-code/k3"

    def test_model_none_when_no_model_field(self, tmp_path):
        rows = [
            {"type": "metadata", "created_at": 1785812149000, "protocol_version": 1},
            {"type": "turn.prompt", "time": 1785812149225, "session_id": "k_m4",
             "input": [{"type": "text", "text": "go"}]},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].model is None

    def test_cwd_none_when_path_is_basename_only(self, tmp_path):
        # Live capture passes only the basename so the native workdir is lost;
        # cwd must stay None rather than be fabricated.
        rows = [
            {"type": "metadata", "created_at": 1785812149000, "protocol_version": 1},
            {"type": "turn.prompt", "time": 1785812149225, "session_id": "k_c2",
             "input": [{"type": "text", "text": "go"}]},
        ]
        result = self._adapt(tmp_path, rows)
        assert result.sessions[0].cwd is None

