"""Phase 62-03: ZCode SQLite adapter (family ``zcode``).

ZCode stores conversation parts in a SQLite store with native trace and
turn IDs (62-RESEARCH format matrix). Capture uses the allowlisted online
backup seam (:func:`capture_sqlite`) so credential-adjacent tables are
dropped before publishing; this adapter reads ONLY the declared
conversation tables from the filtered artifact. Trace IDs are preserved as
session identity without making trace a universal concept (D-20);
text/reasoning/tool/step/compaction parts map to typed events and turn
membership relations.
"""

from __future__ import annotations

import sqlite3
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
    RelationKind,
    TypedEvent,
    make_event_id,
)

FAMILY = "zcode"
ADAPTER_VERSION = "1.0.0"
CONTRACT_VERSION = "1"

ALLOWED_TABLES: tuple[str, ...] = ("conversation_traces", "conversation_parts")
ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "conversation_traces": ("trace_id", "title", "created_at"),
    "conversation_parts": ("part_id", "trace_id", "turn_id", "part_type",
                           "role", "content", "created_at"),
}

_COMPLETE = {
    FidelityDimension.SOURCE_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.STRUCTURE_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.ORDERING_CONFIDENCE: FidelityLevel.COMPLETE,
    FidelityDimension.RELATION_COMPLETENESS: FidelityLevel.COMPLETE,
    FidelityDimension.CONTENT_AVAILABILITY: FidelityLevel.COMPLETE,
    FidelityDimension.COMPACTION_VISIBILITY: FidelityLevel.COMPLETE,
    FidelityDimension.NATIVE_ID_STABILITY: FidelityLevel.COMPLETE,
}

_PART_KINDS = {
    "text": None,  # decided by role
    "reasoning": EventKind.REASONING,
    "tool": EventKind.TOOL_CALL,
    "step": EventKind.TURN_BOUNDARY,
    "compaction": EventKind.COMPACTION_SUMMARY,
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
            EventKind.ASSISTANT_MESSAGE, EventKind.REASONING,
            EventKind.TOOL_CALL, EventKind.TURN_BOUNDARY,
            EventKind.COMPACTION_SUMMARY, EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(RelationKind.TURN_MEMBERSHIP,),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "sqlite_virtual_locator",
            "tables": ",".join(ALLOWED_TABLES),
            "trace_semantics": "session_identity_only",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    if artifact.source_kind != "sqlite":
        return False
    try:
        con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='conversation_parts'"
            ).fetchall()
        finally:
            con.close()
    except sqlite3.Error:
        return False
    return bool(rows)


def _provenance(artifact: SourceArtifact, locator: str, *, session: str | None, native_id: str | None) -> Provenance:
    return Provenance(
        artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
        native_locator=locator, native_session_id=session or None,
        native_event_id=native_id, contract_version=CONTRACT_VERSION,
    )


def _event(artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
           summary=None, fidelity=None, native_session=None) -> TypedEvent:
    return TypedEvent(
        event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               native_id or locator, kind=kind, session_id=session_id),
        session_id=session_id, kind=kind,
        provenance=_provenance(artifact, locator, session=native_session, native_id=native_id),
        fidelity=fidelity or _fidelity(), occurred_at=occurred_at, summary=summary,
    )


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one filtered ZCode snapshot into typed events/relations."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    blob = artifact_root / artifact.artifact_id
    if artifact.source_kind != "sqlite":
        raise EventContractError(f"{FAMILY} adapter requires a sqlite artifact")

    try:
        con = sqlite3.connect(f"file:{blob}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            traces = con.execute("SELECT * FROM conversation_traces").fetchall()
            parts = con.execute("SELECT * FROM conversation_parts").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise EventContractError(f"{FAMILY} artifact unreadable: {exc}") from exc

    sessions: list[AdaptedSession] = []
    events: list[TypedEvent] = []
    relations: list[EventRelation] = []
    warnings: list[str] = []
    by_part: dict[str, TypedEvent] = {}
    unknown = 0

    for trace in traces:
        sid = str(trace["trace_id"])
        session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                   sid, kind=EventKind.SESSION_LIFECYCLE)
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(artifact, f"{artifact.relative_path}#trace:{sid}",
                                   session=sid, native_id=sid),
            fidelity=_fidelity(), native_session_id=sid,
            started_at=trace["created_at"],
        ))
        events.append(_event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                             locator=f"{artifact.relative_path}#trace:{sid}", native_id=sid,
                             occurred_at=trace["created_at"],
                             summary=str(trace["title"] or "")[:256] or None, native_session=sid))

    for part in parts:
        sid = str(part["trace_id"])
        session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                   sid, kind=EventKind.SESSION_LIFECYCLE)
        ptype = part["part_type"]
        kind = _PART_KINDS.get(ptype)
        locator = f"{artifact.relative_path}#part:{part['part_id']}"
        if kind is None:
            if ptype == "text":
                role = part["role"]
                kind = EventKind.USER_MESSAGE if role == "user" else (
                    EventKind.ASSISTANT_MESSAGE if role == "assistant" else None)
            if kind is None:
                unknown += 1
                ev = _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                            locator=locator, native_id=part["part_id"],
                            occurred_at=part["created_at"],
                            fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                               RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                               CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                            native_session=sid)
                events.append(ev)
                by_part[part["part_id"]] = ev
                continue
        ev = _event(artifact, session_id=session_id, kind=kind, locator=locator,
                    native_id=part["part_id"], occurred_at=part["created_at"],
                    summary=str(part["content"] or "")[:2048] or None, native_session=sid)
        events.append(ev)
        by_part[part["part_id"]] = ev

    # Turn membership: parts of the same native turn link to one another (the
    # first part of the turn is the anchor).
    turn_groups: dict[str, list[str]] = {}
    for part in parts:
        turn_groups.setdefault(str(part["turn_id"]), []).append(str(part["part_id"]))
    for turn_parts in turn_groups.values():
        anchor = next((by_part[p] for p in turn_parts if p in by_part), None)
        if anchor is None:
            continue
        for pid in turn_parts:
            member = by_part.get(pid)
            if member is not None and member.event_id != anchor.event_id:
                relations.append(EventRelation(
                    relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                              f"rel-turn:{member.event_id}:{anchor.event_id}"),
                    source_event_id=member.event_id, target_event_id=anchor.event_id,
                    relation_kind=RelationKind.TURN_MEMBERSHIP,
                ))

    if unknown:
        warnings.append(f"{unknown} unknown part type(s) preserved")

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events),
        fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )
