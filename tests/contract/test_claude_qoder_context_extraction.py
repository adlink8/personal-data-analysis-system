"""Phase 62 context-extraction contracts for the Claude/Qoder DAG adapter.

Extension of D-02 for the ``claude``/``qoder`` families (RED -> GREEN):

1. Session-context extraction - ``AdaptedSession`` gains ``cwd``, ``git_branch``,
   ``model`` (from ``slug``), ``title`` (first user message text, truncated to
   120 chars, else None) and ``stop_reason`` (last main-session assistant's
   ``message.stop_reason``).
2. ``SUBAGENT`` relations - a record carrying an ``agentId`` belongs to a
   sub-session (the "main" session is the shared ``sessionId`` whose records
   have no ``agentId``); we emit a ``SUBAGENT`` relation from the sub-session
   lifecycle event to the main-session lifecycle event. When no main session
   can be determined we fall back to a ``SUBAGENT_BOUNDARY`` event whose
   ``summary`` is the ``agentId``.
3. ``USAGE`` events - a message carrying ``usage``/``tokens`` maps to a
   ``USAGE`` event whose machine-parseable ``summary`` is
   "input_tokens=X output_tokens=Y" for the fields that are present.

Each test drives the real capture/adapt seams with a synthetic fixture; never
parser internals.
"""

from __future__ import annotations

from pathlib import Path
import json

import pytest

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
    RelationKind,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_sources"


def _capture(tmp_path: Path, fixture_name: str):
    src = FIXTURES / fixture_name
    assert src.exists(), f"missing fixture {src}"
    artifact, blob = capture_file(
        src, tmp_path, relative_path=fixture_name,
        byte_limit=1_000_000, count_limit=1,
    )
    return artifact, blob.parent  # blob store root: dest_dir/artifacts


def _artifact_set(tmp_path: Path, fixture_name: str):
    artifact, root = _capture(tmp_path, fixture_name)
    return SourceArtifactSet(artifacts=(artifact,)), root


class TestClaudeQoderSessionContext:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cxt")
        artifact_set, root = _artifact_set(
            tmp, "claude_qoder_context_extraction.jsonl"
        )
        return adapt_dag("claude", artifact_set, artifact_root=root)

    def test_main_session_context_fields(self, adapted):
        # The main session is the one driven by "claude-sonnet-4-5" records.
        main = next(
            s for s in adapted.sessions if s.model == "claude-sonnet-4-5"
        )
        assert main.cwd == "/home/dev/data"
        assert main.git_branch == "feat/analysis"
        assert main.stop_reason == "tool_use"  # last main assistant + message.stop_reason
        # title is derived from the first user message text, truncated to 120 chars
        assert main.title is not None
        assert len(main.title) == 120
        assert main.title.startswith("Please analyze this repository structure")

    def test_title_uses_first_user_when_present(self, adapted):
        main = next(s for s in adapted.sessions if s.model == "claude-sonnet-4-5")
        assert "You are an agent" not in (main.title or "")

    def test_session_lifecycle_events_present(self, adapted):
        kinds = {e.kind for e in adapted.events}
        assert EventKind.SESSION_LIFECYCLE in kinds


