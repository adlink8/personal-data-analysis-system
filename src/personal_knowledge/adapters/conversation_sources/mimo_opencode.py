"""Phase 62-03: MimoCode / OpenCode SQLite adapters (families ``mimo``, ``opencode``).

Both families store sessions/messages/message_parts in a SQLite virtual
locator whose database also holds sensitive adjacent account/token tables.
Capture is allowlisted (declared tables/columns only) so those tables are
technically unreachable; this adapter reads only the declared conversation
tables from the filtered artifact. The two families share the parser
primitives but keep separate capability contracts and detection.
"""

from __future__ import annotations

import sqlite3
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
    RelationKind,
    TypedEvent,
    make_event_id,
)

ADAPTER_VERSION = "1.1.0"
CONTRACT_VERSION = "1"

ALLOWED_TABLES: tuple[str, ...] = ("sessions", "messages", "message_parts")
ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "sessions": ("id", "title", "created_at"),
    "messages": ("id", "session_id", "role", "content", "created_at"),
    "message_parts": ("id", "message_id", "part_type", "content", "created_at"),
}

LIVE_ALLOWED_TABLES: tuple[str, ...] = ("session", "message", "part")
LIVE_ALLOWED_COLUMNS: dict[str, tuple[str, ...]] = {
    "session": ("id", "parent_id", "title", "time_created", "time_updated", "time_compacting"),
    "message": ("id", "session_id", "time_created", "time_updated", "data"),
    "part": ("id", "message_id", "session_id", "time_created", "time_updated", "data"),
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
    "reasoning": EventKind.REASONING,
    "tool": EventKind.TOOL_CALL,
    "compaction": EventKind.COMPACTION_SUMMARY,
    "step-start": EventKind.TURN_BOUNDARY,
    "step-finish": EventKind.TURN_BOUNDARY,
    "file": EventKind.FILE_CONTEXT,
}


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


