"""Phase 62-04 Task 1: deterministic event-to-legacy compatibility projection.

RED/GREEN tests for :mod:`personal_knowledge.application.conversation.compatibility_projection`
and the new event-aware seam beside :mod:`personal_knowledge.core.conversation_repository`:

  - legacy ``canonical_sessions/messages/tool_events`` become a deterministic
    projection of the active v2 generation (D-17); old repository methods keep
    reading the legacy table contract, new methods read typed active-generation
    events/relations/fidelity
  - only documented lossy session/message/tool rows are emitted; reasoning,
    usage, compaction, boundaries, file-context and unknown-native events are
    never projected as user facts (D-23)
  - no double counting: each typed event maps to at most one compatibility row
  - stable source refs and exact generation lineage/fingerprint
  - provider/consumer parity: current summary / eligibility / retrieval / delta
    consumers keep working against the projected legacy contract

All tests run against temporary SQLite files under tmp_path. No live database,
no var/, no network, no provider calls (D-31).
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventKind,
    FieldDisposition,
    FieldDispositionRecord,
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
    make_event_id,
)
from personal_knowledge.adapters.conversation_sources.contracts import SourceArtifact
from personal_knowledge.application.conversation.event_repository import (
    EventRepository,
    GenerationInput,
)
from personal_knowledge.application.conversation.event_schema import create_v2_schema
from personal_knowledge.application.conversation.compatibility_projection import (
    CompatibilityProjectionReport,
    ProjectionFingerprint,
    build_compatibility_projection,
    write_compatibility_projection,
)
from personal_knowledge.core.conversation_repository import (
    ConversationRepository,
    EventAwareConversationRepository,
    SOURCE_CANONICAL,
)


def _prov(native_event_id: str, locator: str) -> Provenance:
    return Provenance(
        artifact_id="art-a", artifact_hash="h" * 8, native_locator=locator,
        native_session_id="s-1", native_event_id=native_event_id,
        contract_version="1",
    )


def _artifact() -> SourceArtifact:
    return SourceArtifact(
        artifact_id="art-a", family="codex", source_kind="file",
        content_hash="h" * 8, capture_method="sha256",
        relative_path="rollout.jsonl", byte_size=10,
    )


def _session(session_id: str = "s-1") -> AdaptedSession:
    return AdaptedSession(
        session_id=session_id,
        provenance=_prov(session_id, f"jsonl:{session_id}"),
        fidelity=FidelityProfile.complete(),
        native_session_id=session_id,
        started_at="2026-08-12T00:00:00Z",
        ended_at="2026-08-12T00:05:00Z",
    )


def _event(session_id: str, kind: EventKind, locator: str, *,
           native_id: str | None = None, ordinal: int | None = None,
           summary: str | None = None, fidelity: FidelityProfile | None = None,
           dispositions: tuple[FieldDispositionRecord, ...] = ()) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(
            "codex", "art-a", "1", native_id or locator,
            kind=kind, session_id=session_id, native_locator=locator,
        ),
        session_id=session_id,
        kind=kind,
        provenance=_prov(native_id or locator, locator),
        fidelity=fidelity or FidelityProfile.complete(),
        ordinal=ordinal,
        occurred_at=f"2026-08-12T00:0{ordinal or 0}:00Z",
        summary=summary,
        field_dispositions=dispositions,
    )


def _mixed_generation() -> tuple[GenerationInput, dict[str, EventKind]]:
    """One generation with message/reasoning/tool/compaction/unknown events.

    Returns ``(gen, expected_kinds)`` where ``expected_kinds`` maps event id to
    its kind so tests can assert what a deterministic projection must emit.
    """
    session = _session("s-1")
    events = [
        _event("s-1", EventKind.SESSION_LIFECYCLE, "jsonl:1", ordinal=1,
               native_id="session-1"),
        _event("s-1", EventKind.USER_MESSAGE, "jsonl:2", ordinal=2,
               native_id="msg-1", summary="hello world"),
        _event("s-1", EventKind.ASSISTANT_MESSAGE, "jsonl:3", ordinal=3,
               native_id="msg-2", summary="hi there"),
        _event("s-1", EventKind.REASONING, "jsonl:4", ordinal=4,
               native_id="rs-1", summary="thinking step"),
        _event("s-1", EventKind.TOOL_CALL, "jsonl:5", ordinal=5,
               native_id="call-1", summary="Bash"),
        _event("s-1", EventKind.TOOL_RESULT, "jsonl:6", ordinal=6,
               native_id="call-1#output", summary="ok"),
        _event("s-1", EventKind.COMPACTION_SUMMARY, "jsonl:7", ordinal=7,
               native_id="compact-1", summary="Compacted earlier turns."),
        _event("s-1", EventKind.UNKNOWN_NATIVE, "jsonl:8", ordinal=8,
               native_id="unk-1", summary="raw payload",
               fidelity=FidelityProfile.from_levels(
                   {FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.PARTIAL}
               ),
               dispositions=(
                   FieldDispositionRecord(
                       "native_body", FieldDisposition.PRESERVED_BY_REFERENCE,
                       "raw row kept in immutable artifact slice",
                   ),
               )),
    ]
    kinds = {e.event_id: e.kind for e in events}
    gen = GenerationInput(
        family="codex",
        adapter_version="1",
        contract_version="1",
        capability_digest="cap-1",
        source_manifest_id="manifest-1",
        dataset_digest="ds-1",
        artifacts=(_artifact(),),
        sessions=(session,),
        events=tuple(events),
        relations=(),
        dispositions=(),
        warnings=(),
    )
    return gen, kinds


@pytest.fixture()
def v2_db(tmp_path: Path) -> tuple[Path, EventRepository, GenerationInput, dict[str, EventKind]]:
    db = tmp_path / "conversations.sqlite"
    repo = EventRepository(db)
    repo.create_schema()
    gen, kinds = _mixed_generation()
    repo.write_generation(gen, generation_id="gen-1")
    return db, repo, gen, kinds


# --------------------------------------------------------------- projection

def test_projection_emits_only_documented_lossy_rows(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, generation_id="gen-1")
    assert isinstance(report, CompatibilityProjectionReport)
    assert report.generation_id == "gen-1"
    # 1 session -> 1 session row
    assert len(report.sessions) == 1
    # 4 message kinds (user/assistant/developer/system) -> 2 message rows here
    assert len(report.messages) == 2
    # 2 tool events (call + result) -> 2 tool rows
    assert len(report.tools) == 2
    # excluded events are reported, never flattened into user facts
    excluded_kinds = {e["kind"] for e in report.excluded}
    assert EventKind.COMPACTION_SUMMARY.value in excluded_kinds
    assert EventKind.UNKNOWN_NATIVE.value in excluded_kinds
    assert EventKind.REASONING.value in excluded_kinds
    assert EventKind.SESSION_LIFECYCLE.value in excluded_kinds


def test_projection_no_compact_summary_as_user_fact(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, generation_id="gen-1")
    contents = [m["content"] for m in report.messages]
    assert not any("Compacted" in (c or "") for c in contents)
    roles = {m["role"] for m in report.messages}
    assert "user" in roles
    assert "assistant" in roles


def test_projection_no_double_counting(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, generation_id="gen-1")
    message_ids = [m["canonical_message_id"] for m in report.messages]
    assert len(message_ids) == len(set(message_ids))
    tool_ids = [t["canonical_tool_id"] for t in report.tools]
    assert len(tool_ids) == len(set(tool_ids))
    # each event id maps to exactly one row or is excluded
    projected_events = {
        m["source_message_ref"] for m in report.messages
    } | {t["source_ref"] for t in report.tools}
    counted = sum(1 for eid, kind in kinds.items() if kind in (
        EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE,
        EventKind.DEVELOPER_MESSAGE, EventKind.SYSTEM_MESSAGE,
        EventKind.TOOL_CALL, EventKind.TOOL_RESULT,
    ))
    assert len(projected_events) == counted


def test_projection_stable_source_refs(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, generation_id="gen-1")
    first = build_compatibility_projection(db, generation_id="gen-1")
    assert report.messages == first.messages
    assert report.tools == first.tools
    # source refs resolve back to native locators
    assert any(m["source_message_ref"] == "jsonl:2" for m in report.messages)


def test_projection_exact_generation_lineage_and_fingerprint(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, generation_id="gen-1")
    fp = report.fingerprint
    assert isinstance(fp, ProjectionFingerprint)
    assert fp.generation_id == "gen-1"
    assert fp.session_count == 1
    assert fp.message_count == 2
    assert fp.tool_count == 2
    assert len(fp.digest) == 64
    # deterministic across rebuilds
    fp2 = build_compatibility_projection(db, generation_id="gen-1").fingerprint
    assert fp.digest == fp2.digest
    # a different generation must produce a different lineage/fingerprint


def test_projection_differs_across_generations(tmp_path: Path) -> None:
    db = tmp_path / "conversations.sqlite"
    repo = EventRepository(db)
    repo.create_schema()
    gen_a, _ = _mixed_generation()
    repo.write_generation(gen_a, generation_id="gen-a")
    fp_a = build_compatibility_projection(db, generation_id="gen-a").fingerprint
    # a second generation with a different message
    gen_b, _ = _mixed_generation()
    events = list(gen_b.events)
    events = tuple(
        _event("s-1", EventKind.USER_MESSAGE, "jsonl:200", ordinal=20,
               native_id="msg-2nd", summary="second user message")
        if e.kind is EventKind.SESSION_LIFECYCLE else e
        for e in events
    )  # placeholder replacement; build a fresh generation below instead
    events = tuple(
        e for e in gen_b.events
    ) + (
        _event("s-1", EventKind.USER_MESSAGE, "jsonl:200", ordinal=200,
               native_id="msg-2nd", summary="second user message"),
    )
    gen_b = GenerationInput(
        family="codex", adapter_version="1", contract_version="1",
        capability_digest="cap-1", source_manifest_id="manifest-1",
        dataset_digest="ds-2", artifacts=gen_b.artifacts,
        sessions=gen_b.sessions, events=events,
        relations=gen_b.relations, dispositions=gen_b.dispositions,
        warnings=(),
    )
    repo.write_generation(gen_b, generation_id="gen-b")
    fp_b = build_compatibility_projection(db, generation_id="gen-b").fingerprint
    assert fp_b.generation_id == "gen-b"
    assert fp_b.digest != fp_a.digest


# --------------------------------------------------------- write + legacy repo

def test_write_projection_keeps_legacy_repository_contract(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    report = build_compatibility_projection(db, "gen-1")
    csid = report.sessions[0]["canonical_session_id"]
    con = sqlite3.connect(str(db))
    con.execute("BEGIN")
    write_compatibility_projection(con, report)
    con.commit()
    con.close()

    legacy_repo = ConversationRepository(
        source=SOURCE_CANONICAL, legacy_db=db, canonical_db=db,
    )
    assert legacy_repo.session_count() == 1
    turns = list(legacy_repo.iter_turns(csid))
    # projection message rows keep the legacy contract: role, ordinal, content
    assert {t.role for t in turns} == {"user", "assistant"}
    assert legacy_repo.user_turn_count() == 1
    tools = list(legacy_repo.iter_tools(csid))
    assert len(tools) == 2  # one call row + one result row
    assert any(t.tool_name == "Bash" for t in tools)
    assert all(t.output_display == "[tool output omitted]" for t in tools)


def test_projection_rows_match_consumer_column_contract(v2_db) -> None:
    """Summary/eligibility/retrieval consumers read the legacy projection contract."""
    db, repo, gen, kinds = v2_db
    con = sqlite3.connect(str(db))
    con.execute("BEGIN")
    write_compatibility_projection(con, build_compatibility_projection(db, "gen-1"))
    con.commit()

    # eligibility-style query: eligible user messages with content length > 0
    rows = con.execute(
        "SELECT m.role, m.content, m.evidence_scope, s.evidence_eligible "
        "FROM canonical_messages m JOIN canonical_sessions s "
        "ON s.canonical_session_id=m.canonical_session_id "
        "WHERE s.evidence_eligible=1 AND m.role IN ('user','assistant') "
        "ORDER BY m.ordinal"
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] == "user"
    assert rows[0][2] == "user"
    assert rows[0][3] == 1
    # retrieval-style: message text is searchable content
    texts = [r[1] for r in rows]
    assert "hello world" in texts
    # delta-style consumer: canonical session + message rows exist with ids
    assert con.execute("SELECT COUNT(*) FROM canonical_sessions").fetchone()[0] == 1


# ------------------------------------------------------- event-aware repository

def test_event_aware_repository_reads_typed_events(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    # simulate the authority pointer: this plan's tests activate via the same
    # table the repository reads (the activation owner is Task 2; here the
    # event-aware seam must only read, never write, the authority).
    con = sqlite3.connect(str(db))
    con.execute(
        "INSERT INTO ce_generation_authority (generation_id, active, updated_at) "
        "VALUES ('gen-1', 1, '2026-08-12T00:00:00Z')"
    )
    con.commit()
    con.close()

    aware = EventAwareConversationRepository(event_db=db)
    assert aware.authority_generation_id() == "gen-1"
    events = aware.iter_typed_events()
    kinds_seen = {e["kind"] for e in events}
    assert EventKind.REASONING.value in kinds_seen
    assert EventKind.COMPACTION_SUMMARY.value in kinds_seen
    # fidelity and dispositions are explicit, not flattened
    unknown = [e for e in events if e["kind"] == EventKind.UNKNOWN_NATIVE.value]
    assert unknown and unknown[0]["fidelity_json"]
    disps = aware.iter_event_dispositions()
    assert any(d["disposition"] == FieldDisposition.PRESERVED_BY_REFERENCE.value
               for d in disps)


def test_event_aware_repository_readonly_authority(v2_db) -> None:
    db, repo, gen, kinds = v2_db
    aware = EventAwareConversationRepository(event_db=db)
    assert aware.authority_generation_id() is None
    assert aware.iter_typed_events() == []
    # read-only seam: no public activation/write mutation surface
    public = [n for n in dir(aware) if not n.startswith("_")]
    assert not any("activate" in n.lower() for n in public)
