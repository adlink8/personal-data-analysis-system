"""Agent F - Copilot/Cursor/Grok/Mimo-OpenCode context extraction (RED).

Extends the four family adapters to surface session-context attributes
(cwd / title), machine-parseable USAGE events from token fields, and
- for Grok - a COMPACTED_RANGE relation when a compaction marker file is
present. All fixtures are synthetic, hand-written and redacted.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from personal_knowledge.adapters.conversation_sources import (
    copilot,
    cursor,
    grok,
    mimo_opencode,
    workbuddy_kimi,
    zcode,
)
from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_directory,
    capture_file,
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import (
    EventKind,
    FidelityDimension,
    FidelityLevel,
    FieldDisposition,
    RelationKind,
)


def _capture_jsonl(tmp_path, name, rows):
    src = tmp_path / name
    src.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        src, tmp_path / "capture", relative_path=name,
        byte_limit=1000000, count_limit=1,
    )
    return SourceArtifactSet((artifact,)), blob.parent


class TestCopilotContext:
    def test_cwd_title_and_usage(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0",
             "data": {"sessionId": "s", "cwd": "D:/proj/alpha"}},
            {"type": "user.message", "session_id": "s", "id": "u",
             "timestamp": "t1",
             "data": {"messageId": "u",
                       "content": "Help me refactor the parser"}},
            {"type": "assistant.message", "session_id": "s", "id": "a",
             "timestamp": "t2",
             "data": {"messageId": "a", "content": "Here is a plan"}},
            {"type": "usage", "session_id": "s", "id": "usage-1",
             "timestamp": "t3",
             "data": {"input_tokens": 123, "output_tokens": 45}},
            {"type": "session.shutdown", "session_id": "s", "id": "end",
             "timestamp": "t4", "data": {}},
        ]
        artifact_set, root = _capture_jsonl(tmp_path, "copilot_ctx.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].cwd == "D:/proj/alpha"
        assert result.sessions[0].title == "Help me refactor the parser"
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert "input_tokens=123" in (usages[0].summary or "")
        assert "output_tokens=45" in (usages[0].summary or "")
    def test_tool_pairing_and_boundaries(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0",
             "data": {"sessionId": "s", "context": {"cwd": "C:/repo/x"}}},
            {"type": "assistant.turn_start", "session_id": "s", "id": "ts1",
             "timestamp": "t1", "data": {"turnId": "0"}},
            {"type": "tool.execution_start", "session_id": "s", "id": "e1",
             "timestamp": "t2",
             "data": {"toolCallId": "call_1", "toolName": "edit",
                       "arguments": {"path": "a.py"}}},
            {"type": "tool.execution_complete", "session_id": "s", "id": "c1",
             "timestamp": "t3",
             "data": {"toolCallId": "call_1", "toolName": "edit",
                       "success": True, "result": {"content": "done"}}},
            {"type": "assistant.turn_end", "session_id": "s", "id": "te1",
             "timestamp": "t4", "data": {"turnId": "0"}},
        ]
        artifact_set, root = _capture_jsonl(
            tmp_path, "copilot_dotted.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        calls = [e for e in result.events if e.kind is EventKind.TOOL_CALL]
        results = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        boundaries = [e for e in result.events
                      if e.kind is EventKind.TURN_BOUNDARY]
        assert len(calls) == 1
        assert len(results) == 1
        assert len(boundaries) == 2
        rels = [r for r in result.relations
                if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rels) == 1
        assert rels[0].source_event_id == calls[0].event_id
        assert rels[0].target_event_id == results[0].event_id
        assert result.sessions[0].cwd == "C:/repo/x"

    def test_unpaired_tool_call_is_partial(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0", "data": {"sessionId": "s"}},
            {"type": "tool.execution_start", "session_id": "s", "id": "e1",
             "timestamp": "t1",
             "data": {"toolCallId": "call_orphan", "toolName": "powershell"}},
        ]
        artifact_set, root = _capture_jsonl(
            tmp_path, "copilot_orphan.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        calls = [e for e in result.events if e.kind is EventKind.TOOL_CALL]
        assert len(calls) == 1
        # an orphaned TOOL_CALL must advertise bounded fidelity on itself
        assert calls[0].fidelity.level(
            FidelityDimension.RELATION_COMPLETENESS) is FidelityLevel.PARTIAL
        assert not calls[0].fidelity.is_complete()
        assert result.fidelity.has_loss()
        assert any(w.startswith("tool ") for w in result.warnings)

    def test_compaction_and_subagent(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0", "data": {"sessionId": "s"}},
            {"type": "session.compaction_start", "session_id": "s",
             "id": "cp1", "timestamp": "t1",
             "data": {"summary": "Summarised earlier turns about ETL"}},
            {"type": "session.compaction_complete", "session_id": "s",
             "id": "cp2", "timestamp": "t2", "data": {}},
            {"type": "subagent.started", "session_id": "s", "id": "sa1",
             "timestamp": "t3",
             "data": {"toolCallId": "call_sub", "agentName": "task"}},
            {"type": "subagent.failed", "session_id": "s", "id": "sf1",
             "timestamp": "t4",
             "data": {"toolCallId": "call_sub", "agentName": "task",
                       "error": "boom"}},
        ]
        artifact_set, root = _capture_jsonl(
            tmp_path, "copilot_comp.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        compactions = [e for e in result.events
                       if e.kind is EventKind.COMPACTION_SUMMARY]
        assert len(compactions) == 2
        assert any("Summarised earlier turns" in (c.summary or "")
                   for c in compactions)
        subagents = [e for e in result.events
                     if e.kind is EventKind.SUBAGENT_BOUNDARY]
        assert len(subagents) == 2
        for sub in subagents:
            assert (sub.summary or "").startswith("call_sub")

    def test_title_excludes_system_prompt(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0", "data": {"sessionId": "s"}},
            {"type": "user.message", "session_id": "s", "id": "sys",
             "timestamp": "t1",
             "data": {"messageId": "sys",
                       "content": "[Assistant Rules] You are a coding agent"}},
            {"type": "user.message", "session_id": "s", "id": "u",
             "timestamp": "t2",
             "data": {"messageId": "u",
                       "content": "Refactor the parser module"}},
        ]
        artifact_set, root = _capture_jsonl(
            tmp_path, "copilot_title.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        assert result.sessions[0].title == "Refactor the parser module"

    def test_session_started_ended_and_model(self, tmp_path):
        rows = [
            {"type": "session.start", "session_id": "s", "id": "s",
             "timestamp": "t0",
             "data": {"sessionId": "s",
                       "context": {"cwd": "C:/repo", "gitRoot": "C:/repo",
                                    "branch": "main"}}},
            {"type": "session.info", "session_id": "s", "id": "si",
             "timestamp": "t1",
             "data": {"infoType": "model",
                       "message": "Model changed to: Gemini 3 Pro"}},
            {"type": "user.message", "session_id": "s", "id": "u",
             "timestamp": "t2",
             "data": {"messageId": "u", "content": "hi"}},
            {"type": "session.shutdown", "session_id": "s", "id": "end",
             "timestamp": "t9", "data": {}},
        ]
        artifact_set, root = _capture_jsonl(
            tmp_path, "copilot_times.jsonl", rows)
        result = copilot.adapt(artifact_set, artifact_root=root)
        session = result.sessions[0]
        assert session.cwd == "C:/repo"
        assert session.started_at == "t0"
        assert session.ended_at == "t9"
        assert session.model and "Gemini" in session.model
        assert session.git_branch == "main"



class TestCursorContext:
    def test_jsonl_project_cwd_title_and_usage(self, tmp_path):
        rows = [
            {"role": "user", "message": {"content": "optimize the build"}},
            {"role": "assistant", "message": {"content": "done"}},
            {"role": "assistant", "message": {"content": "usage done"},
             "usage": {"input_tokens": 11, "output_tokens": 22}},
        ]
        src = tmp_path / "agent-transcripts" / "proj-web" / "abc" / "t.jsonl"
        src.parent.mkdir(parents=True)
        src.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "cap",
            relative_path="agent-transcripts/proj-web/abc/t.jsonl",
            byte_limit=1000000, count_limit=1,
        )
        result = cursor.adapt(SourceArtifactSet((artifact,)), artifact_root=blob.parent)
        assert len(result.sessions) == 1
        assert result.sessions[0].cwd == "proj-web"
        assert result.sessions[0].title == "optimize the build"
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert "input_tokens=11" in (usages[0].summary or "")

    def test_jsonl_record_model_extraction(self, tmp_path):
        # A transcript that carries an explicit model field must surface it
        # on the session (Red for the missing model extraction).
        rows = [
            {"role": "user", "message": {"content": "hello"}},
            {"role": "assistant", "message": {"content": "ok"},
             "model": "claude-opus"},
        ]
        src = tmp_path / "agent-transcripts" / "proj-x" / "abc" / "t.jsonl"
        src.parent.mkdir(parents=True)
        src.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        artifact, blob = capture_file(
            src, tmp_path / "cap",
            relative_path="agent-transcripts/proj-x/abc/t.jsonl",
            byte_limit=1000000, count_limit=1,
        )
        result = cursor.adapt(SourceArtifactSet((artifact,)), artifact_root=blob.parent)
        assert result.sessions[0].model == "claude-opus"


def _capture_dir(tmp_path, files):
    src = tmp_path / "grok_ctx"
    src.mkdir(parents=True)
    for rel, text in files.items():
        p = src / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    _m, artifacts = capture_directory(
        src, tmp_path / "cap", include_relative=tuple(files),
        byte_limit=1000000, count_limit=20,
    )
    return SourceArtifactSet(artifacts), (tmp_path / "cap" / "artifacts")


class TestGrokContext:
    def test_cwd_title_usage_and_compacted_range(self, tmp_path):
        files = {
            "summary.json": json.dumps({
                "info": {"id": "gk-1", "project": "D:/repo/ml",
                          "title": "train the model"},
                "created_at": "t0", "updated_at": "t1",
                "session_summary": "Compacted earlier turns about ETL",
            }),
            "chat_history.jsonl": "\n".join([
                json.dumps({"role": "user", "content": "first user prompt",
                            "id": "c0", "timestamp": "t0"}),
                json.dumps({"role": "assistant", "content": "ok", "id": "c1",
                            "timestamp": "t1",
                            "usage": {"input_tokens": 5, "output_tokens": 9}}),
            ]) + "\n",
            "compaction.md": "# Compaction\nSummarised earlier rounds.",
        }
        artifact_set, root = _capture_dir(tmp_path, files)
        result = grok.adapt(artifact_set, artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].cwd == "D:/repo/ml"
        assert result.sessions[0].title == "train the model"
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert "input_tokens=5" in (usages[0].summary or "")
        compactions = [e for e in result.events if
                      e.kind is EventKind.COMPACTION_SUMMARY]
        assert any("Summarised earlier rounds" in (c.summary or "")
                   for c in compactions)
        ranges = [r for r in result.relations
                  if r.relation_kind is RelationKind.COMPACTED_RANGE]
        assert len(ranges) >= 1
        known = {e.event_id for e in result.events}
        for rel in ranges:
            assert rel.source_event_id in known
            assert rel.target_event_id in known

    def test_cwd_via_info_cwd_and_chat_model(self, tmp_path):
        # Native Grok exports put the working directory in info.cwd (not
        # info.project) and record model_id per assistant row. Verifying the
        # real field names surfaces both the cwd field-name fix and model.
        files = {
            "summary.json": json.dumps({
                "info": {"id": "gk-2", "cwd": "D:/repo/native"},
                "created_at": "t0", "updated_at": "t1",
                "session_summary": "native cwd layout",
            }),
            "chat_history.jsonl": "\n".join([
                json.dumps({"role": "user", "content": "set things up",
                            "id": "c0", "timestamp": "t0"}),
                json.dumps({"role": "assistant", "content": "ok", "id": "c1",
                            "timestamp": "t1", "model_id": "grok-4.5",
                            "usage": {"input_tokens": 2, "output_tokens": 1}}),
            ]) + "\n",
        }
        artifact_set, root = _capture_dir(tmp_path, files)
        result = grok.adapt(artifact_set, artifact_root=root)
        assert result.sessions[0].cwd == "D:/repo/native"
        assert result.sessions[0].model == "grok-4.5"
    def test_model_and_branch_from_summary_json(self, tmp_path):
        # Real Grok exports carry the current model at top-level
        # current_model_id and the git branch at top-level head_branch (both
        # outside info). They must surface on AdaptedSession.model / git_branch
        # so the fidelity audit stops reporting them as missing.
        files = {
            "summary.json": json.dumps({
                "info": {"id": "gk-3", "cwd": "D:/repo/native"},
                "current_model_id": "grok-4.5",
                "head_branch": "chore/ci-and-full-tests",
                "created_at": "t0", "updated_at": "t1",
                "session_summary": "native model+branch layout",
            }),
            "chat_history.jsonl": "\n".join([
                json.dumps({"role": "user", "content": "set things up",
                            "id": "c0", "timestamp": "t0"}),
                json.dumps({"role": "assistant", "content": "ok", "id": "c1",
                            "timestamp": "t1",
                            "usage": {"input_tokens": 2, "output_tokens": 1}}),
            ]) + "\n",
        }
        artifact_set, root = _capture_dir(tmp_path, files)
        result = grok.adapt(artifact_set, artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].model == "grok-4.5"
        assert result.sessions[0].git_branch == "chore/ci-and-full-tests"

    def test_branch_fallback_via_info(self, tmp_path):
        # Some Grok variants keep head_branch inside info; the adapter must
        # fall back so a schema rename never silently drops the branch.
        files = {
            "summary.json": json.dumps({
                "info": {"id": "gk-4", "cwd": "D:/repo/native",
                          "head_branch": "main"},
                "current_model_id": "grok-4.5",
                "created_at": "t0", "updated_at": "t1",
                "session_summary": "info-scoped branch layout",
            }),
        }
        artifact_set, root = _capture_dir(tmp_path, files)
        result = grok.adapt(artifact_set, artifact_root=root)
        assert result.sessions[0].git_branch == "main"



def _make_sqlite(path, *, model=None):
    con = sqlite3.connect(str(path))
    con.executescript(
        "CREATE TABLE sessions (id TEXT, title TEXT, cwd TEXT, model TEXT, created_at TEXT);"
        "CREATE TABLE messages (id TEXT, session_id TEXT, role TEXT, "
        "                       content TEXT, created_at TEXT, usage TEXT);"
        "CREATE TABLE message_parts (id TEXT, message_id TEXT, "
        "                            part_type TEXT, content TEXT, created_at TEXT);"
    )
    con.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?)",
        ("s1", "training run", "D:/data/proj", model, "t0"),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?)",
        ("m1", "s1", "user", "refactor the module", "t1", None),
    )
    con.execute(
        "INSERT INTO messages VALUES (?,?,?,?,?,?)",
        ("m2", "s1", "assistant", "ok", "t2",
         json.dumps({"input_tokens": 7, "output_tokens": 3})),
    )
    con.commit()
    con.close()


def _capture_sqlite(tmp_path, *, model=None):
    src = tmp_path / "store.sqlite"
    _make_sqlite(src, model=model)
    artifact, blob = capture_sqlite(
        src, tmp_path / "cap",
        allowed_tables=("sessions", "messages", "message_parts"),
        allowed_columns={
            "sessions": ("id", "title", "cwd", "model", "created_at"),
            "messages": ("id", "session_id", "role", "content",
                          "created_at", "usage"),
            "message_parts": ("id", "message_id", "part_type", "content",
                               "created_at"),
        },
        byte_limit=1000000, count_limit=3,
    )
    return SourceArtifactSet((artifact,)), blob.parent


# Real Mimo/OpenCode export a live session/message/part shape where usage is a
# part.data["tokens"] aggregate: {"total":..., "input":..., "output":...,
# "cache": {"read":..., "write":...}}. This captures that live wire layout.
_LIVE_TABLES = ("session", "message", "part")
_LIVE_COLUMNS = {
    "session": ("id", "parent_id", "title", "time_created", "time_updated",
                "time_compacting"),
    "message": ("id", "session_id", "time_created", "time_updated", "data"),
    "part": ("id", "message_id", "session_id", "time_created", "time_updated",
             "data"),
}


def _capture_live_sqlite(tmp_path, rows):
    db = tmp_path / "live.sqlite"
    con = sqlite3.connect(str(db))
    con.executescript(
        "CREATE TABLE session (id TEXT, parent_id TEXT, title TEXT,"
        " time_created TEXT, time_updated TEXT, time_compacting TEXT);"
        "CREATE TABLE message (id TEXT, session_id TEXT, time_created TEXT,"
        " time_updated TEXT, data TEXT);"
        "CREATE TABLE part (id TEXT, message_id TEXT, session_id TEXT,"
        " time_created TEXT, time_updated TEXT, data TEXT);"
    )
    con.execute("INSERT INTO session VALUES (?,?,?,?,?,?)",
                ("s_live", None, "live mimo run", "t0", None, None))
    for msg in rows["messages"]:
        con.execute("INSERT INTO message VALUES (?,?,?,?,?)", msg)
    for part in rows["parts"]:
        con.execute("INSERT INTO part VALUES (?,?,?,?,?,?)", part)
    con.commit()
    con.close()
    artifact, blob = capture_sqlite(
        db, tmp_path / "cap", allowed_tables=_LIVE_TABLES,
        allowed_columns=_LIVE_COLUMNS,
        byte_limit=1000000, count_limit=8,
    )
    return SourceArtifactSet((artifact,)), blob.parent


_LIVE_MESSAGE = lambda sid, m, role: (m, sid, "t1", None,
                                         json.dumps({"role": role}))
_LIVE_ASSISTANT_PART = lambda pid, mid, sid, tokens: (
    pid, mid, sid, "t2", None,
    json.dumps({"type": "step-finish", "reason": "stop", "tokens": tokens}))


class TestMimoContext:
    def test_session_title_cwd_model_and_usage(self, tmp_path):
        artifact_set, root = _capture_sqlite(tmp_path, model="deepseek-v3")
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].title == "training run"
        assert result.sessions[0].cwd == "D:/data/proj"
        assert result.sessions[0].model == "deepseek-v3"
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert "input_tokens=7" in (usages[0].summary or "")
        assert "output_tokens=3" in (usages[0].summary or "")

    def test_model_json_id_extraction(self, tmp_path):
        # Some sqlite stores hold the model as a JSON blob; the dataset must
        # expose its ``id`` rather than the raw JSON. (Red for the JSON path.)
        artifact_set, root = _capture_sqlite(
            tmp_path, model=json.dumps({"id": "gpt-5", "providerID": "x"}),
        )
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        assert result.sessions[0].model == "gpt-5"


    def test_part_tokens_usage_canonical(self, tmp_path):
        # Real Mimo live wire carries usage as part.data tokens on a
        # step-finish part; assert the canonical input_tokens= form.
        rows = {}
        rows['messages'] = []
        rows['parts'] = []
        rows['messages'].append(_LIVE_MESSAGE('s_live', 'm_u', 'user'))
        rows['messages'].append(_LIVE_MESSAGE('s_live', 'm_a', 'assistant'))
        tokens = {'total': 41943, 'input': 307, 'output': 253,
                  'reasoning': 231,
                  'cache': {'write': 0, 'read': 41152}}
        rows['parts'].append(_LIVE_ASSISTANT_PART('p1', 'm_a', 's_live', tokens))
        artifact_set, root = _capture_live_sqlite(tmp_path, rows)
        result = mimo_opencode.adapt('mimo', artifact_set, artifact_root=root)
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert usages[0].content is None
        s = usages[0].summary or ''
        assert s.startswith('input_tokens=')
        assert 'input_tokens=307' in s
        assert 'output_tokens=253' in s
        assert 'cache_read=41152' in s
        assert 'reasoning=' not in s

class TestOpenCodeContext:
    def test_session_title_cwd_model_and_usage(self, tmp_path):
        artifact_set, root = _capture_sqlite(tmp_path, model="claude-sonnet")
        result = mimo_opencode.adapt("opencode", artifact_set, artifact_root=root)
        assert len(result.sessions) == 1
        assert result.sessions[0].title == "training run"
        assert result.sessions[0].cwd == "D:/data/proj"
        assert result.sessions[0].model == "claude-sonnet"
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert len(usages) == 1
        assert "input_tokens=7" in (usages[0].summary or "")
        assert "output_tokens=3" in (usages[0].summary or "")


_LIVE_TOOL_MSG = lambda sid, m, role, path=None: (
    m, sid, "t1", None,
    json.dumps({"role": role, "path": path} if path else {"role": role}))
_LIVE_TOOL_PART = lambda pid, mid, sid, tool, state: (
    pid, mid, sid, "t2", None,
    json.dumps({"type": "tool", "callID": "call_t", "tool": tool, "state": state}))


class TestMimoToolContext:
    def test_tool_call_content_and_result_output(self, tmp_path):
        # Real Mimo tool part carries arguments in state.input and the result
        # in state.output; both must land in canonical content, not be dropped.
        rows = {
            "messages": [
                _LIVE_TOOL_MSG("s_live", "m_u", "user"),
                _LIVE_TOOL_MSG("s_live", "m_a", "assistant"),
            ],
            "parts": [
                _LIVE_TOOL_PART("p_t", "m_a", "s_live", "Read", {
                    "status": "completed",
                    "input": {"file_path": "C:/repo/a.py"},
                    "output": "1\tfoo"},
                ),
            ],
        }
        artifact_set, root = _capture_live_sqlite(tmp_path, rows)
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        calls = [e for e in result.events if e.kind is EventKind.TOOL_CALL]
        results = [e for e in result.events if e.kind is EventKind.TOOL_RESULT]
        assert len(calls) == 1
        assert len(results) == 1
        # tool arguments surface as content (not dropped)
        assert calls[0].content and "file_path" in calls[0].content
        assert calls[0].content and "C:/repo/a.py" in calls[0].content
        # tool result output surfaces as content
        assert results[0].content and "foo" in results[0].content
        # args were actually captured -> complete content availability
        assert calls[0].fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE
        # a CALL_RESULT relation links them
        rels = [r for r in result.relations
                if r.relation_kind is RelationKind.CALL_RESULT]
        assert len(rels) == 1
        assert rels[0].source_event_id == calls[0].event_id
        assert rels[0].target_event_id == results[0].event_id

    def test_tool_call_missing_args_is_partial_with_disposition(self, tmp_path):
        # A tool part whose arguments could not be mapped must NOT advertise
        # complete content availability; it must be partial + a field
        # disposition.
        rows = {
            "messages": [
                _LIVE_TOOL_MSG("s_live", "m_u", "user"),
                _LIVE_TOOL_MSG("s_live", "m_a", "assistant"),
            ],
            "parts": [
                _LIVE_TOOL_PART("p_t", "m_a", "s_live", "Read", {
                    "status": "completed", "output": "done"}),
            ],
        }
        artifact_set, root = _capture_live_sqlite(tmp_path, rows)
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        call = next(e for e in result.events if e.kind is EventKind.TOOL_CALL)
        assert call.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.PARTIAL
        assert not call.fidelity.is_complete()
        assert call.field_dispositions
        assert any(d.field_name in ("state.input", "input", "arguments")
                   for d in call.field_dispositions)

    def test_cwd_extracted_from_message_path(self, tmp_path):
        # Real Mimo live messages carry cwd under data.path.cwd; the session
        # must surface it.
        rows = {
            "messages": [
                _LIVE_TOOL_MSG("s_live", "m_u", "user",
                               {"cwd": "D:/proj/alpha", "root": "D:/proj/alpha"}),
            ],
            "parts": [],
        }
        artifact_set, root = _capture_live_sqlite(tmp_path, rows)
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        assert result.sessions[0].cwd == "D:/proj/alpha"

class TestUnifiedUsageFormat:
    # every USAGE summary must follow the canonical grammar
    # input_tokens=X output_tokens=Y [cache_read=Z cache_write=W].
    def _check(self, result):
        usages = [e for e in result.events if e.kind is EventKind.USAGE]
        assert usages, 'expected at least one USAGE event'
        for u in usages:
            assert u.summary, 'USAGE event summary must not be empty'
            assert u.summary.startswith('input_tokens='), u.summary
    def test_grok(self, tmp_path):
        rows = [
            {'role': 'user', 'content': 'u', 'id': 'c0', 'timestamp': 't0'},
            {'role': 'assistant', 'content': 'a', 'id': 'c1', 'timestamp': 't1',
             'usage': {'input': 5, 'output': 9, 'cacheRead': 2}},
        ]
        aset, root = _capture_jsonl(tmp_path, 'chat_history.jsonl', rows)
        self._check(grok.adapt(aset, artifact_root=root))
    def test_copilot(self, tmp_path):
        rows = [
            {'type': 'session.start', 'session_id': 's', 'id': 's', 'timestamp': 't0', 'data': {}},
            {'type': 'usage', 'session_id': 's', 'id': 'u1', 'timestamp': 't1',
             'data': {'input_tokens': 123, 'output_tokens': 45, 'cache_read': 6}},
        ]
        aset, root = _capture_jsonl(tmp_path, 'cp_use.jsonl', rows)
        self._check(copilot.adapt(aset, artifact_root=root))
    def test_kimi(self, tmp_path):
        rows = [
            {'type': 'usage.record', 'time': 't0', 'session_id': 'k1',
             'usage': {'inputOther': 100, 'output': 12, 'inputCacheRead': 30, 'inputCacheCreation': 2}},
        ]
        aset, root = _capture_jsonl(tmp_path, 'kimi_use.jsonl', rows)
        self._check(workbuddy_kimi.adapt('kimi', aset, artifact_root=root))


_LIVE_REASONING_PART = lambda pid, mid, sid, text: (
    pid, mid, sid, "t2", None,
    json.dumps({"type": "reasoning", "text": text}))


class TestMimoReasoningContext:
    # Reasoning parts must carry the full reasoning text in canonical content
    # (not be dropped), with a 2048-char summary and explicit MAPPED/REDACTED
    # dispositions plus matching CONTENT_AVAILABILITY fidelity. (F7)
    def _session(self, tmp_path, part):
        rows = {
            "messages": [
                _LIVE_MESSAGE("s_live", "m_u", "user"),
                _LIVE_MESSAGE("s_live", "m_a", "assistant"),
            ],
            "parts": [part],
        }
        artifact_set, root = _capture_live_sqlite(tmp_path, rows)
        result = mimo_opencode.adapt("mimo", artifact_set, artifact_root=root)
        reasons = [e for e in result.events if e.kind is EventKind.REASONING]
        assert len(reasons) == 1
        return reasons[0]

    def test_reasoning_content_not_dropped(self, tmp_path):
        text = "Let me think about the refactor. " * 50
        ev = self._session(tmp_path, _LIVE_REASONING_PART(
            "p_r", "m_a", "s_live", text))
        assert ev.content == text
        assert ev.summary == text[:2048]
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE
        assert ev.fidelity.is_complete()
        assert ev.field_dispositions
        assert any(
            d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions)

    def test_reasoning_over_limit_redacted_partial(self, tmp_path):
        # Real Mimo reasoning can exceed the canonical content cap; the
        # overrun must be honestly declared REDACTED + partial, never silently
        # truncated while advertising complete content availability.
        text = "x" * (100_000 + 100)
        ev = self._session(tmp_path, _LIVE_REASONING_PART(
            "p_r", "m_a", "s_live", text))
        assert len(ev.content) == 100_000
        assert ev.content == text[:100_000]
        assert ev.summary == text[:2048]
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.PARTIAL
        assert not ev.fidelity.is_complete()
        assert any(
            d.disposition is FieldDisposition.REDACTED
            for d in ev.field_dispositions)

    def test_reasoning_exact_limit_not_redacted(self, tmp_path):
        # At the cap the full text is retained in content and stays MAPPED.
        text = "y" * 100_000
        ev = self._session(tmp_path, _LIVE_REASONING_PART(
            "p_r", "m_a", "s_live", text))
        assert ev.content == text
        assert ev.fidelity.level(
            FidelityDimension.CONTENT_AVAILABILITY) is FidelityLevel.COMPLETE
        assert any(
            d.disposition is FieldDisposition.MAPPED
            for d in ev.field_dispositions)
        assert not any(
            d.disposition is FieldDisposition.REDACTED
            for d in ev.field_dispositions)

