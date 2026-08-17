"""Phase P0-F1: Codex tool-content fidelity + concrete model + title placeholders.

Red-to-green contract for the codex adapter fidelity fixes:

  1. TOOL_CALL events carry the real tool input as "content"
     (function_call.arguments / custom_tool_call.input), not just a name summary.
  2. TOOL_RESULT events carry the execution output as "content"
     (function_call_output.output, string or content-block list), capped at a
     generous ceiling with a field disposition when truncated.
  3. AdaptedSession.model is the concrete model (turn_context.payload.model /
     thread_settings_applied.payload.thread_settings.model), not the coarse
     model_provider name, falling back to the provider only when needed.
  4. Session title never collides with system-injected Codex scaffolding
     ('The following is the Codex agent history...', '[Assistant Rules]').

Fixtures are synthetic real-shape records (fields nested under payload) so the
contract is exercised against the wire shape Codex writes.
"""

from __future__ import annotations

from pathlib import Path
import json

from personal_knowledge.adapters.conversation_sources import codex
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import capture_file
from personal_knowledge.core.conversation_events import (
    EventKind,
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
        "id": "sess_p0f1_01",
        "timestamp": "2026-07-01T10:00:00Z",
        "model_provider": "openai",
    },
}


class TestCodexToolContentFidelity:
    """P0-F1: tool_call / tool_result carry real content, not just name/summary."""

    def test_tool_call_content_is_arguments(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:50Z",
                    "type": "function_call", "id": "fc_a",
                    "call_id": "call_tcA", "name": "shell_command",
                    "arguments": "{\"command\": \"git status\"}",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        call = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        assert len(call) == 1
        assert call[0].content == "{\"command\": \"git status\"}"
        assert call[0].summary == "shell_command"

    def test_custom_tool_call_content_is_input(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:51Z",
                    "type": "custom_tool_call", "id": "ctc_a",
                    "call_id": "call_ctA", "name": "exec",
                    "input": "const x = 1;",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        call = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL]
        assert len(call) == 1
        assert call[0].content == "const x = 1;"
        assert call[0].summary == "exec"

    def test_tool_result_content_is_output(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:55Z",
                    "type": "function_call_output", "id": "fco_a",
                    "call_id": "call_tcA",
                    "output": "Exit code: 0\nOutput:\nchanged",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1
        assert res[0].content == "Exit code: 0\nOutput:\nchanged"

    def test_tool_result_output_content_block_list(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:56Z",
                    "type": "function_call_output", "id": "fco_b",
                    "call_id": "call_tcB",
                    "output": [
                        {"type": "input_text", "text": "Script completed"},
                        {"type": "input_text", "text": "Ok"},
                    ],
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1
        assert res[0].content == "Script completed Ok"

    def test_tool_result_output_truncation_records_disposition(self, tmp_path):
        big = "x" * (100_000 + 5)
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:57Z",
                    "type": "function_call_output", "id": "fco_c",
                    "call_id": "call_tcC", "output": big,
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT]
        assert len(res) == 1
        assert len(res[0].content or "") == 100_000
        dispo = [d for d in res[0].field_dispositions
                 if d.disposition is FieldDisposition.MAPPED
                 and "truncated" in d.reason]
        assert dispo, "a truncation field disposition must be recorded"

    def test_tool_call_and_result_pair_preserved_with_content(self, tmp_path):
        rows = [_META,
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:58Z",
                    "type": "function_call", "id": "fc_d",
                    "call_id": "call_tcD", "name": "read",
                    "arguments": "{\"path\": \"a.py\"}",
                },
            },
            {
                "type": "response_item",
                "payload": {
                    "timestamp": "2026-07-01T10:00:59Z",
                    "type": "function_call_output", "id": "fco_d",
                    "call_id": "call_tcD", "output": "contents",
                },
            },
        ]
        adapted = _adapted(tmp_path, rows)
        call = [e for e in adapted.events if e.kind is EventKind.TOOL_CALL][0]
        res = [e for e in adapted.events if e.kind is EventKind.TOOL_RESULT][0]
        pair = [r for r in adapted.relations if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(pair) == 1
        assert pair[0].source_event_id == call.event_id
        assert pair[0].target_event_id == res.event_id
        assert call.content == "{\"path\": \"a.py\"}"
        assert res.content == "contents"


class TestCodexModelFidelity:
    """P0-F1: session.model is the concrete model, not the provider name."""

    def test_model_from_turn_context(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["model_provider"] = "openai"
        meta["payload"].pop("model", None)
        rows = [meta, {
            "type": "turn_context",
            "payload": {
                "turn_id": "019f0000-0000-0000-0000-000000000001",
                "cwd": "D:/repos/acme",
                "model": "gpt-5.6-luna",
            },
        }]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].model == "gpt-5.6-luna"

    def test_model_from_thread_settings(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["model_provider"] = "codex"
        meta["payload"].pop("model", None)
        rows = [meta, {
            "type": "event_msg",
            "payload": {
                "timestamp": "2026-07-01T10:00:20Z",
                "type": "thread_settings_applied",
                "thread_settings": {"model": "codex-auto-review"},
            },
        }]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].model == "codex-auto-review"

    def test_model_falls_back_to_provider_when_no_concrete(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["model_provider"] = "openai/gpt-5.1-codex"
        meta["payload"].pop("model", None)
        adapted = _adapted(tmp_path, [meta])
        assert adapted.sessions[0].model == "openai/gpt-5.1-codex"

    def test_session_meta_flat_model_still_used(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"].pop("model_provider", None)
        meta["payload"]["model"] = "gpt-5"
        adapted = _adapted(tmp_path, [meta])
        assert adapted.sessions[0].model == "gpt-5"


class TestCodexTitlePlaceholderFidelity:
    """P0-F1: the title must not be system-injected Codex scaffolding."""

    def test_title_skips_codex_agent_history_preamble(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "The following is the Codex agent history as observed by the user."
        rows = [meta, {
            "type": "response_item",
            "payload": {
                "id": "msg_user_a",
                "timestamp": "2026-07-01T10:00:01Z",
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Explain the git flow"}],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        title = adapted.sessions[0].title
        assert title is not None
        assert title.startswith("Explain the git flow")

    def test_title_skips_assistant_rules_directive(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "stale summary"
        rows = [meta, {
            "type": "response_item",
            "payload": {
                "id": "msg_sys_b",
                "timestamp": "2026-07-01T10:00:01Z",
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "[Assistant Rules]\nYou are a coding agent."}],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        title = adapted.sessions[0].title
        assert title is None or not title.lower().startswith("[assistant rules")

    def test_title_from_real_user_message_when_meta_is_placeholder(self, tmp_path):
        meta = json.loads(json.dumps(_META))
        meta["payload"]["summary"] = "The following is the Codex agent history observed by the user."
        rows = [meta, {
            "type": "response_item",
            "payload": {
                "id": "msg_user_real",
                "timestamp": "2026-07-01T10:00:01Z",
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": "Refactor the auth module"}],
            },
        }]
        adapted = _adapted(tmp_path, rows)
        assert adapted.sessions[0].title.startswith("Refactor the auth module")