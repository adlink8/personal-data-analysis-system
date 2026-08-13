"""Phase 62-03: Antigravity SQLite trajectory adapter (family ``antigravity``).

Antigravity stores a trajectory/step/subtrajectory hierarchy in SQLite
(62-RESEARCH format matrix). Capture is allowlisted so adjacent
credential tables are unreachable; this adapter reads only the declared
hierarchy tables. Hierarchical trajectory relations are preserved as typed
``parent_child`` / ``subagent`` relations, with explicit partial transcript
fidelity for step kinds that are not user/assistant prose.
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

FAMILY = "antigravity"
ADAPTER_VERSION = "1.0.0"
CONTRACT_VERSION = "1"

ALLOWED_TABLES: tuple[str, ...] = ("trajectories", "steps", "subtrajectories")
ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "trajectories": ("id", "name", "created_at"),
    "steps": ("id", "trajectory_id", "seq", "kind", "content", "created_at"),
    "subtrajectories": ("id", "step_id", "parent_trajectory_id", "content", "created_at"),
}
LIVE_ALLOWED_TABLES: tuple[str, ...] = ("trajectory_meta", "steps", "parent_references")
LIVE_ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "trajectory_meta": ("trajectory_id", "cascade_id", "trajectory_type", "source"),
    "steps": ("idx", "step_type", "status", "has_subtrajectory", "metadata", "error_details", "permissions", "task_details", "render_info", "step_payload", "step_format"),
    "parent_references": ("idx", "data"),
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

_STEP_KINDS = {
    "user": EventKind.USER_MESSAGE,
    "assistant": EventKind.ASSISTANT_MESSAGE,
    "tool": EventKind.TOOL_CALL,
    "reasoning": EventKind.REASONING,
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
            EventKind.TOOL_CALL, EventKind.COMPACTION_SUMMARY,
            EventKind.SUBAGENT_BOUNDARY, EventKind.UNKNOWN_NATIVE,
        ),
        supported_relation_kinds=(RelationKind.PARENT_CHILD, RelationKind.SUBAGENT),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "sqlite_trajectory_store",
            "hierarchy": "trajectory_step_subtrajectory",
            "transcript_fidelity": "partial_for_non_prose_steps",
        },
    )


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    if artifact.source_kind != "sqlite":
        return False
    try:
        con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name IN ('trajectories','trajectory_meta')"
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
    """Adapt one filtered Antigravity snapshot into typed events/relations."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    if artifact.source_kind != "sqlite":
        raise EventContractError(f"{FAMILY} adapter requires a sqlite artifact")
    try:
        con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            if "trajectory_meta" in tables:
                return _adapt_live_store(con, artifact)
            trajectories = con.execute("SELECT * FROM trajectories").fetchall()
            steps = con.execute("SELECT * FROM steps").fetchall()
            sub_flows = con.execute("SELECT * FROM subtrajectories").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise EventContractError(f"{FAMILY} artifact unreadable: {exc}") from exc

    sessions: list[AdaptedSession] = []
    events: list[TypedEvent] = []
    relations: list[EventRelation] = []
    warnings: list[str] = []
    by_step: dict[str, TypedEvent] = {}
    by_trajectory: dict[str, str] = {}
    unknown = 0

    for trajectory in trajectories:
        sid = str(trajectory["id"])
        session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                   sid, kind=EventKind.SESSION_LIFECYCLE)
        by_trajectory[sid] = session_id
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=_provenance(artifact, f"{artifact.relative_path}#trajectory:{sid}",
                                   session=sid, native_id=sid),
            fidelity=_fidelity(), native_session_id=sid, started_at=trajectory["created_at"],
        ))
        events.append(_event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                             locator=f"{artifact.relative_path}#trajectory:{sid}", native_id=sid,
                             occurred_at=trajectory["created_at"],
                             summary=str(trajectory["name"] or "")[:256] or None, native_session=sid))

    for step in steps:
        sid = str(step["trajectory_id"])
        session_id = by_trajectory.get(sid)
        if session_id is None:
            warnings.append(f"step {step['id']!r} references unknown trajectory {sid!r}")
            continue
        kind = _STEP_KINDS.get(step["kind"])
        locator = f"{artifact.relative_path}#step:{step['id']}"
        if kind is None:
            unknown += 1
            ev = _event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                        locator=locator, native_id=step["id"], occurred_at=step["created_at"],
                        fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                           RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                           CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                        native_session=sid)
            events.append(ev)
            by_step[str(step["id"])] = ev
            continue
        ev = _event(artifact, session_id=session_id, kind=kind, locator=locator,
                    native_id=step["id"], occurred_at=step["created_at"],
                    summary=str(step["content"] or "")[:2048] or None, native_session=sid)
        events.append(ev)
        by_step[str(step["id"])] = ev

    # Subtrajectories are side branches attached to a parent step.
    for sub in sub_flows:
        parent = by_step.get(str(sub["step_id"]))
        if parent is None:
            warnings.append(f"subtrajectory {sub['id']!r} references unknown step {sub['step_id']!r}")
            continue
        ev = _event(artifact, session_id=parent.session_id, kind=EventKind.SUBAGENT_BOUNDARY,
                    locator=f"{artifact.relative_path}#subtrajectory:{sub['id']}",
                    native_id=sub["id"], occurred_at=sub["created_at"],
                    summary=str(sub["content"] or "")[:2048] or None,
                    native_session=parent.provenance.native_session_id)
        events.append(ev)
        relations.append(EventRelation(
            relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                      f"rel-subagent:{ev.event_id}:{parent.event_id}"),
            source_event_id=ev.event_id, target_event_id=parent.event_id,
            relation_kind=RelationKind.SUBAGENT,
        ))

    # Every step belongs to its trajectory's session-lifecycle event.
    for step in steps:
        ev = by_step.get(str(step["id"]))
        if ev is None:
            continue
        session_id = by_trajectory.get(str(step["trajectory_id"]))
        anchor = next((e for e in events if e.session_id == session_id
                       and e.kind is EventKind.SESSION_LIFECYCLE), None)
        if anchor is not None and anchor.event_id != ev.event_id:
            relations.append(EventRelation(
                relation_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-parent:{ev.event_id}:{anchor.event_id}"),
                source_event_id=ev.event_id, target_event_id=anchor.event_id,
                relation_kind=RelationKind.PARENT_CHILD,
            ))

    if unknown:
        warnings.append(f"{unknown} unknown step kind(s) preserved")

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events),
        fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE,
                           RELATION_COMPLETENESS=FidelityLevel.PARTIAL if not relations else FidelityLevel.COMPLETE),
        sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
    )


def _adapt_live_store(
    con: sqlite3.Connection, artifact: SourceArtifact
) -> AdaptationResult:
    """Preserve the observed protobuf-backed schema without inventing payloads."""
    trajectories = con.execute("SELECT * FROM trajectory_meta").fetchall()
    steps = con.execute("SELECT * FROM steps ORDER BY idx").fetchall()
    sessions: list[AdaptedSession] = []
    events: list[TypedEvent] = []
    partial = _fidelity(
        STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
        RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
        CONTENT_AVAILABILITY=FidelityLevel.UNAVAILABLE,
        COMPACTION_VISIBILITY=FidelityLevel.UNKNOWN,
    )
    for trajectory in trajectories:
        native_session = str(trajectory["trajectory_id"])
        session_id = make_event_id(
            FAMILY, artifact.artifact_id, CONTRACT_VERSION, native_session,
            kind=EventKind.SESSION_LIFECYCLE,
        )
        locator = f"{artifact.relative_path}#trajectory:{native_session}"
        provenance = _provenance(
            artifact, locator, session=native_session, native_id=native_session
        )
        sessions.append(AdaptedSession(
            session_id=session_id, provenance=provenance,
            fidelity=partial, native_session_id=native_session,
        ))
        events.append(_event(
            artifact, session_id=session_id,
            kind=EventKind.SESSION_LIFECYCLE, locator=locator,
            native_id=native_session, fidelity=partial,
            native_session=native_session,
        ))
        for step in steps:
            step_id = f"{native_session}:step:{step['idx']}"
            step_locator = f"{artifact.relative_path}#step:{step['idx']}"
            events.append(TypedEvent(
                event_id=make_event_id(
                    FAMILY, artifact.artifact_id, CONTRACT_VERSION, step_id,
                    kind=EventKind.UNKNOWN_NATIVE, session_id=session_id,
                ),
                session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                provenance=_provenance(
                    artifact, step_locator, session=native_session,
                    native_id=step_id,
                ),
                fidelity=partial, ordinal=int(step["idx"]),
                native_payload_ref=f"{artifact.artifact_id}:{step_locator}",
                summary=f"step_type={step['step_type']};status={step['status']}",
            ))
    return AdaptationResult(
        family=FAMILY, adapter_version="1.1.0",
        contract_version=CONTRACT_VERSION, artifacts=(artifact,),
        sessions=tuple(sessions), events=tuple(events), relations=(),
        fidelity=partial,
        warnings=(
            "protobuf step payloads are preserved by reference; semantic decode unavailable",
        ),
    )
