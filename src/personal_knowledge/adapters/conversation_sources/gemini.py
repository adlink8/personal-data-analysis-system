"""Phase 62-02: Gemini single-JSON adapter (family ``gemini``).

Gemini exports one JSON document with ordered ``messages`` plus metadata.
The whole file is one immutable snapshot; ordered messages map to typed
user/assistant events and unknown top-level fields are preserved by
reference (never silently dropped). ``native_payload_ref`` records the
source slice for unmodeled fields (D-07).
"""

from __future__ import annotations

import json
from pathlib import Path

from personal_knowledge.adapters.conversation_sources.contracts import (
    AdaptationResult,
    CapabilityDescriptor,
    SourceArtifact,
    SourceArtifactSet,
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
    TypedEvent,
    make_event_id,
)

FAMILY = "gemini"
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
            EventKind.ASSISTANT_MESSAGE, EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "single_json",
            "unmodeled_fields": "preserved_by_reference",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    if not (artifact.relative_path or "").lower().endswith(".json"):
        return False
    try:
        with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
            doc = json.load(h)
    except (OSError, ValueError):
        return False
    return isinstance(doc, dict) and isinstance(doc.get("messages"), list)


def _provenance(artifact: SourceArtifact, locator: str, *, session: str | None, native_id: str | None) -> Provenance:
    return Provenance(
        artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
        native_locator=locator, native_session_id=session or None,
        native_event_id=native_id, contract_version=CONTRACT_VERSION,
    )


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           content=None, summary=None, fidelity=None, native_session=None,
           payload_ref=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id),
        session_id=session_id, kind=kind,
        provenance=_provenance(artifact, locator, session=native_session, native_id=native_id),
        fidelity=fidelity or _fidelity(), occurred_at=occurred_at,
        content=content, summary=summary,
        native_payload_ref=payload_ref,
    )


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one immutable Gemini JSON document into typed events."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    try:
        with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
            doc = json.load(h)
    except (OSError, ValueError) as exc:
        raise EventContractError(f"{FAMILY} artifact is not a JSON document: {exc}") from exc

    if not isinstance(doc, dict) or not isinstance(doc.get("messages"), list):
        raise EventContractError(f"{FAMILY} artifact has no ordered messages array")

    session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator="session")
    events: list[TypedEvent] = []
    native_session = doc.get("session_id") or doc.get("sessionId") or doc.get("id")

    events.append(_event(
        artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
        locator=f"{artifact.relative_path}#root", native_id=str(native_session or "root"),
        occurred_at=doc.get("created_at"),
        summary=str(doc.get("model") or "")[:128] or None,
        native_session=native_session,
    ))

    for index, message in enumerate(doc["messages"]):
        if not isinstance(message, dict):
            continue
        role = message.get("role") or message.get("type")
        kind = EventKind.USER_MESSAGE if role in ("user", "human") else (
            EventKind.ASSISTANT_MESSAGE if role in ("model", "assistant", "ai") else None)
        locator = f"{artifact.relative_path}#messages[{index}]"
        if kind is None:
            events.append(_event(
                artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                locator=locator, native_id=message.get("id") or f"msg-{index}",
                occurred_at=message.get("timestamp"),
                fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                   RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                   CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                native_session=native_session, payload_ref=locator,
            ))
            continue
        events.append(_event(
            artifact, session_id=session_id, kind=kind, locator=locator,
            native_id=message.get("id") or f"msg-{index}",
            occurred_at=message.get("timestamp"),
            content=(
                None if message.get("content") is None
                else str(message.get("content"))
            ),
            native_session=native_session, payload_ref=locator,
        ))

    unknown = sum(1 for e in events if e.kind is EventKind.UNKNOWN_NATIVE)

    sessions: list[AdaptedSession] = []
    if native_session:
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(artifact, f"{artifact.relative_path}#root",
                                   session=str(native_session), native_id=str(native_session)),
            fidelity=_fidelity(), native_session_id=str(native_session),
        ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events),
        fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE),
        sessions=tuple(sessions), relations=(), warnings=(
            (f"{unknown} unknown message role(s) preserved",) if unknown else ()
        ),
    )
