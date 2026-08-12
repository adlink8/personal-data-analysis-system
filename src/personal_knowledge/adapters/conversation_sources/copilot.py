"""Phase 62-02: Copilot / vscode-copilot JSONL trace adapter.

Copilot exports turn start/end, assistant message and tool execution
start/complete records. Lifecycle events are paired by native IDs; a
missing ``tool_execution_complete`` or ``turn_end`` is tolerated as bounded
partial fidelity (never guessed). The family keeps a single capability
contract with an alias for vscode-copilot.
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

FAMILY = "copilot"
ADAPTER_VERSION = "1.0.0"
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

_KINDS = {
    "turn_start": EventKind.TURN_BOUNDARY,
    "turn_end": EventKind.TURN_BOUNDARY,
    "assistant_message": EventKind.ASSISTANT_MESSAGE,
    "tool_execution_start": EventKind.TOOL_CALL,
    "tool_execution_complete": EventKind.TOOL_RESULT,
}


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(
            EventKind.SESSION_LIFECYCLE, EventKind.TURN_BOUNDARY,
            EventKind.ASSISTANT_MESSAGE, EventKind.TOOL_CALL,
            EventKind.TOOL_RESULT, EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(RelationKind.CALL_RESULT,),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "jsonl_trace",
            "aliases": "vscode-copilot",
            "pairing": "native_tool_id_lifecycle",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    if not (artifact.relative_path or "").lower().endswith(".jsonl"):
        return False
    try:
        with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
            for raw in h:
                line = raw.strip()
                if not line:
                    continue
                return '"turn_start"' in line or '"tool_execution_start"' in line
    except OSError:
        return False
    return False


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id),
        session_id=session_id, kind=kind,
        provenance=Provenance(
            artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
            native_locator=locator, native_session_id=native_session or None,
            native_event_id=native_id, contract_version=CONTRACT_VERSION,
        ),
        fidelity=fidelity or _fidelity(), occurred_at=occurred_at, summary=summary,
    )


def _adapt_record(record: dict, artifact, *, session_id, locator) -> TypedEvent | None:
    kind = _KINDS.get(record.get("type"))
    ts = record.get("timestamp")
    sid = record.get("session_id")
    native_id = record.get("tool_id") or record.get("message_id") or record.get("turn_id")
    if kind is None:
        return _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                      locator=locator, native_id=record.get("id"), occurred_at=ts,
                      fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                         RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                         CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                      native_session=sid)
    if kind is EventKind.TOOL_RESULT and record.get("tool_id"):
        # start and complete share the native tool_id; make_event_id omits
        # kind when a native id is present, so disambiguate the completion.
        native_id = f"{record['tool_id']}#complete"
    return _event(artifact, session_id=session_id, kind=kind, locator=locator,
                  native_id=native_id, occurred_at=ts,
                  summary=str(record.get("content") or record.get("name") or "")[:2048] or None,
                  native_session=sid)


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one immutable Copilot trace into typed events/relations."""
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
    tool_starts: dict[str, TypedEvent] = {}
    tool_ends: dict[str, TypedEvent] = {}
    native_session = next((r.get("session_id") for r in records if r.get("session_id")), None)

    for lineno, record in enumerate(records, start=1):
        ev = _adapt_record(record, artifact, session_id=session_id,
                           locator=f"{artifact.relative_path}#L{lineno}")
        if ev is None:
            continue
        events.append(ev)
        tool_id = record.get("tool_id")
        if not tool_id:
            continue
        if ev.kind is EventKind.TOOL_CALL:
            tool_starts[tool_id] = ev
        elif ev.kind is EventKind.TOOL_RESULT:
            tool_ends[tool_id] = ev

    for tool_id, start in tool_starts.items():
        end = tool_ends.get(tool_id)
        if end is None:
            warnings.append(f"tool {tool_id!r} has no completion (partial)")
            continue
        relations.append(EventRelation(
            relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                      f"rel-call:{tool_id}"),
            source_event_id=start.event_id, target_event_id=end.event_id,
            relation_kind=RelationKind.CALL_RESULT,
        ))

    unknown = sum(1 for e in events if e.kind is EventKind.UNKNOWN_NATIVE)
    if unknown:
        warnings.append(f"{unknown} unknown native record(s) preserved")

    sessions: list[AdaptedSession] = []
    if native_session:
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=f"{artifact.relative_path}#session",
                native_session_id=native_session, native_event_id=native_session,
                contract_version=CONTRACT_VERSION,
            ),
            fidelity=_fidelity(), native_session_id=native_session,
        ))

    relation_loss = bool(tool_starts) and len(tool_starts) != len(relations)
    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events),
        fidelity=_fidelity(
            STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE,
            RELATION_COMPLETENESS=FidelityLevel.PARTIAL if relation_loss else FidelityLevel.COMPLETE,
        ),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )
