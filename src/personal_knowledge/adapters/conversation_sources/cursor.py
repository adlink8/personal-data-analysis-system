"""Phase 62-03: Cursor versioned-discovery adapter (family ``cursor``).

Cursor stores session/thread identity in machine-local project/database
artifacts whose schema varies by version. This adapter versions its schema
probe: supported thread/session stores are distinguished from
attribution-only databases, unsafe/ambiguous stores fail closed, and the
single observed family is represented without inventing native semantics.
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
    FidelityDimension,
    FidelityLevel,
    FidelityProfile,
    Provenance,
    TypedEvent,
    make_event_id,
)

FAMILY = "cursor"
ADAPTER_VERSION = "1.0.0"
CONTRACT_VERSION = "1"

# Versioned schema probes: supported stores carry thread/session tables.
SUPPORTED_PROBES: dict[str, tuple[str, ...]] = {
    "v1": ("threads", "messages"),
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


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


def capability() -> CapabilityDescriptor:
    return CapabilityDescriptor(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        supported_event_kinds=(EventKind.SESSION_LIFECYCLE, EventKind.USER_MESSAGE,
                               EventKind.ASSISTANT_MESSAGE, EventKind.UNKNOWN_NATIVE),
        supported_relation_kinds=(),
        fidelity_dimensions=tuple(FidelityDimension),
        capabilities={
            "native_shape": "machine_local_project_database",
            "schema_probes": "v1(threads,messages)",
            "ambiguous_stores": "fail_closed",
        },
    )


def _probe_schema(db: Path) -> tuple[str | None, set[str]]:
    """Return (probe_version, present_table_names); None version = unsupported."""
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
        finally:
            con.close()
    except sqlite3.Error:
        return None, set()
    for version, required in SUPPORTED_PROBES.items():
        if set(required) <= tables:
            return version, tables
    return None, tables


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """True for a Cursor store whose schema matches a supported probe version."""
    if artifact.source_kind != "sqlite":
        return False
    version, _tables = _probe_schema(artifact_root / artifact.artifact_id)
    return version is not None


def adapt(artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    """Adapt one supported Cursor store; attribution-only/ambiguous stores
    fail closed with an honest blocked result."""
    if len(artifact_set.artifacts) != 1:
        raise EventContractError(
            f"{FAMILY} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
        )
    artifact = artifact_set.artifacts[0]
    if artifact.source_kind != "sqlite":
        raise EventContractError(f"{FAMILY} adapter requires a sqlite artifact")

    version, tables = _probe_schema(artifact_root / artifact.artifact_id)
    if version is None:
        # Unsafe/ambiguous/attribution-only store: honest blocked result.
        session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                                   None, kind=EventKind.SESSION_LIFECYCLE, native_locator="blocked")
        blocked = _fidelity(SOURCE_AVAILABILITY=FidelityLevel.PARTIAL,
                            STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                            CONTENT_AVAILABILITY=FidelityLevel.UNAVAILABLE)
        return AdaptationResult(
            family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            artifacts=(artifact,), events=(), fidelity=blocked, sessions=(), relations=(),
            warnings=(f"schema not supported by any probe version; present tables: {sorted(tables)[:8]}",),
        )

    session_id = make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION,
                               None, kind=EventKind.SESSION_LIFECYCLE, native_locator=f"probe:{version}")
    events: list[TypedEvent] = []
    sessions: list[AdaptedSession] = []

    try:
        con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            threads = con.execute("SELECT * FROM threads").fetchall()
            messages = con.execute("SELECT * FROM messages").fetchall()
        finally:
            con.close()
    except sqlite3.Error as exc:
        raise EventContractError(f"{FAMILY} artifact unreadable: {exc}") from exc

    if not threads:
        return AdaptationResult(
            family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            artifacts=(artifact,), events=(), fidelity=_fidelity(RELATION_COMPLETENESS=FidelityLevel.PARTIAL),
            sessions=(), relations=(), warnings=("threads table is empty (partial)",),
        )

    for thread in threads:
        tid = str(thread["id"] if "id" in thread.keys() else thread[0])
        locator = f"{artifact.relative_path}#thread:{tid}"
        sessions.append(AdaptedSession(
            session_id=session_id,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=tid, native_event_id=tid,
                contract_version=CONTRACT_VERSION,
            ),
            fidelity=_fidelity(), native_session_id=tid,
        ))
        events.append(TypedEvent(
            event_id=session_id,
            session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=tid, native_event_id=tid,
                contract_version=CONTRACT_VERSION,
            ),
            fidelity=_fidelity(),
            occurred_at=thread["created_at"] if "created_at" in thread.keys() else None,
            summary=str(thread["title"] if "title" in thread.keys() else "")[:256] or None,
        ))

    for message in messages:
        if "role" not in message.keys():
            continue
        role = message["role"]
        kind = EventKind.USER_MESSAGE if role == "user" else (
            EventKind.ASSISTANT_MESSAGE if role in ("assistant", "model") else None)
        locator = f"{artifact.relative_path}#message:{message['id'] if 'id' in message.keys() else len(events)}"
        if kind is None:
            events.append(TypedEvent(
                event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION, locator,
                                       kind=EventKind.UNKNOWN_NATIVE, session_id=session_id),
                session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                provenance=Provenance(
                    artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                    native_locator=locator, native_session_id=session_id,
                    native_event_id=message["id"] if "id" in message.keys() else None,
                    contract_version=CONTRACT_VERSION,
                ),
                fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                   RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                   CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
            ))
            continue
        events.append(TypedEvent(
            event_id=make_event_id(FAMILY, artifact.artifact_id, CONTRACT_VERSION, locator,
                                   kind=kind, session_id=session_id),
            session_id=session_id, kind=kind,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=session_id,
                native_event_id=message["id"] if "id" in message.keys() else None,
                contract_version=CONTRACT_VERSION,
            ),
            fidelity=_fidelity(),
            occurred_at=message["created_at"] if "created_at" in message.keys() else None,
            summary=str(message["content"] if "content" in message.keys() else "")[:2048] or None,
        ))

    return AdaptationResult(
        family=FAMILY, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
        artifacts=(artifact,), events=tuple(events), fidelity=_fidelity(),
        sessions=tuple(sessions), relations=(), warnings=(),
    )