class _Family:
    def __init__(self, family: str):
        self.family = family

    def capability(self) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            family=self.family, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            supported_event_kinds=(
                EventKind.SESSION_LIFECYCLE, EventKind.USER_MESSAGE,
                EventKind.ASSISTANT_MESSAGE, EventKind.REASONING,
                EventKind.TOOL_CALL, EventKind.COMPACTION_SUMMARY,
                EventKind.UNKNOWN_NATIVE,
            ),
            supported_relation_kinds=(RelationKind.PARENT_CHILD,),
            fidelity_dimensions=tuple(FidelityDimension),
            capabilities={
                "native_shape": "sqlite_virtual_locator",
                "tables": ",".join(ALLOWED_TABLES),
                "adjacent_tables": "forbidden_by_capture_allowlist",
            },
        )

    def detect(self, artifact: SourceArtifact, *, artifact_root: Path) -> bool:
        if artifact.source_kind != "sqlite":
            return False
        try:
            con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
            try:
                rows = con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('messages','message')"
                ).fetchall()
            finally:
                con.close()
        except sqlite3.Error:
            return False
        return bool(rows)

    def _event(self, artifact, *, session_id, kind, locator, native_id=None, occurred_at=None,
               content=None, summary=None, fidelity=None, native_session=None) -> TypedEvent:
        return TypedEvent(
            event_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                   native_id or locator, kind=kind, session_id=session_id),
            session_id=session_id, kind=kind,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=native_session or None,
                native_event_id=native_id, contract_version=CONTRACT_VERSION,
            ),
            fidelity=fidelity or _fidelity(), occurred_at=occurred_at,
            content=content, summary=summary,
        )

    def adapt(self, artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
        if len(artifact_set.artifacts) != 1:
            raise EventContractError(
                f"{self.family} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
            )
        artifact = artifact_set.artifacts[0]
        if artifact.source_kind != "sqlite":
            raise EventContractError(f"{self.family} adapter requires a sqlite artifact")
        try:
            con = sqlite3.connect(f"file:{artifact_root / artifact.artifact_id}?mode=ro", uri=True)
            con.row_factory = sqlite3.Row
            try:
                tables = {r[0] for r in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )}
                live = {"session", "message", "part"} <= tables
                sessions_rows = con.execute(
                    "SELECT * FROM session" if live else "SELECT * FROM sessions"
                ).fetchall()
                messages = con.execute(
                    "SELECT * FROM message" if live else "SELECT * FROM messages"
                ).fetchall()
                parts = con.execute(
                    "SELECT * FROM part" if live else "SELECT * FROM message_parts"
                ).fetchall()
            finally:
                con.close()
        except sqlite3.Error as exc:
            raise EventContractError(f"{self.family} artifact unreadable: {exc}") from exc

        sessions: list[AdaptedSession] = []
        events: list[TypedEvent] = []
        relations: list[EventRelation] = []
        warnings: list[str] = []
        by_message: dict[str, TypedEvent] = {}
        unknown = 0

        for row in sessions_rows:
            sid = str(row["id"])
            session_id = make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                       sid, kind=EventKind.SESSION_LIFECYCLE)
            sessions.append(AdaptedSession(
                session_id=session_id,
                provenance=Provenance(
                    artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                    native_locator=f"{artifact.relative_path}#session:{sid}",
                    native_session_id=sid, native_event_id=sid, contract_version=CONTRACT_VERSION,
                ),
                fidelity=_fidelity(
                    COMPACTION_VISIBILITY=FidelityLevel.PARTIAL if live else FidelityLevel.COMPLETE
                ), native_session_id=sid,
                started_at=row["time_created"] if live else row["created_at"],
            ))
            events.append(self._event(artifact, session_id=session_id, kind=EventKind.SESSION_LIFECYCLE,
                                      locator=f"{artifact.relative_path}#session:{sid}", native_id=sid,
                                      occurred_at=row["time_created"] if live else row["created_at"],
                                      summary=str(row["title"] or "")[:256] or None, native_session=sid))

        for msg in messages:
            sid = str(msg["session_id"])
            session_id = make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                       sid, kind=EventKind.SESSION_LIFECYCLE)
            data = _json_object(msg["data"]) if live else dict(msg)
            role = data.get("role")
            kind = EventKind.USER_MESSAGE if role == "user" else (
                EventKind.ASSISTANT_MESSAGE if role == "assistant" else None)
            locator = f"{artifact.relative_path}#message:{msg['id']}"
            if kind is None:
                unknown += 1
                ev = self._event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                                 locator=locator, native_id=msg["id"],
                                 occurred_at=msg["time_created"] if live else msg["created_at"],
                                 fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                                    RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                                    CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                                 native_session=sid)
                events.append(ev)
                by_message[str(msg["id"])] = ev
                continue
            raw_content = data.get("content")
            ev = self._event(
                artifact, session_id=session_id, kind=kind, locator=locator,
                native_id=msg["id"],
                occurred_at=msg["time_created"] if live else msg["created_at"],
                content=None if raw_content is None else str(raw_content),
                native_session=sid,
            )
            events.append(ev)
            by_message[str(msg["id"])] = ev

        for part in parts:
            parent = by_message.get(str(part["message_id"]))
            if parent is None:
                continue
            part_data = _json_object(part["data"]) if live else dict(part)
            part_type = part_data.get("type") if live else part["part_type"]
            kind = _PART_KINDS.get(part_type)
            if live and part_type == "text":
                kind = parent.kind
            if kind is None:
                unknown += 1
                kind = EventKind.UNKNOWN_NATIVE
            raw_content = (
                part_data.get("text")
                if "text" in part_data
                else part_data.get("content")
            )
            text = None if raw_content is None else str(raw_content)
            is_message = kind in {
                EventKind.USER_MESSAGE,
                EventKind.ASSISTANT_MESSAGE,
                EventKind.DEVELOPER_MESSAGE,
                EventKind.SYSTEM_MESSAGE,
            }
            ev = self._event(
                artifact, session_id=parent.session_id, kind=kind,
                locator=f"{artifact.relative_path}#part:{part['id']}",
                native_id=part["id"],
                occurred_at=part["time_created"] if live else part["created_at"],
                content=text if is_message else None,
                summary=None if is_message else (text[:2048] if text else None),
                native_session=parent.provenance.native_session_id,
            )
            events.append(ev)
            relations.append(EventRelation(
                relation_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-parent:{ev.event_id}:{parent.event_id}"),
                source_event_id=ev.event_id, target_event_id=parent.event_id,
                relation_kind=RelationKind.PARENT_CHILD,
            ))

        if unknown:
            warnings.append(f"{unknown} unknown native record(s) preserved")

        return AdaptationResult(
            family=self.family, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            artifacts=(artifact,), events=tuple(events),
            fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE),
            sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
        )


def _json_object(value) -> dict:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except ValueError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


_FAMILIES = {
    "mimo": _Family("mimo"),
    "opencode": _Family("opencode"),
}


def capability(family: str) -> CapabilityDescriptor:
    return _FAMILIES[family].capability()


def detect(artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    """Detection is family-agnostic here; ownership is resolved by the caller."""
    return _FAMILIES["mimo"].detect(artifact, artifact_root=artifact_root)


def adapt_family(family: str):
    return _FAMILIES[family].adapt


def adapt(family: str, artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    return _FAMILIES[family].adapt(artifact_set, artifact_root=artifact_root)
