"""Exact message-body contract shared by conversation source adapters."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.adapters.conversation_sources.contracts import (
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.registry import adapt_for
from personal_knowledge.adapters.conversation_sources import mimo_opencode, zcode
from personal_knowledge.adapters.conversation_sources.snapshots import (
    capture_file,
    capture_sqlite,
)
from personal_knowledge.core.conversation_events import EventKind
from personal_knowledge.core.conversation_events import (
    FieldDisposition,
    FidelityDimension,
    FidelityLevel,
    RelationKind,
)


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "conversation_sources"
MESSAGE_KINDS = {
    EventKind.USER_MESSAGE,
    EventKind.ASSISTANT_MESSAGE,
    EventKind.DEVELOPER_MESSAGE,
    EventKind.SYSTEM_MESSAGE,
}


@pytest.mark.parametrize(
    ("family", "fixture_name", "expected_body"),
    [
        pytest.param("codex", "codex_agent_sessions.jsonl", "Here is the summary.", id="codex"),
        pytest.param("claude", "claude_export.jsonl", "hello", id="claude"),
        pytest.param("qoder", "qoder_export.jsonl", "q prompt", id="qoder"),
        pytest.param("pi", "pi_conversation.jsonl", "pi prompt", id="pi"),
        pytest.param("workbuddy", "workbuddy_session.jsonl", "wb prompt", id="workbuddy"),
        pytest.param("kimi", "kimi_turn.jsonl", "kimi prompt", id="kimi"),
        pytest.param("kimi-work", "kimi_turn.jsonl", "kimi prompt", id="kimi-work"),
        pytest.param("copilot", "copilot_trace.jsonl", "copilot answer", id="copilot"),
        pytest.param("gemini", "gemini_conversation.json", "gemini prompt", id="gemini"),
    ],
)
def test_message_adapter_carries_exact_source_body_outside_summary(
    tmp_path: Path,
    family: str,
    fixture_name: str,
    expected_body: str,
) -> None:
    source = FIXTURES / fixture_name
    artifact, blob = capture_file(
        source,
        tmp_path,
        relative_path=fixture_name,
        byte_limit=1_000_000,
        count_limit=1,
    )

    result = adapt_for(
        family,
        SourceArtifactSet((artifact,)),
        artifact_root=blob.parent,
    )

    matching = [
        event
        for event in result.events
        if event.kind in MESSAGE_KINDS and event.content == expected_body
    ]
    assert len(matching) == 1
    assert matching[0].summary is None


@pytest.mark.parametrize(
    ("family", "fixture_name", "source_body", "native_event_id"),
    [
        pytest.param("codex", "codex_agent_sessions.jsonl", "Here is the summary.", "resp_1", id="codex"),
        pytest.param("claude", "claude_export.jsonl", "hello", "u1:content:0", id="claude"),
        pytest.param("qoder", "qoder_export.jsonl", "q prompt", "q1:content:0", id="qoder"),
        pytest.param("pi", "pi_conversation.jsonl", "pi prompt", "m1", id="pi"),
        pytest.param("workbuddy", "workbuddy_session.jsonl", "wb prompt", "m1", id="workbuddy"),
        pytest.param("kimi", "kimi_turn.jsonl", "kimi prompt", "km1", id="kimi"),
        pytest.param("kimi-work", "kimi_turn.jsonl", "kimi prompt", "km1", id="kimi-work"),
        pytest.param("copilot", "copilot_trace.jsonl", "copilot answer", "cm1", id="copilot"),
        pytest.param("gemini", "gemini_conversation.json", "gemini prompt", "msg-0", id="gemini"),
    ],
)
@pytest.mark.parametrize("source_value", [None, ""], ids=["null", "empty"])
def test_stream_message_adapters_preserve_null_vs_explicit_empty_string(
    tmp_path: Path,
    family: str,
    fixture_name: str,
    source_body: str,
    native_event_id: str,
    source_value: str | None,
) -> None:
    fixture_text = (FIXTURES / fixture_name).read_text(encoding="utf-8")
    assert fixture_text.count(source_body) == 1
    source = tmp_path / fixture_name
    source.write_text(
        fixture_text.replace(json.dumps(source_body), json.dumps(source_value)),
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path / "capture", relative_path=fixture_name,
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    message = next(
        event for event in result.events
        if event.kind in MESSAGE_KINDS
        and event.provenance.native_event_id == native_event_id
    )
    assert message.content is source_value or message.content == source_value
    assert message.summary is None


@pytest.mark.parametrize("family", ["zcode", "mimo", "opencode"])
@pytest.mark.parametrize("source_value", [None, ""], ids=["null", "empty"])
def test_live_sqlite_part_adapters_preserve_null_vs_explicit_empty_string(
    tmp_path: Path, family: str, source_value: str | None,
) -> None:
    db = tmp_path / "live.sqlite"
    con = sqlite3.connect(db)
    try:
        if family == "zcode":
            con.executescript(
                "CREATE TABLE session (id TEXT,parent_id TEXT,title TEXT,"
                "time_created TEXT,time_updated TEXT,time_compacting TEXT,trace_id TEXT,"
                "directory TEXT,path TEXT);"
                "CREATE TABLE message (id TEXT,session_id TEXT,time_created TEXT,"
                "time_updated TEXT,data TEXT,sequence INTEGER);"
                "CREATE TABLE part (id TEXT,message_id TEXT,session_id TEXT,"
                "time_created TEXT,time_updated TEXT,data TEXT,sequence INTEGER);"
            )
            con.execute("INSERT INTO session VALUES (?,?,?,?,?,?,?,?,?)", (
                "s1", None, "session", "2026-08-01", None, None, None, None, None,
            ))
            con.execute("INSERT INTO message VALUES (?,?,?,?,?,?)", (
                "m1", "s1", "2026-08-01", None,
                json.dumps({"role": "user"}), 1,
            ))
            con.execute("INSERT INTO part VALUES (?,?,?,?,?,?,?)", (
                "p1", "m1", "s1", "2026-08-01", None,
                json.dumps({"type": "text", "text": source_value}), 1,
            ))
            tables = zcode.LIVE_ALLOWED_TABLES
            columns = zcode.LIVE_ALLOWED_COLUMNS
        else:
            con.executescript(
                "CREATE TABLE session (id TEXT,parent_id TEXT,title TEXT,"
                "time_created TEXT,time_updated TEXT,time_compacting TEXT);"
                "CREATE TABLE message (id TEXT,session_id TEXT,time_created TEXT,"
                "time_updated TEXT,data TEXT);"
                "CREATE TABLE part (id TEXT,message_id TEXT,session_id TEXT,"
                "time_created TEXT,time_updated TEXT,data TEXT);"
            )
            con.execute("INSERT INTO session VALUES (?,?,?,?,?,?)", (
                "s1", None, "session", "2026-08-01", None, None,
            ))
            con.execute("INSERT INTO message VALUES (?,?,?,?,?)", (
                "m1", "s1", "2026-08-01", None,
                json.dumps({"role": "user"}),
            ))
            con.execute("INSERT INTO part VALUES (?,?,?,?,?,?)", (
                "p1", "m1", "s1", "2026-08-01", None,
                json.dumps({"type": "text", "text": source_value}),
            ))
            tables = mimo_opencode.LIVE_ALLOWED_TABLES
            columns = mimo_opencode.LIVE_ALLOWED_COLUMNS
        con.commit()
    finally:
        con.close()
    artifact, blob = capture_sqlite(
        db, tmp_path / "capture", allowed_tables=tables,
        allowed_columns=columns, byte_limit=1_000_000, count_limit=3,
    )

    result = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    message = next(
        event for event in result.events
        if event.kind in MESSAGE_KINDS
        and event.provenance.native_event_id == "p1"
    )
    assert message.content is source_value or message.content == source_value


def test_codex_live_output_text_block_carries_exact_body(tmp_path: Path) -> None:
    source = tmp_path / "rollout.jsonl"
    source.write_text(
        '{"type":"session_meta","payload":{"id":"session-live"}}\n'
        '{"type":"response_item","payload":{"type":"message",'
        '"id":"message-live","role":"assistant","content":'
        '[{"type":"output_text","text":"live codex body"}]}}\n',
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path, relative_path="rollout.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        "codex", SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    message = next(
        event for event in result.events
        if event.kind is EventKind.ASSISTANT_MESSAGE
    )
    assert message.content == "live codex body"
    assert message.summary is None


def test_workbuddy_live_output_text_block_carries_exact_body(tmp_path: Path) -> None:
    source = tmp_path / "workbuddy.jsonl"
    source.write_text(
        '{"type":"message","id":"message-live","sessionId":"session-live",'
        '"role":"assistant","content":'
        '[{"type":"output_text","text":"live workbuddy body"}]}\n',
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path, relative_path="workbuddy.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        "workbuddy", SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    message = next(
        event for event in result.events
        if event.kind is EventKind.ASSISTANT_MESSAGE
    )
    assert message.content == "live workbuddy body"
    assert message.summary is None


@pytest.mark.parametrize("family", ["kimi", "kimi-work"])
def test_kimi_live_turn_prompt_input_carries_exact_body(
    tmp_path: Path, family: str,
) -> None:
    source = tmp_path / "wire.jsonl"
    source.write_text(
        '{"type":"turn.prompt","input":'
        '[{"type":"text","text":"live kimi prompt"}],'
        '"origin":{"kind":"user"}}\n',
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path, relative_path="wire.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    message = next(
        event for event in result.events
        if event.kind is EventKind.USER_MESSAGE
    )
    assert message.content == "live kimi prompt"
    assert message.summary is None


def test_kimi_live_content_parts_separate_text_from_reasoning(tmp_path: Path) -> None:
    source = tmp_path / "wire.jsonl"
    source.write_text(
        '{"type":"context.append_loop_event","event":{"type":"content.part",'
        '"uuid":"part-text","part":{"type":"text","text":"live kimi answer"}}}\n'
        '{"type":"context.append_loop_event","event":{"type":"content.part",'
        '"uuid":"part-think","part":{"type":"think","think":"private reasoning"}}}\n',
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path, relative_path="wire.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        "kimi", SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    messages = [
        event for event in result.events
        if event.kind is EventKind.ASSISTANT_MESSAGE
    ]
    assert [(event.content, event.summary) for event in messages] == [
        ("live kimi answer", None),
    ]
    assert sum(event.kind is EventKind.REASONING for event in result.events) == 1


@pytest.mark.parametrize("family", ["claude", "qoder"])
def test_claude_dag_content_blocks_are_typed_individually_and_replay_stably(
    tmp_path: Path, family: str,
) -> None:
    source = FIXTURES / "claude_live_content_blocks.jsonl"
    artifact, blob = capture_file(
        source, tmp_path / "capture", relative_path=f"{family}-live.jsonl",
        byte_limit=1_000_000, count_limit=1,
    )

    first = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )
    second = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    assert [event.kind for event in first.events] == [
        EventKind.REASONING,
        EventKind.ASSISTANT_MESSAGE,
        EventKind.TOOL_CALL,
        EventKind.TOOL_RESULT,
        EventKind.USER_MESSAGE,
        EventKind.USER_MESSAGE,
        EventKind.TOOL_CALL,
        EventKind.USAGE,
        EventKind.SYSTEM_MESSAGE,
    ]
    # the api_error system_message has no content; only the real messages carry bodies
    assert [event.content for event in first.events
            if event.kind in MESSAGE_KINDS and event.content is not None] == [
        "assistant body", "post-tool user body", "",
    ]
    assert [event.event_id for event in first.events] == [
        event.event_id for event in second.events
    ]
    assert [event.ordinal for event in first.events] == list(range(9))
    assert all(
        "/content/" in event.provenance.native_locator
        for event in first.events[:6]
    )
    assert any(
        relation.relation_kind is RelationKind.CALL_RESULT
        and relation.source_event_id == first.events[2].event_id
        and relation.target_event_id == first.events[3].event_id
        for relation in first.relations
    )
    result_block_ids = {first.events[3].event_id, first.events[4].event_id}
    result_parent_relations = {
        relation.source_event_id
        for relation in first.relations
        if relation.relation_kind is RelationKind.PARENT_CHILD
        and relation.target_event_id == first.events[0].event_id
    }
    assert result_block_ids <= result_parent_relations
    orphan = first.events[6]
    assert orphan.fidelity.level(FidelityDimension.RELATION_COMPLETENESS) is FidelityLevel.PARTIAL
    assert any(
        disposition.field_name == "tool_call_id"
        and disposition.disposition is FieldDisposition.UNAVAILABLE
        for disposition in orphan.field_dispositions
    )
    api_error = first.events[-1]
    # DEEP-3: api_error system records are now classified as system_message
    assert api_error.kind is EventKind.SYSTEM_MESSAGE
    assert api_error.content is None
    # its recovered summary is non-empty and the record is tracked as mapped
    assert api_error.summary and "api_error" in api_error.summary
    assert any(
        disposition.field_name == "type:system"
        and disposition.disposition is FieldDisposition.MAPPED
        for disposition in api_error.field_dispositions
    )


@pytest.mark.parametrize("family", ["claude", "qoder"])
def test_claude_uuidless_child_still_inherits_native_parent_relation(
    tmp_path: Path, family: str,
) -> None:
    source = tmp_path / f"{family}-uuidless.jsonl"
    source.write_text(
        '{"type":"assistant","uuid":"parent","sessionId":"s",'
        '"message":{"content":[{"type":"text","text":"parent body"}]}}\n'
        '{"type":"user","parentUuid":"parent","sessionId":"s",'
        '"message":{"content":[{"type":"text","text":"child body"}]}}\n',
        encoding="utf-8",
    )
    artifact, blob = capture_file(
        source, tmp_path / "capture", relative_path=source.name,
        byte_limit=1_000_000, count_limit=1,
    )

    result = adapt_for(
        family, SourceArtifactSet((artifact,)), artifact_root=blob.parent,
    )

    parent, child = result.events
    assert child.provenance.native_event_id is None
    assert any(
        relation.relation_kind is RelationKind.PARENT_CHILD
        and relation.source_event_id == child.event_id
        and relation.target_event_id == parent.event_id
        for relation in result.relations
    )
    assert result.fidelity.level(
        FidelityDimension.RELATION_COMPLETENESS
    ) is FidelityLevel.COMPLETE
