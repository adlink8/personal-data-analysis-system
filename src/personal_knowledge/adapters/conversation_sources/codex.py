"""Phase 62-02: Codex JSONL event-stream adapter (family ``codex``).

Maps Codex's top-level JSONL event stream into typed events, relations and
fidelity (62-RESEARCH format matrix). Two native shapes are supported:

  - synthetic: ``{"type": "session_meta", "session_id": ..., ...}`` with flat
    fields (contract fixtures);
  - real export: fields nested under a ``payload`` object
    (``session_meta.payload.id``, ``turn_context.payload.turn_id``,
    ``response_item.payload.{role, content:[{type,text}]}``) and
    ``event_msg.payload.type`` loop hints.

Native turn IDs and call/result links survive as typed relations; compaction
boundaries become compaction events, never user messages. Unknown record
kinds stay ``unknown_native``; a missing native session never fabricates a
complete-looking session (D-04/D-11).
"""

from __future__ import annotations

from pathlib import Path

from personal_knowledge.adapters.conversation_sources.contracts import (
    AdaptationResult,
    CapabilityDescriptor,
    SourceArtifact,
    SourceArtifactSet,
)
from personal_knowledge.adapters.conversation_sources.jsonl_stream import (
    iter_jsonl_lines,
)
from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    EventContractError,
    EventKind,
    EventRelation,
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
    make_event_id,
)

FAMILY = "codex"
ADAPTER_VERSION = "1.2.0"
CONTRACT_VERSION = "1"

_COMPLETE = {
    FidelityDimension.SOURCE_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.ORDERING_CONFIDENCE: FidelityLevel.COMPLETE,
    FidelityDimension.RELATION_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.COMPACTION_VISIBILITY: FidelityLevel.COMPLETE,
    FidelityDimension.NATIVE_ID_STABILITY: FidelityLevel.COMPLETE,
}

# event_msg payload loop hints that act as turn boundaries.
_LOOP_HINTS = ("task_started", "turn_started", "agent_message", "agent_turn_started")


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


def _inner(record: dict) -> dict:
    """Real Codex exports nest fields under ``payload``; synthetic fixtures
    are flat. Both shapes share the top-level ``type``/``timestamp``."""
    return record.get("payload") if isinstance(record.get("payload"), dict) else record


def _text(record: dict) -> str | None:
    """Text from a content block list (real shape) or a flat string."""
    content = _inner(record).get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        saw_text = False
        for block in content:
            if isinstance(block, dict) and block.get("type") in (
                "text", "input_text", "output_text",
            ):
                saw_text = True
                raw = block.get("text")
                parts.append("" if raw is None else str(raw))
        return " ".join(parts) if saw_text else None
    return None


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(
            EventKind.SESSION_LIFECYCLE,
            EventKind.USER_MESSAGE,
            EventKind.ASSISTANT_MESSAGE,
            EventKind.DEVELOPER_MESSAGE,
            EventKind.REASONING,
            EventKind.TOOL_CALL,
            EventKind.TOOL_RESULT,
            EventKind.COMPACTION_SUMMARY,
            EventKind.TURN_BOUNDARY,
            EventKind.USAGE,
            EventKind.FILE_CONTEXT,
            EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(
            RelationKind.CALL_RESULT,
            RelationKind.TURN_MEMBERSHIP,
        ),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "jsonl_event_stream",
            "nested_payload": "true",
            "compaction": "top_level_context_compacted",
            "call_result": "call_id_pairing",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """Probe the first non-blank line for the opening ``session_meta`` event."""
    if not (artifact.relative_path or "").lower().endswith(".jsonl"):
        return False
    try:
        with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
            for raw in h:
                line = raw.strip()
                if not line:
                    continue
                return '"type"' in line and '"session_meta"' in line
    except OSError:
        return False
    return False


def _provenance(artifact: SourceArtifact, locator: str, *, session: str | None, native_id: str | None) -> Provenance:
    return Provenance(
        artifact_id=artifact.artifact_id,
        artifact_hash=artifact.content_hash,
        native_locator=locator,
        native_session_id=session or None,
        native_event_id=native_id,
        contract_version=CONTRACT_VERSION,
    )


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           content=None, summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(
            FAMILY, artifact.artifact_id, CONTRACT_VERSION,
            native_id or locator, kind=kind, session_id=session_id,
            native_locator=locator,
        ),
        session_id=session_id,
        kind=kind,
        provenance=_provenance(artifact, locator, session=native_session or "", native_id=native_id),
        fidelity=fidelity or _fidelity(),
        occurred_at=occurred_at,
        content=content,
        summary=summary,
    )


def _adapt_record(record: dict, artifact, *, session_id, locator) -> TypedEvent | None:
    """Map one Codex record to a typed event; unknown kinds stay unknown_native."""
    kind = record.get("type")
    inner = _inner(record)
    ts = record.get("timestamp") or inner.get("timestamp")
    sid = record.get("session_id") or inner.get("session_id") or inner.get("id")
    if kind == "session_meta":
        return _event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                      locator=locator, native_id=inner.get("id"), occurred_at=ts,
                      native_session=sid)
    if kind == "turn_context":
        return _event(artifact, session_id=session_id, kind=EventKind.TURN_BOUNDARY,
                      locator=locator, native_id=inner.get("turn_id"), occurred_at=ts,
                      summary=str(inner.get("prompt") or "")[:512] or None, native_session=sid)
    if kind == "response_item":
        item_type = inner.get("type")
        role = inner.get("role")
        ev = EventKind.ASSISTANT_MESSAGE if role == "assistant" else (
            EventKind.USER_MESSAGE if role == "user" else (
                EventKind.DEVELOPER_MESSAGE if role == "developer" else None))
        if ev is not None:
            return _event(artifact, session_id=session_id, kind=ev, locator=locator,
                          native_id=inner.get("id") or inner.get("item_id"), occurred_at=ts,
                          content=_text(record), native_session=sid)
        if item_type in ("function_call", "custom_tool_call", "tool_search_call"):
            return _event(
                artifact, session_id=session_id, kind=EventKind.TOOL_CALL,
                locator=locator, native_id=inner.get("call_id") or inner.get("id"),
                occurred_at=ts, summary=str(inner.get("name") or item_type)[:256],
                native_session=sid,
            )
        if item_type in (
            "function_call_output", "custom_tool_call_output", "tool_search_output"
        ):
            call_id = inner.get("call_id") or inner.get("id")
            return _event(
                artifact, session_id=session_id, kind=EventKind.TOOL_RESULT,
                locator=locator, native_id=f"{call_id}#output",
                occurred_at=ts, native_session=sid,
            )
        if item_type == "reasoning":
            return _event(
                artifact, session_id=session_id, kind=EventKind.REASONING,
                locator=locator, native_id=inner.get("id"), occurred_at=ts,
                summary=_summary_text(inner.get("summary")), native_session=sid,
            )
    if kind == "event_msg":
        # loop hints are first-class episode hints; other event messages stay
        # unknown native records rather than guessed content.
        hint = inner.get("type")
        if hint == "context_compacted":
            return _event(
                artifact, session_id=session_id,
                kind=EventKind.COMPACTION_SUMMARY, locator=locator,
                native_id=inner.get("turn_id") or f"compact:{locator}",
                occurred_at=ts, summary=str(inner.get("summary") or "")[:2048] or None,
                native_session=sid,
            )
        if hint == "user_message":
            raw_message = inner.get("message")
            return _event(
                artifact, session_id=session_id, kind=EventKind.USER_MESSAGE,
                locator=locator, native_id=inner.get("id"), occurred_at=ts,
                content=None if raw_message is None else str(raw_message),
                native_session=sid,
            )
        if hint == "token_count":
            return _event(
                artifact, session_id=session_id, kind=EventKind.USAGE,
                locator=locator, native_id=inner.get("turn_id"), occurred_at=ts,
                fidelity=_fidelity(CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                native_session=sid,
            )
        if hint in _LOOP_HINTS:
            return _event(artifact, session_id=session_id, kind=EventKind.TURN_BOUNDARY,
                          locator=locator, native_id=inner.get("turn_id") or hint,
                          occurred_at=ts, summary=str(inner.get("message") or "")[:256] or None,
                          native_session=sid)
        return _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                      locator=locator, native_id=inner.get("turn_id") or hint or inner.get("id"),
                      occurred_at=ts, fidelity=_fidelity(
                          STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                          RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                          CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                      ), native_session=sid)
    if kind == "function_call":
        return _event(artifact, session_id=session_id, kind=EventKind.TOOL_CALL,
                      locator=locator, native_id=inner.get("call_id") or inner.get("id"),
                      occurred_at=ts, summary=str(inner.get("name") or "")[:256] or None,
                      native_session=sid)
    if kind == "function_call_output":
        # Codex shares call_id between call and output; make_event_id omits
        # kind when a native id is present, so disambiguate the output's id.
        call_id = inner.get("call_id") or inner.get("id")
        return _event(artifact, session_id=session_id, kind=EventKind.TOOL_RESULT,
                      locator=locator, native_id=f"{call_id}#output",
                      occurred_at=ts, summary=str(inner.get("output") or "")[:2048] or None,
                      native_session=sid)
    if kind == "context_compacted":
        return _event(artifact, session_id=session_id, kind=EventKind.COMPACTION_SUMMARY,
                      locator=locator, native_id=inner.get("turn_id"), occurred_at=ts,
                      summary=str(inner.get("summary") or "")[:2048] or None, native_session=sid)
    if kind == "world_state":
        return _event(
            artifact, session_id=session_id, kind=EventKind.FILE_CONTEXT,
            locator=locator, native_id=inner.get("id"), occurred_at=ts,
            fidelity=_fidelity(CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
            native_session=sid,
        )
    return _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                  locator=locator, native_id=record.get("id") or inner.get("id"),
                  occurred_at=ts, fidelity=_fidelity(
                      STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                      RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                      CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                  ), native_session=sid)


