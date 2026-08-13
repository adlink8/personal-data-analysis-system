"""Phase 62-02: Pi JSONL event-stream adapter (family ``pi``).

Pi exports an independent JSONL event stream (62-RESEARCH format matrix)
where compaction is a typed event carrying ``summary``,
``firstKeptEntryId`` and ``tokensBefore`` — never a user message. We emit
``compaction_summary`` events plus a ``compacted_range`` relation from the
compaction to its first kept entry. Missing native IDs, unknown kinds and
malformed lines fail closed or report bounded partial fidelity.
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

FAMILY = "pi"
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


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(
            EventKind.SESSION_LIFECYCLE, EventKind.USER_MESSAGE,
            EventKind.ASSISTANT_MESSAGE, EventKind.COMPACTION_SUMMARY,
            EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(RelationKind.COMPACTED_RANGE,),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "jsonl_event_stream",
            "compaction": "independent_record_with_range_metadata",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """Probe the first non-blank line for a Pi ``conversation`` record."""
    if not (artifact.relative_path or "").lower().endswith(".jsonl"):
        return False
    try:
        with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
            for raw in h:
                line = raw.strip()
                if not line:
                    continue
                return '"type"' in line and (
                    '"conversation"' in line or '"session"' in line
                )
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


def _adapt_record(record: dict, artifact, *, session_id, locator, native_session) -> TypedEvent | None:
    kind = record.get("type")
    ts = record.get("timestamp")
    mid = record.get("message_id")
    if kind == "conversation":
        return _event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                      locator=locator, native_id=record.get("id"), occurred_at=ts,
                      summary=str(record.get("title") or "")[:256] or None, native_session=native_session)
    if kind == "session":
        return _event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                      locator=locator, native_id=record.get("id"), occurred_at=ts,
                      native_session=native_session)
    if kind == "message":
        message = record.get("message") if isinstance(record.get("message"), dict) else {}
        role = message.get("role")
        message_kind = (
            EventKind.USER_MESSAGE if role == "user" else
            EventKind.ASSISTANT_MESSAGE if role == "assistant" else
            EventKind.SYSTEM_MESSAGE if role == "system" else
            EventKind.UNKNOWN_NATIVE
        )
        return _event(
            artifact, session_id=session_id, kind=message_kind,
            locator=locator, native_id=record.get("id"), occurred_at=ts,
            summary=_message_text(message.get("content")),
            fidelity=(None if message_kind is not EventKind.UNKNOWN_NATIVE else _fidelity(
                STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
            )),
            native_session=native_session,
        )
    if kind == "user_message":
        return _event(artifact, session_id=session_id, kind=EventKind.USER_MESSAGE,
                      locator=locator, native_id=mid, occurred_at=ts,
                      summary=str(record.get("content") or "")[:2048] or None, native_session=native_session)
    if kind == "assistant_message":
        return _event(artifact, session_id=session_id, kind=EventKind.ASSISTANT_MESSAGE,
                      locator=locator, native_id=mid, occurred_at=ts,
                      summary=str(record.get("content") or "")[:2048] or None, native_session=native_session)
    if kind == "compaction":
        return _event(artifact, session_id=session_id, kind=EventKind.COMPACTION_SUMMARY,
                      locator=locator, native_id=mid or record.get("id"), occurred_at=ts,
                      summary=str(record.get("summary") or "")[:2048] or None, native_session=native_session)
    if kind in ("model_change", "thinking_level_change"):
        return _event(
            artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
            locator=locator, native_id=record.get("id"), occurred_at=ts,
            fidelity=_fidelity(
                STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
            ), native_session=native_session,
        )
    return _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                  locator=locator, native_id=mid, occurred_at=ts,
                  fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                     RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                     CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                  native_session=native_session)


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one immutable Pi export into typed events/relations."""
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
    native_session = next(
        (r.get("conversation_id") for r in records if r.get("conversation_id")),
        next((r.get("id") for r in records if r.get("type") == "session"), None),
    )
    by_mid: dict[str, TypedEvent] = {}

    for lineno, record in enumerate(records, start=1):
        ev = _adapt_record(record, artifact, session_id=session_id,
                           locator=f"{artifact.relative_path}#L{lineno}", native_session=native_session)
        if ev is None:
            continue
        events.append(ev)
        if record.get("message_id"):
            by_mid[record["message_id"]] = ev

    for record, ev in zip(records, events):
        if record.get("type") != "compaction":
            continue
        first_kept = record.get("firstKeptEntryId")
        target = by_mid.get(first_kept)
        if target is None:
            warnings.append(f"compaction firstKeptEntryId {first_kept!r} not in file (partial range)")
            continue
        relations.append(EventRelation(
            relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                      f"rel-compact:{ev.event_id}"),
            source_event_id=ev.event_id, target_event_id=target.event_id,
            relation_kind=RelationKind.COMPACTED_RANGE,
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

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events),
        fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )


def _message_text(content) -> str | None:
    if isinstance(content, str):
        return content[:2048] or None
    if isinstance(content, list):
        values = []
        for item in content:
            if isinstance(item, dict):
                value = item.get("text") or item.get("content")
                if value:
                    values.append(str(value))
        return " ".join(values)[:2048] or None
    return None
