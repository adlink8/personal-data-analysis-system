"""Phase 62-02: Copilot / vscode-copilot JSONL trace adapter.

Copilot exports turn start/end, assistant message and tool execution
start/complete records. Lifecycle events are paired by native IDs; a
missing ``tool_execution_complete`` or ``turn_end`` is tolerated as bounded
partial fidelity (never guessed). The family keeps a single capability
contract with an alias for vscode-copilot.
"""

from __future__ import annotations

from pathlib import Path
import json

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
    "session.start": EventKind.SESSION_LIFECYCLE,
    "session.shutdown": EventKind.SESSION_LIFECYCLE,
    "user.message": EventKind.USER_MESSAGE,
    "assistant.turn_start": EventKind.TURN_BOUNDARY,
    "assistant.message": EventKind.ASSISTANT_MESSAGE,
    "assistant.turn_end": EventKind.TURN_BOUNDARY,
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
    suffix = Path(artifact.relative_path or "").suffix.lower()
    if suffix not in (".jsonl", ".json"):
        return False
    try:
        path = artifact_root / artifact.artifact_id
        if suffix == ".json":
            doc = json.loads(path.read_text(encoding="utf-8"))
            return isinstance(doc, dict) and isinstance(doc.get("requests"), list)
        with path.open("r", encoding="utf-8") as h:
            for raw in h:
                line = raw.strip()
                if not line:
                    continue
                return (
                    '"turn_start"' in line or '"tool_execution_start"' in line
                    or '"assistant.turn_start"' in line or '"session.start"' in line
                )
    except OSError:
        return False
    return False


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id,
                               native_locator=locator),
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
    data = record.get("data") if isinstance(record.get("data"), dict) else record
    sid = record.get("session_id") or data.get("sessionId")
    native_id = (
        record.get("id") or data.get("toolId") or record.get("tool_id")
        or data.get("messageId") or record.get("message_id")
        or data.get("turnId") or record.get("turn_id")
        or data.get("interactionId")
    )
    if kind is None:
        return _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                      locator=locator, native_id=record.get("id"), occurred_at=ts,
                      fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                         RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                         CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                      native_session=sid)
    tool_id = record.get("tool_id") or data.get("toolId")
    if kind is EventKind.TOOL_RESULT and tool_id:
        # start and complete share the native tool_id; make_event_id omits
        # kind when a native id is present, so disambiguate the completion.
        native_id = f"{tool_id}#complete"
    return _event(artifact, session_id=session_id, kind=kind, locator=locator,
                  native_id=native_id, occurred_at=ts,
                  summary=str(data.get("content") or data.get("name") or "")[:2048] or None,
                  native_session=sid)


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one immutable Copilot trace into typed events/relations."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    records, malformed = _load_records(
        artifact_root / artifact.artifact_id, artifact.relative_path
    )

    session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator="session")
    events: list[TypedEvent] = []
    relations: list[EventRelation] = []
    warnings: list[str] = []
    if malformed:
        warnings.append(f"{malformed} malformed/native-corrupt record(s) skipped")
    tool_starts: dict[str, TypedEvent] = {}
    tool_ends: dict[str, TypedEvent] = {}
    native_session = next((
        r.get("session_id")
        or ((r.get("data") or {}).get("sessionId") if isinstance(r.get("data"), dict) else None)
        for r in records
        if r.get("session_id") or (
            isinstance(r.get("data"), dict) and (r.get("data") or {}).get("sessionId")
        )
    ), Path(artifact.relative_path).stem)

    for lineno, record in enumerate(records, start=1):
        ev = _adapt_record(record, artifact, session_id=session_id,
                           locator=f"{artifact.relative_path}#L{lineno}")
        if ev is None:
            continue
        events.append(ev)
        data = record.get("data") if isinstance(record.get("data"), dict) else {}
        tool_id = record.get("tool_id") or data.get("toolId")
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


def _load_records(path: Path, relative_path: str) -> tuple[list[dict], int]:
    if Path(relative_path).suffix.lower() == ".jsonl":
        values = list(iter_jsonl_lines(path, strict=False))
        nonblank = sum(1 for line in path.read_text(
            encoding="utf-8", errors="replace"
        ).splitlines() if line.strip("\x00 \t\r\n"))
        return values, max(0, nonblank - len(values))
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise EventContractError(f"{FAMILY} JSON artifact unreadable: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("requests"), list):
        raise EventContractError(f"{FAMILY} JSON export has no requests list")
    sid = str(doc.get("sessionId") or Path(relative_path).stem)
    records: list[dict] = [{
        "type": "session.start", "id": sid,
        "timestamp": doc.get("creationDate"), "data": {"sessionId": sid},
    }]
    for index, request in enumerate(doc["requests"]):
        if not isinstance(request, dict):
            continue
        message = request.get("message")
        if isinstance(message, dict):
            message = message.get("text")
        request_id = str(request.get("requestId") or f"request-{index}")
        records.append({
            "type": "user.message", "id": request_id,
            "timestamp": request.get("timestamp"),
            "data": {"sessionId": sid, "messageId": request_id, "content": message},
        })
        response_parts = request.get("response")
        text_parts: list[str] = []
        if isinstance(response_parts, list):
            for part in response_parts:
                if isinstance(part, dict) and isinstance(part.get("value"), str):
                    text_parts.append(part["value"])
        response_id = str(request.get("responseId") or f"{request_id}:response")
        records.append({
            "type": "assistant.message", "id": response_id,
            "timestamp": request.get("timestamp"),
            "data": {
                "sessionId": sid, "messageId": response_id,
                "content": "\n".join(text_parts),
            },
        })
    return records, 0