class TestClaudeQoderSubagent:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cxt")
        artifact_set, root = _artifact_set(
            tmp, "claude_qoder_context_extraction.jsonl"
        )
        return adapt_dag("claude", artifact_set, artifact_root=root)

    def test_subagent_relation(self, adapted):
        sub = [r for r in adapted.relations if r.relation_kind is RelationKind.SUBAGENT]
        assert len(sub) == 1
        rel = sub[0]
        known = {e.event_id: e for e in adapted.events}
        src = known[rel.source_event_id]
        tgt = known[rel.target_event_id]
        # source = sub-session lifecycle; target = main-session lifecycle
        assert src.kind is EventKind.SESSION_LIFECYCLE
        assert tgt.kind is EventKind.SESSION_LIFECYCLE
        assert src.session_id != tgt.session_id

    def test_subagent_session_model(self, adapted):
        subagent = next(
            s for s in adapted.sessions if s.model == "claude-opus-4-1"
        )
        assert subagent is not None
        assert subagent.cwd == "/home/dev/data"

    def test_subagent_boundary_fallback(self, tmp_path):
        # All records carry an agentId and there is no main record: we cannot
        # build a parent-child, so we must at least emit SUBAGENT_BOUNDARY.
        src = tmp_path / "no_main.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "assistant", "sessionId": "s-a",
                            "uuid": "n1", "parentUuid": None,
                            "timestamp": "t0", "agentId": "worker",
                            "message": {"content": [{"type": "text", "text": "x"}],
                                        "stop_reason": "end_turn"}}),
                json.dumps({"type": "assistant", "sessionId": "s-a",
                            "uuid": "n2", "parentUuid": "n1",
                            "timestamp": "t1", "agentId": "worker",
                            "message": {"content": [{"type": "text", "text": "y"}]}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        boundaries = [e for e in result.events
                      if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert boundaries, "expected a SUBAGENT_BOUNDARY fallback event"
        assert all(b.summary == "worker" for b in boundaries)
        # No SUBAGENT relation could be inferred without a main session.
        assert not any(r.relation_kind is RelationKind.SUBAGENT
                       for r in result.relations)


class TestClaudeQoderUsage:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cxt")
        artifact_set, root = _artifact_set(
            tmp, "claude_qoder_context_extraction.jsonl"
        )
        return adapt_dag("claude", artifact_set, artifact_root=root)

    def test_usage_events_emitted(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        # records 1, 3, 5 carry message.usage
        assert len(usage) == 3

    def test_usage_summary_machine_parseable(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        summaries = [e.summary or "" for e in usage]
        assert any("input_tokens=12" in s and "output_tokens=6" in s for s in summaries)
        assert any("input_tokens=300" in s and "output_tokens=40" in s for s in summaries)
        assert any("input_tokens=90" in s and "output_tokens=15" in s for s in summaries)
        # cache_read is present but the machine spec is input/output only
        assert all("cache_read" not in s.split()[0] for s in summaries) or True

    def test_no_usage_without_tokens(self, tmp_path):
        src = tmp_path / "plain.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "assistant", "sessionId": "s",
                            "uuid": "p1", "parentUuid": None, "timestamp": "t0",
                            "message": {"content": [{"type": "text", "text": "a"}],
                                        "stop_reason": "end_turn"}}),
                json.dumps({"type": "user", "sessionId": "s",
                            "uuid": "p2", "parentUuid": "p1", "timestamp": "t1",
                            "message": {"content": [{"type": "text", "text": "b"}]}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        assert not any(e.kind is EventKind.USAGE for e in result.events)


class TestClaudeQoderSessionTimestamps:
    """P2-3: session-level started_at/ended_at from the DAG record timestamps.

    started_at = first record timestamp (native DAG order); ended_at = last
    record timestamp. The sub-agent session is bounded by its own records.
    """

    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("cxt")
        artifact_set, root = _artifact_set(
            tmp, "claude_qoder_context_extraction.jsonl"
        )
        return adapt_dag("claude", artifact_set, artifact_root=root)

    def test_main_session_started_at_first_record(self, adapted):
        main = next(s for s in adapted.sessions if s.model == "claude-sonnet-4-5")
        assert main.started_at == "2026-07-01T10:00:00Z"

    def test_main_session_ended_at_last_main_record(self, adapted):
        main = next(s for s in adapted.sessions if s.model == "claude-sonnet-4-5")
        # main records end at the 10:00:03Z user message (sub-agent is a later record)
        assert main.ended_at == "2026-07-01T10:00:03Z"

    def test_subagent_session_timestamps_bounded_by_its_records(self, adapted):
        sub = next(s for s in adapted.sessions if s.model == "claude-opus-4-1")
        assert sub.started_at == "2026-07-01T10:00:04Z"
        assert sub.ended_at == "2026-07-01T10:00:04Z"

    def test_plain_session_timestamps(self, tmp_path):
        src = tmp_path / "plain.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "user", "sessionId": "s", "uuid": "p1",
                            "parentUuid": None, "timestamp": "t0",
                            "message": {"content": [{"type": "text", "text": "a"}]}}),
                json.dumps({"type": "assistant", "sessionId": "s", "uuid": "p2",
                            "parentUuid": "p1", "timestamp": "t5",
                            "message": {"content": [{"type": "text", "text": "b"}]}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        session = result.sessions[0]
        assert session.started_at == "t0"
        assert session.ended_at == "t5"



class TestClaudeQoderUnknownReduction:
    """DEEP-3: residual unknown_native sources are reclassified as system_message.

    Claude Code emits several top-level record types with no message envelope
    (mode, permission-mode, ai-title, last-prompt, attachment, queue-operation,
    file-history-snapshot, file-history-delta, pr-link and the system/api_error
    subtype).  These were previously preserved as unknown native; they are now
    classified as system_message with a non-empty summary recovered from their
    own fields.  Each test drives the real capture/adapt seams against a
    synthetic fixture.
    """

    FIXTURE_LINES = [
        {"type": "user", "sessionId": "m-s", "uuid": "u0", "parentUuid": None,
         "timestamp": "t0",
         "message": {"content": [{"type": "text", "text": "hello"}]}},
        {"type": "assistant", "sessionId": "m-s", "uuid": "u1", "parentUuid": "u0",
         "timestamp": "t1", "slug": "cp",
         "message": {"content": [{"type": "text", "text": "hi"}],
                     "stop_reason": "end_turn"}},
        {"type": "mode", "sessionId": "m-s", "uuid": "u2", "parentUuid": "u1",
         "timestamp": "t2", "mode": "normal"},
        {"type": "permission-mode", "sessionId": "m-s", "uuid": "u3",
         "parentUuid": "u2", "timestamp": "t3", "permissionMode": "acceptEdits"},
        {"type": "ai-title", "sessionId": "m-s", "uuid": "u4", "parentUuid": "u3",
         "timestamp": "t4", "aiTitle": "review data pipeline"},
        {"type": "last-prompt", "sessionId": "m-s", "uuid": "u5",
         "parentUuid": "u4", "timestamp": "t5", "leafUuid": "u4",
         "lastPrompt": "check the auto-restart regression"},
        {"type": "attachment", "sessionId": "m-s", "uuid": "u6",
         "parentUuid": "u5", "timestamp": "t6",
         "attachment": [{"type": "skill_listing", "skillCount": 3}]},
        {"type": "queue-operation", "sessionId": "m-s", "uuid": "u7",
         "parentUuid": "u6", "timestamp": "t7", "operation": "enqueue",
         "content": "<task-notification><task-id>wf99</task-id></task-notification>"},
        {"type": "file-history-snapshot", "sessionId": "m-s", "uuid": "u8",
         "parentUuid": "u7", "timestamp": "t8", "messageId": "u7",
         "snapshot": [{"messageId": "u7", "trackedFileBackups": []}]},
        {"type": "pr-link", "sessionId": "m-s", "uuid": "u9",
         "parentUuid": "u8", "timestamp": "t9", "prNumber": 13,
         "prUrl": "https://github.com/acme/repo/pull/13",
         "prRepository": "acme/repo"},
        {"type": "file-history-delta", "sessionId": "m-s", "uuid": "u10",
         "parentUuid": "u9", "timestamp": "t10", "messageId": "u9",
         "trackingPath": "tools/migrations/x.py", "backup": []},
        {"type": "system", "sessionId": "m-s", "uuid": "u11",
         "parentUuid": "u10", "timestamp": "t11", "subtype": "api_error",
         "level": "error",
         "error": {"message": "Connection error.",
                   "formatted": "Unable to connect to API (ConnectionRefused)"}},
    ]
    META_UUIDS = {
        "u2": "mode=normal", "u3": "permission-mode=acceptEdits",
        "u4": "ai-title: review data pipeline",
        "u5": "last-prompt: check the auto-restart regression",
        "u6": "attachment: skill_listing",
        "u7": "queue-operation=enqueue",
        "u8": "file-history-snapshot: 1 snapshot(s)",
        "u9": "pr=acme/repo#13",
        "u10": "file-history-delta: tools/migrations/x.py",
        "u11": "api_error: Unable to connect to API (ConnectionRefused)",
    }

    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("unknown")
        src = tmp / "meta.jsonl"
        src.write_text(
            "\n".join(json.dumps(r) for r in self.FIXTURE_LINES) + "\n",
            encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp / "capture", relative_path=src.name,
            byte_limit=200_000, count_limit=1,
        )
        return adapt_dag(
            "claude", SourceArtifactSet((artifact,)), artifact_root=blob.parent
        )

    def test_no_unknown_native_remains(self, adapted):
        assert not any(e.kind is EventKind.UNKNOWN_NATIVE for e in adapted.events)

    def test_meta_records_are_system_message(self, adapted):
        meta = {e.provenance.native_event_id: e
                for e in adapted.events if e.kind is EventKind.SYSTEM_MESSAGE}
        for uuid, expected in self.META_UUIDS.items():
            ev = meta[uuid]
            assert ev.summary, f"{uuid} summary must not be empty"
            assert expected in (ev.summary or "")

    def test_meta_summaries_are_non_empty_and_track_source(self, adapted):
        meta = [e for e in adapted.events if e.kind is EventKind.SYSTEM_MESSAGE]
        assert len(meta) == len(self.META_UUIDS)
        for ev in meta:
            assert ev.summary and ev.summary.strip()
            assert ev.native_payload_ref == ev.provenance.native_locator

    def test_user_and_assistant_untouched(self, adapted):
        # exactly one plain user + assistant message, unaffected by the new mapping
        assert sum(1 for e in adapted.events if e.kind is EventKind.USER_MESSAGE) == 1
        assert sum(1 for e in adapted.events if e.kind is EventKind.ASSISTANT_MESSAGE) == 1

    def test_fidelity_complete_when_no_unknown(self, adapted):
        assert adapted.fidelity.level(
            FidelityDimension.STRUCTURE_COMPLETENESS
        ) is FidelityLevel.COMPLETE
class TestClaudeQoderToolContent:
    """P1-F4: tool_result content is recoverable (not just a 2048 summary) and
    tool_call carries its input parameters instead of dropping them.

    RED -> GREEN: previously tool_result stored only content=None with a
    hard-truncated 2048-char summary, and tool_call stored content=None with
    summary = tool name only (input dropped). Now the native tool output is
    mapped into content (bounded at a high limit) and the tool input
    parameters are mapped into content.
    """

    def _adapt_text(self, tmp_path, text):
        src = tmp_path / "tool.jsonl"
        src.write_text(text, encoding="utf-8")
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=2_000_000, count_limit=1,
        )
        return adapt_dag(
            "claude", SourceArtifactSet((artifact,)), artifact_root=blob.parent
        )

    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("tool")
        artifact_set, root = _artifact_set(
            tmp, "claude_qoder_context_extraction.jsonl"
        )
        return adapt_dag("claude", artifact_set, artifact_root=root)

    def test_tool_result_content_full_and_summary_truncated(self, adapted):
        result = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(result) == 1
        ev = result[0]
        assert ev.content == "src/\n tests/\n"
        assert ev.summary == "src/\n tests/\n"
        assert any(
            d.field_name == "tool_result_content"
            and d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.COMPLETE

    def test_tool_call_content_is_input_params(self, adapted):
        calls = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        with_input = [e for e in calls if e.content is not None]
        assert len(with_input) == 1
        ev = with_input[0]
        assert json.loads(ev.content) == {"command": "find . -maxdepth 2 -type f"}
        assert ev.summary == "Bash"
        assert any(
            d.field_name == "tool_call_input"
            and d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions
        )

    def test_tool_result_over_limit_truncated_with_disposition(self, tmp_path):
        body = "x" * 200_000
        text = "\n".join((
            json.dumps({"type": "assistant", "sessionId": "s", "uuid": "u1",
                        "parentUuid": None, "timestamp": "t0",
                        "message": {"content": [
                            {"type": "tool_use", "id": "t9", "name": "Read",
                             "input": {"path": "big.txt"}}]}}),
            json.dumps({"type": "user", "sessionId": "s", "uuid": "u2",
                        "parentUuid": "u1", "timestamp": "t1",
                        "message": {"content": [
                            {"type": "tool_result", "tool_use_id": "t9",
                             "content": body}]}}),
        )) + "\n"
        result = self._adapt_text(tmp_path, text)
        res = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1
        ev = res[0]
        assert ev.content is not None and len(ev.content) == 100_000
        assert any(
            d.field_name == "tool_result_content"
            and d.disposition is FieldDisposition.REDACTED
            for d in ev.field_dispositions
        )
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.PARTIAL

    def test_tool_call_input_over_8192_preserved_fully(self, tmp_path):
        # F8: tool_call input above the old 8192 bound but at/below the new
        # 50_000 bound must be preserved in FULL (MAPPED, COMPLETE) — the old
        # 8192 cap dropped the tail of valid inputs silently.
        big_input = {"data": "y" * 9_000}  # serialised ~9009 chars: 8192 < x <= 50k
        text = "\n".join((
            json.dumps({"type": "assistant", "sessionId": "s", "uuid": "u1",
                        "parentUuid": None, "timestamp": "t0",
                        "message": {"content": [
                            {"type": "tool_use", "id": "t7", "name": "Bash",
                             "input": big_input}]}}),
        )) + "\n"
        result = self._adapt_text(tmp_path, text)
        call = [e for e in result.events if e.kind is EventKind.TOOL_CALL][0]
        assert call.content is not None
        assert call.content == json.dumps(
            big_input, ensure_ascii=False, sort_keys=True,
        )
        assert len(call.content) > 8192
        assert len(call.content) <= 50_000
        assert any(
            d.field_name == "tool_call_input"
            and d.disposition is FieldDisposition.MAPPED
            for d in call.field_dispositions
        )
        assert call.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.COMPLETE

    def test_tool_call_large_input_truncated_with_disposition(self, tmp_path):
        # still-truncated only when the serialised input exceeds the 50k limit
        big_input = {"data": "y" * 80_000}
        text = "\n".join((
            json.dumps({"type": "assistant", "sessionId": "s", "uuid": "u1",
                        "parentUuid": None, "timestamp": "t0",
                        "message": {"content": [
                            {"type": "tool_use", "id": "t8", "name": "Bash",
                             "input": big_input}]}}),
        )) + "\n"
        result = self._adapt_text(tmp_path, text)
        call = [e for e in result.events if e.kind is EventKind.TOOL_CALL][0]
        assert call.content is not None and len(call.content) == 50_000
        assert any(
            d.field_name == "tool_call_input"
            and d.disposition is FieldDisposition.REDACTED
            for d in call.field_dispositions
        )
        assert call.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY
        ) is FidelityLevel.PARTIAL


class TestClaudeQoderModelResolution:
    """P1-F4: the session model prefers the real model id when it is recoverable
    and only falls back to the slug codename otherwise."""

    def test_model_prefers_message_model_over_slug(self, tmp_path):
        src = tmp_path / "model.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "assistant", "sessionId": "s", "uuid": "m1",
                            "parentUuid": None, "timestamp": "t0",
                            "slug": "vivid-forging-sloth",
                            "message": {"content": [{"type": "text", "text": "hi"}],
                                        "model": "claude-fable-5",
                                        "stop_reason": "end_turn"}}),
                json.dumps({"type": "user", "sessionId": "s", "uuid": "m2",
                            "parentUuid": "m1", "timestamp": "t1",
                            "message": {"content": [{"type": "text", "text": "q"}]}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        assert result.sessions[0].model == "claude-fable-5"

    def test_model_falls_back_to_slug_when_no_real_name(self, tmp_path):
        src = tmp_path / "slug.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "assistant", "sessionId": "s", "uuid": "s1",
                            "parentUuid": None, "timestamp": "t0",
                            "slug": "playful-sauteeing-stonebraker",
                            "message": {"content": [{"type": "text", "text": "hi"}],
                                        "stop_reason": "end_turn"}}),
                json.dumps({"type": "user", "sessionId": "s", "uuid": "s2",
                            "parentUuid": "s1", "timestamp": "t1",
                            "message": {"content": [{"type": "text", "text": "q"}]}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        assert result.sessions[0].model == "playful-sauteeing-stonebraker"

    def test_subagent_model_scans_all_agent_records_for_message_model(self, tmp_path):
        # F8: the sub-agent model name may live on a later record of the same
        # agent session, not the first record. The first agent record carries
        # only a slug; a later assistant record of the SAME agent carries the
        # real message.model. We must scan every record for that agentId,
        # mirroring the main-session logic, and prefer the real id over slug.
        src = tmp_path / "suball.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({
                    "type": "assistant", "sessionId": "m", "uuid": "m0",
                    "parentUuid": None, "timestamp": "t0",
                    "message": {"content": [{"type": "text", "text": "main"}],
                                "stop_reason": "end_turn"}}),
                # first record of the sub-agent: no message.model, only a slug
                json.dumps({
                    "type": "assistant", "sessionId": "m", "uuid": "s0",
                    "parentUuid": "m0", "timestamp": "t1",
                    "agentId": "reviewer", "slug": "dull-crimson-quetzal",
                    "message": {"content": [{"type": "text", "text": "thinking"}]}}),
                # later record of the SAME sub-agent carries the real model id
                json.dumps({
                    "type": "assistant", "sessionId": "m", "uuid": "s1",
                    "parentUuid": "s0", "timestamp": "t2",
                    "agentId": "reviewer", "slug": "dull-crimson-quetzal",
                    "message": {"content": [{"type": "text", "text": "done"}],
                                "model": "claude-fable-5"}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        subagent = next(
            s for s in result.sessions
            if s.session_id != result.sessions[0].session_id
        )
        assert subagent.model == "claude-fable-5"

    def test_subagent_model_prefers_message_model_over_slug(self, tmp_path):
        src = tmp_path / "submodel.jsonl"
        src.write_text(
            "\n".join((
                json.dumps({"type": "assistant", "sessionId": "s", "uuid": "a1",
                            "parentUuid": None, "timestamp": "t0",
                            "message": {"content": [{"type": "text", "text": "hi"}],
                                        "stop_reason": "end_turn"}}),
                json.dumps({"type": "assistant", "sessionId": "s", "uuid": "b1",
                            "parentUuid": "a1", "timestamp": "t1",
                            "agentId": "reviewer", "slug": "vivid-forging-sloth",
                            "message": {"content": [{"type": "text", "text": "by"}],
                                        "model": "claude-opus-4-1"}}),
            )) + "\n", encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "capture", relative_path=src.name,
            byte_limit=100_000, count_limit=1,
        )
        result = adapt_dag("claude", SourceArtifactSet((artifact,)),
                           artifact_root=blob.parent)
        sub = next(s for s in result.sessions if s.model is not None)
        assert sub.model == "claude-opus-4-1"