def _summary_text(value) -> str | None:
    if isinstance(value, str):
        return value[:2048] or None
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, dict):
                text = item.get("text") or item.get("summary")
                if text:
                    parts.append(str(text))
        return " ".join(parts)[:2048] or None
    return None


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one immutable Codex export into typed events/relations."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    records = list(iter_jsonl_lines(artifact_root / artifact.artifact_id))

    session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator="session")
    events: list[TypedEvent] = []
    relations: list[EventRelation] = []
    warnings: list[str] = []
    turn_of: dict[str, str] = {}  # event_id -> native turn id
    native_session = None
    for record in records:
        inner = _inner(record)
        sid = record.get("session_id") or inner.get("session_id") or (
            inner.get("id") if record.get("type") == "session_meta" else None)
        if sid:
            native_session = sid
            break

    for lineno, record in enumerate(records, start=1):
        ev = _adapt_record(record, artifact, session_id=session_id,
                           locator=f"{artifact.relative_path}#L{lineno}")
        if ev is not None:
            events.append(ev)
            tid = _inner(record).get("turn_id")
            if tid:
                turn_of[ev.event_id] = tid

    # Turn membership: events carrying a native turn id link to its boundary.
    boundaries = {e.provenance.native_event_id: e for e in events if e.kind is EventKind.TURN_BOUNDARY}
    for event_id, tid in turn_of.items():
        anchor = boundaries.get(tid)
        if anchor is not None and anchor.event_id != event_id:
            relations.append(EventRelation(
                relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-turn:{event_id}:{anchor.event_id}"),
                source_event_id=event_id, target_event_id=anchor.event_id,
                relation_kind=RelationKind.TURN_MEMBERSHIP,
            ))

    # Call/result pairing: call and output share the native call_id; the
    # output's native id carries a "#output" suffix (see _adapt_record).
    calls = {e.provenance.native_event_id: e for e in events if e.kind is EventKind.TOOL_CALL}
    results = {
        (e.provenance.native_event_id or "").removesuffix("#output"): e
        for e in events if e.kind is EventKind.TOOL_RESULT
    }
    for call_id, call_ev in calls.items():
        result_ev = results.get(call_id)
        if result_ev is None:
            warnings.append(f"tool call {call_id!r} has no result (partial)")
            continue
        relations.append(EventRelation(
            relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                      f"rel-call:{call_id}"),
            source_event_id=call_ev.event_id, target_event_id=result_ev.event_id,
            relation_kind=RelationKind.CALL_RESULT,
        ))

    unknown = sum(1 for e in events if e.kind is EventKind.UNKNOWN_NATIVE)
    if unknown:
        warnings.append(f"{unknown} unknown native record(s) preserved")

    sessions: list[AdaptedSession] = []
    if native_session:
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(artifact, f"{artifact.relative_path}#session",
                                   session=native_session, native_id=native_session),
            fidelity=_fidelity(),
            native_session_id=native_session,
        ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events), fidelity=_fidelity(
            STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE,
        ),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )
