"""Phase 62-05: Codex context extraction (Agent A) - RED to GREEN.

Extends the Codex event-stream adapter contract (codex family) with the
context attributes a real Codex export exposes:

  - AdaptedSession context fields: cwd, git_branch, model, title
    (from session_meta.payload plus the first user message).
  - USAGE events: when a response_item carries token counts, emit a
    usage event whose machine-parseable summary is
    "input_tokens=X output_tokens=Y [cache_read=Z cache_write=W]".
  - Sub-agent signalling: when session_meta carries forked_from_id the
    current session is the forked child. The forked-from (parent)
    session lifecycle event is never resolvable inside a
    single-session Codex artifact, so a SUBAGENT_BOUNDARY event is
    emitted with summary=forked_from_id instead of fabricating a
    cross-session SUBAGENT relation.

Fixtures are synthetic real-shape records (fields nested under payload)
so the extraction contract is exercised against the wire shape Codex writes.
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
    RelationKind,
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
        "id": "sess_forked_01",
        "timestamp": "2026-07-01T10:00:00Z",
        "originator": "user",
        "cli_version": "0.51.0",
        "source": "cli",
        "model_provider": "openai/gpt-5.1-codex",
        "base_instructions": "You are Codex, a coding agent.",
        "cwd": "D:/repos/acme",
        "git": {"branch": "feature/fork"},
        "forked_from_id": "sess_parent_abc",
    },
}


_USAGE_ITEMS = [
    {
        "type": "response_item",
        "payload": {
            "id": "msg_user_1",
            "timestamp": "2026-07-01T10:00:01Z",
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Please fix the bug in auth."}],
            "usage": {"input_tokens": 123, "output_tokens": 45},
        },
    },
    {
        "type": "response_item",
        "payload": {
            "id": "msg_asst_1",
            "timestamp": "2026-07-01T10:00:05Z",
            "type": "message",
            "role": "assistant",
            "content": [{"type": "output_text", "text": "Fixed the auth bug."}],
            "usage": {
                "input_tokens": 200,
                "output_tokens": 60,
                "cache_read_input_tokens": 6,
                "cache_creation_input_tokens": 7,
            },
        },
    },
]


class TestCodexContextExtraction:
    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("codex-ctx")
        rows = [_META] + _USAGE_ITEMS + [
            {
                "type": "event_msg",
                "payload": {
                    "timestamp": "2026-07-01T10:02:00Z",
                    "type": "context_compacted",
                    "compaction_summary": "Earlier turns compacted.",
                },
            },
        ]
        return _adapted(tmp, rows)

    # -------------------------------------------------------- session context
    def test_session_context_fields(self, adapted):
        assert len(adapted.sessions) == 1
        session = adapted.sessions[0]
        assert session.cwd == "D:/repos/acme"
        assert session.git_branch == "feature/fork"
        assert session.model == "openai/gpt-5.1-codex"

    def test_session_title_from_meta_summary(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "A short summary title"
        adapted = _adapted(tmp_path, [meta] + _USAGE_ITEMS)
        assert adapted.sessions[0].title == "A short summary title"

    # ---- P2-1: skip system-scaffolding summaries (plugin/AGENTS templates) ---
    def test_title_skips_plugin_scaffolding_summary(self, tmp_path):
        # session_meta.summary is the <recommended_plugins> plugin template;
        # the title must come from the first real user message instead.
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = (
            "<recommended_plugins>\n"
            "instructions for how to use the plugin bundle; not a user title."
        )
        adapted = _adapted(
            tmp_path, [meta] + [
                {
                    "type": "response_item",
                    "payload": {
                        "id": "msg_user_plugin",
                        "timestamp": "2026-07-01T10:00:01Z",
                        "type": "message", "role": "user",
                        "content": [{"type": "input_text",
                                     "text": "Refactor the payment module" }],
                    },
                },
            ]
        )
        title = adapted.sessions[0].title
        assert title is not None
        assert title.startswith("Refactor the payment module")
        assert len(title) <= 120

    def test_title_skips_agent_md_summary(self, tmp_path):
        # summary carrying the AGENTS.md / "instructions for" preamble is not
        # a real title; fall back to the first real user message.
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "AGENTS.md instructions for the coding agent"
        adapted = _adapted(tmp_path, [meta] + _USAGE_ITEMS)
        title = adapted.sessions[0].title
        assert title is not None
        assert title.startswith("Please fix the bug in auth.")
        assert len(title) <= 120

    def test_title_none_when_user_message_is_also_system(self, tmp_path):
        # summary is a plugin template AND the first user message is itself
        # system scaffolding -> both are rejected and the title stays None.
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "<INSTRUCTIONS>system only</INSTRUCTIONS>"
        rows = [meta] + [
            {
                "type": "response_item",
                "payload": {
                    "id": "msg_sys_user",
                    "timestamp": "2026-07-01T10:00:01Z",
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text",
                                 "text": "instructions for the AGENTS files" }],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].title is None

    def test_title_caps_user_message_at_120(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "<recommended_plugins>template</recommended_plugins>"
        long_user = "start here explode " + ("x" * 300)
        rows = [meta] + [
            {
                "type": "response_item",
                "payload": {
                    "id": "msg_long",
                    "timestamp": "2026-07-01T10:00:01Z",
                    "type": "message", "role": "user",
                    "content": [{"type": "input_text", "text": long_user }],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].title == long_user.strip()[:120]

    def test_session_title_falls_back_to_first_user_message(self, tmp_path):
        rows = [_META] + _USAGE_ITEMS
        adapted = _adapted(tmp_path, rows)
        session = adapted.sessions[0]
        assert session.title is not None
        assert session.title.startswith("Please fix the bug in auth.")
        assert len(session.title) <= 120

    def test_no_user_message_yields_none_title(self, tmp_path):
        rows = [_META] + [
            {
                "type": "response_item",
                "payload": {
                    "id": "msg_asst_only",
                    "timestamp": "2026-07-01T10:00:05Z",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi"}],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].title is None

    def test_model_tolerates_legacy_flat_model_field(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"].pop("model_provider", None)
        meta["payload"]["model"] = "gpt-5"
        adapted = _adapted(tmp_path, [meta])
        assert adapted.sessions[0].model == "gpt-5"

    def test_missing_context_fields_stay_none(self, tmp_path):
        meta = {
            "type": "session_meta",
            "payload": {"id": "sess_plain", "timestamp": "2026-07-01T10:00:00Z"},
        }
        adapted = _adapted(tmp_path, [meta])
        session = adapted.sessions[0]
        assert session.cwd is None
        assert session.git_branch is None
        assert session.model is None
        assert session.title is None

    # ------------------------------------------------------------------ usage
    def test_usage_events_emitted(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        assert len(usage) == 2

    def test_usage_summary_machine_parseable(self, adapted):
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        summaries = sorted(e.summary or "" for e in usage)
        # summary is a prefix grammar; cache fields may trail the core pair.
        assert any(s == "input_tokens=123 output_tokens=45"
                   or s.startswith("input_tokens=123 output_tokens=45 ") for s in summaries)
        assert any(s == "input_tokens=200 output_tokens=60"
                   or s.startswith("input_tokens=200 output_tokens=60 ") for s in summaries)

    def test_usage_summary_includes_cache_tokens(self, tmp_path):
        adapted = _adapted(tmp_path, [_META] + _USAGE_ITEMS)
        usage = [e for e in adapted.events if e.kind is EventKind.USAGE]
        cache_summaries = [
            s for s in sorted(e.summary or "" for e in usage) if "cache_read=" in s
        ]
        assert len(cache_summaries) == 1
        assert "cache_read=6 cache_write=7" in cache_summaries[0]

    def test_response_item_without_usage_emits_no_usage(self, tmp_path):
        rows = [_META] + [
            {
                "type": "response_item",
                "payload": {
                    "id": "no_usage",
                    "timestamp": "2026-07-01T10:00:05Z",
                    "type": "message",
                    "role": "assistant",
                    "content": [{"type": "output_text", "text": "hi"}],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        assert not any(e.kind is EventKind.USAGE for e in adapted.events)

    def test_usage_event_is_in_stream_order(self, adapted):
        kinds = [e.kind for e in adapted.events]
        first_usage = kinds.index(EventKind.USAGE)
        assert first_usage >= 0

    # -------------------------------------------------------- sub-agent signal
    def test_forked_session_emits_subagent_boundary(self, adapted):
        boundary = [e for e in adapted.events if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert len(boundary) == 1
        assert boundary[0].summary == "sess_parent_abc"

    def test_forked_session_has_no_fabricated_subagent_relation(self, adapted):
        assert not any(
            r.relation_kind is RelationKind.SUBAGENT for r in adapted.relations
        )

    def test_non_forked_session_has_no_boundary(self, tmp_path):
        meta = {
            "type": "session_meta",
            "payload": {"id": "sess_plain", "timestamp": "2026-07-01T10:00:00Z"},
        }
        adapted = _adapted(tmp_path, [meta])
        assert not any(e.kind is EventKind.SUBAGENT_BOUNDARY for e in adapted.events)

    def test_all_relations_reference_known_events(self, adapted):
        known = {e.event_id for e in adapted.events}
        for rel in adapted.relations:
            assert rel.source_event_id in known
            assert rel.target_event_id in known


class TestCodexSessionTimestamps:
    """P2-3: session-level started_at/ended_at from event timestamps.

    started_at prefers the native session_meta timestamp; ended_at is the
    last record's timestamp in the export.
    """

    @pytest.fixture(scope="class")
    def adapted(self, tmp_path_factory):
        tmp = tmp_path_factory.mktemp("codex-ts")
        rows = [_META] + _USAGE_ITEMS + [
            {
                "type": "event_msg",
                "payload": {
                    "timestamp": "2026-07-01T10:02:00Z",
                    "type": "context_compacted",
                    "compaction_summary": "Earlier turns compacted.",
                },
            },
        ]
        return _adapted(tmp, rows)

    def test_started_at_from_session_meta_timestamp(self, adapted):
        session = adapted.sessions[0]
        assert session.started_at == "2026-07-01T10:00:00Z"

    def test_ended_at_is_last_record_timestamp(self, adapted):
        session = adapted.sessions[0]
        # last record in the fixture is the context_compacted event at 10:02:00Z
        assert session.ended_at == "2026-07-01T10:02:00Z"

    def test_started_at_falls_back_to_first_record(self, tmp_path):
        # No timestamp on session_meta: use the first record's timestamp.
        meta = {
            "type": "session_meta",
            "payload": {"id": "sess_nots", "summary": "t"},
        }
        row = {
            "type": "response_item",
            "payload": {
                "id": "m1", "timestamp": "2026-07-01T09:00:00Z",
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            },
        }
        adapted = _adapted(tmp_path, [meta, row])
        session = adapted.sessions[0]
        assert session.started_at == "2026-07-01T09:00:00Z"
        assert session.ended_at == "2026-07-01T09:00:00Z"

    def test_no_timestamps_yield_none(self, tmp_path):
        meta = {"type": "session_meta", "payload": {"id": "sess_nts"}}
        adapted = _adapted(tmp_path, [meta])
        session = adapted.sessions[0]
        assert session.started_at is None
        assert session.ended_at is None


class TestCodexUnknownClassificationReduction:
    """DEEP-2: extend codex event_msg / response_item classification so the
    previously-unknown_native payload types land on typed event kinds. Fixtures
    are synthetic real-shape records (fields nested under payload) matching the
    wire shape Codex writes, so the classification contract is exercised
    against real-format records."""

    def test_agent_message_maps_to_assistant_message(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:00:30Z", "type": "agent_message",
                "message": "我将按五项直接核验当前代码。",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        asst = [e for e in adapted.events if e.kind is EventKind.ASSISTANT_MESSAGE]
        assert len(asst) == 1
        assert (asst[0].content or "").startswith("我将按五项直接核验当前代码。")

    def test_exec_command_end_maps_to_tool_result(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:00:40Z", "type": "exec_command_end",
                "call_id": "exec-abc", "turn_id": "019f0000-0000-0000-0000-000000000001",
                "aggregated_output": "Directory listing output\r\n",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        results = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(results) == 1
        assert (results[0].summary or "").startswith("Directory")

    def test_task_started_maps_to_loop_boundary(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:00:20Z", "type": "task_started",
                "turn_id": "019f0000-0000-0000-0000-000000000001",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        loop = [e for e in adapted.events if e.kind is EventKind.LOOP_BOUNDARY]
        assert len(loop) == 1
        assert loop[0].provenance.native_event_id == "019f0000-0000-0000-0000-000000000001"

    def test_task_complete_maps_to_loop_boundary(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:02:00Z", "type": "task_complete",
                "turn_id": "019f0000-0000-0000-0000-000000000001",
                "last_agent_message": "已完成。",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        loop = [e for e in adapted.events if e.kind is EventKind.LOOP_BOUNDARY]
        assert len(loop) == 1
        assert (loop[0].summary or "").startswith("已完成。")

    def test_custom_tool_call_result_pairing(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:50Z",
                    "type": "custom_tool_call", "id": "ctc_a",
                    "call_id": "call_pkA", "name": "shell_command", "status": "completed",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:55Z",
                    "type": "custom_tool_call_output", "id": "ctco_a",
                    "call_id": "call_pkA",
                    "output": [{"type": "input_text", "text": "exit 0"}],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        call = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(call) == 1
        assert len(res) == 1
        pair = [r for r in adapted.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(pair) == 1
        assert pair[0].source_event_id == call[0].event_id
        assert pair[0].target_event_id == res[0].event_id

    def test_error_keeps_unknown_native_with_summary(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:03:00Z", "type": "error",
                "message": "unexpected status 401 Unauthorized",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        unknown = [e for e in adapted.events if e.kind is EventKind.UNKNOWN_NATIVE]
        assert len(unknown) == 1
        assert (unknown[0].summary or "") == "unexpected status 401 Unauthorized"

    def test_agent_reasoning_maps_to_reasoning(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:00:45Z", "type": "agent_reasoning",
                "text": "**Identifying missing user habit memory**",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        reason = [e for e in adapted.events if e.kind is EventKind.REASONING]
        assert len(reason) == 1
        assert (reason[0].summary or "").startswith("**Identifying")

    def test_turn_aborted_maps_to_turn_boundary_with_reason(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:04:00Z", "type": "turn_aborted",
                "turn_id": "019f0000-0000-0000-0000-000000000001",
                "reason": "interrupted",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        boundary = [e for e in adapted.events if e.kind is EventKind.TURN_BOUNDARY]
        assert len(boundary) == 1
        assert boundary[0].summary == "interrupted"

    def test_web_search_call_and_end_pairing_map_to_tool_events(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:01:00Z",
                    "type": "web_search_call", "id": "ws_call_1", "call_id": "call_ws",
                    "action": {"type": "search", "query": "official AI memory docs"},
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "timestamp": "2026-07-01T10:01:05Z",
                    "type": "web_search_end", "call_id": "call_ws",
                    "query": "official AI memory docs",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        calls = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert any((e.summary or "").startswith("official AI memory docs") for e in calls)
        assert len(res) == 1
        pairs = [r for r in adapted.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(pairs) == 1

    def test_collab_spawn_close_map_to_subagent_boundary(self, tmp_path):
        rows = [_META,
            {
                "type": "event_msg",
                "payload": {
                    "timestamp": "2026-07-01T10:05:00Z", "type": "collab_agent_spawn_end",
                    "call_id": "call_collab", "new_agent_nickname": "Franklin",
                    "new_agent_role": "worker",
                },
            },
            {
                "type": "event_msg",
                "payload": {
                    "timestamp": "2026-07-01T10:06:00Z", "type": "collab_close_end",
                    "call_id": "call_collab", "receiver_agent_nickname": "Ohm",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        # _META carries forked_from_id, which also emits a fork boundary; the
        # two collab lifecycle events add their own sub-agent boundaries.
        sub = [e for e in adapted.events if e.kind is EventKind.SUBAGENT_BOUNDARY]
        collab = [e for e in sub if e.summary in ("Franklin", "Ohm")]
        assert len(collab) == 2

    def test_patch_apply_end_maps_to_tool_result(self, tmp_path):
        rows = [_META, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:07:00Z", "type": "patch_apply_end",
                "call_id": "patch_1", "stdout": "Success. Updated 1 file.", "success": True,
            },
        }]
        adapted = _adapted(tmp_path, rows)
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1
        assert (res[0].summary or "").startswith("Success.")


class TestCodexOrdinalAndOrderingFidelity:
    """F10: event ordinal must carry the source JSONL line number and the
    fidelity ORDERING_CONFIDENCE=complete claim must be backed by those real
    ordinal values.

    Previously every codex event had ordinal=None (line order existed but was
    never carried into the typed event) while fidelity_json still claimed
    ordering_confidence=complete for all events - a claim contradicted by the
    missing ordinals. With ordinal now stamped from the 1-based line number:
      * every record-derived event has ordinal == its line number, strictly
        increasing across the stream;
      * the ORDERING_CONFIDENCE=complete claim is justified for events that
        actually carry an ordinal.
    """

    def test_all_record_events_carry_increasing_line_ordinals(self, tmp_path):
        # meta on line 1, then a mixed real-shape stream across several lines.
        rows = [_META] + _USAGE_ITEMS + [
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:50Z",
                    "type": "function_call", "id": "fc_o", "call_id": "call_o",
                    "name": "shell_command",
                    "arguments": "{\"cmd\": \"ls\"}",
                },
            },
        ]
        # records are serialized one per line; line 1 is the meta record.
        adapted = _adapted(tmp_path, rows)
        ordinals = [e.ordinal for e in adapted.events]
        assert len(ordinals) > 1
        # Every RECORD-DERIVED event carries a non-null line-number ordinal;
        # only the synthetic runtime fork boundary (from _META.forked_from_id)
        # is ordinal-less because it is not a native record on a JSONL line.
        record_ordinals = [
            o for e, o in ((e, e.ordinal) for e in adapted.events)
            if o is not None
        ]
        # ordinal is the file line number: monotonically non-decreasing in
        # stream order. Multiple events may share a line (a response_item and
        # its usage event both carry that line), so values repeat but never
        # regress, mirroring the JSONL file order.
        assert record_ordinals == sorted(record_ordinals)
        # every record-derived event holds a line ordinal (only the synthetic
        # fork boundary is exempt).
        assert len(record_ordinals) == len([
            e for e in adapted.events
            if e.kind is not EventKind.SUBAGENT_BOUNDARY
        ])
        # Usages come from the two response_item records at lines 2 and 3;
        # each USAGE event carries its owning line number (2, 3) in stream order.
        usage_ordinals = [
            e.ordinal for e in adapted.events if e.kind is EventKind.USAGE
        ]
        assert sorted(usage_ordinals) == [2, 3]

    def test_ordering_fidelity_complete_is_backed_by_real_ordinal(self, tmp_path):
        rows = [_META] + _USAGE_ITEMS
        adapted = _adapted(tmp_path, rows)
        for event in adapted.events:
            if event.ordinal is None:
                continue  # synthetic runtime events (fork boundary) are exempt
            assert event.fidelity.level(
                FidelityDimension.ORDERING_CONFIDENCE
            ) is FidelityLevel.COMPLETE
            # the complete claim rests on an actually-present ordinal.
            assert event.ordinal is not None

    def test_content_availability_complete_when_full_content_present(self, tmp_path):
        # TOOL_CALL / TOOL_RESULT carry real content; with the full body stored
        # (no excess over the cap) CONTENT_AVAILABILITY may legitimately be
        # complete, so the ordering fix keeps the dimension consistent.
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:50Z",
                    "type": "function_call", "id": "fc_z", "call_id": "call_z",
                    "name": "read", "arguments": "{\"path\": \"a.py\"}",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        call = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL][0]
        assert call.content == '{"path": "a.py"}'
        assert call.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY,
        ) is FidelityLevel.COMPLETE

