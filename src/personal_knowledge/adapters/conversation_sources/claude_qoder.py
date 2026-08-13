"""Phase 62-02: Claude / Qoder JSONL DAG adapters (families ``claude``, ``qoder``).

Both families export a UUID-parent DAG as JSONL (62-RESEARCH format
matrix): ``uuid``, ``parentUuid``, ``isSidechain``, content blocks. Parent
relations are authoritative — file order alone is insufficient — so we emit
``parent_child`` / ``sidechain`` typed relations and never guess relations
from adjacency. Qoder adds an explicit ``isCompactSummary`` record, which
becomes a ``compaction_summary`` event, not a user message. Each family
keeps its own detector, schema gate and capability/fidelity outcomes.
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


def _record_kind(record: dict) -> EventKind | None:
    """Typed kind for a DAG record; None means unknown native."""
    if record.get("isCompactSummary"):
        return EventKind.COMPACTION_SUMMARY
    rtype = record.get("type")
    if rtype in ("user", "human"):
        return EventKind.USER_MESSAGE
    if rtype in ("assistant", "ai"):
        return EventKind.ASSISTANT_MESSAGE
    if rtype == "tool_use":
        return EventKind.TOOL_CALL
    if rtype == "tool_result":
        return EventKind.TOOL_RESULT
    if rtype in ("system", "system_message"):
        return EventKind.SYSTEM_MESSAGE
    return None


def _text_content(record: dict) -> str | None:
    """Text from content blocks; tool blocks are not treated as prose."""
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    blocks = record.get("content", message.get("content"))
    if isinstance(blocks, str):
        return blocks[:2048] or None
    if isinstance(blocks, list):
        parts = [
            str(b.get("text") or "") for b in blocks
            if isinstance(b, dict) and b.get("type") == "text" and b.get("text")
        ]
        return (" ".join(parts))[:2048] or None
    return None


class _Family:
    def __init__(self, family: str, *, dag_shape: bool = True, markers: tuple[str, ...] = ()):
        self.family = family
        self.dag_shape = dag_shape
        self.markers = markers

    def capability(self) -> CapabilityDescriptor:
        kinds = {
            EventKind.SESSION_LIFECYCLE, EventKind.USER_MESSAGE,
            EventKind.ASSISTANT_MESSAGE, EventKind.SYSTEM_MESSAGE,
            EventKind.TOOL_CALL, EventKind.TOOL_RESULT,
            EventKind.COMPACTION_SUMMARY, EventKind.UNKNOWN_NATIVE,
        }
        relations = {RelationKind.PARENT_CHILD, RelationKind.SIDECHAIN}
        if self.family == "qoder":
            relations.add(RelationKind.COMPACTED_RANGE)
        return CapabilityDescriptor(
            family=self.family, adapter_version=ADAPTER_VERSION,
            contract_version=CONTRACT_VERSION,
            supported_event_kinds=tuple(sorted(kinds, key=lambda k: k.value)),
            supported_relation_kinds=tuple(sorted(relations, key=lambda r: r.value)),
            fidelity_dimensions=tuple(FidelityDimension),
            capabilities={
                "native_shape": "jsonl_uuid_dag",
                "relations": "parent_uuid_authoritative",
                "compaction": "explicit_compact_summary" if self.family == "qoder" else "content_blocks",
            },
        )

    def detect(self, artifact: SourceArtifact, *, artifact_root: Path) -> bool:
        if not (artifact.relative_path or "").lower().endswith(".jsonl"):
            return False
        try:
            lines = (artifact_root / artifact.artifact_id).read_text(encoding="utf-8").splitlines()
        except OSError:
            return False
        if self.dag_shape and not any('"uuid"' in l and '"parentUuid"' in l for l in lines):
            return False
        return any(m in l for l in lines for m in self.markers) if self.markers else True

    def _event(self, artifact, *, session_id, kind, locator, native_id=None,
               occurred_at=None, summary=None, fidelity=None, native_session=None) -> TypedEvent:
        return TypedEvent(
            event_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                   native_id or locator, kind=kind, session_id=session_id),
            session_id=session_id, kind=kind,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=native_session or None,
                native_event_id=native_id, contract_version=CONTRACT_VERSION,
            ),
            fidelity=fidelity or _fidelity(), occurred_at=occurred_at, summary=summary,
        )

    def _adapt_record(self, record: dict, artifact, *, session_id, locator) -> TypedEvent | None:
        kind = _record_kind(record)
        ts = record.get("timestamp")
        sid = record.get("session_id") or record.get("sessionId")
        if kind is None:
            return self._event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                               locator=locator, native_id=record.get("uuid"), occurred_at=ts,
                               fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                                  RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                                  CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                               native_session=sid)
        return self._event(artifact, session_id=session_id, kind=kind, locator=locator,
                           native_id=record.get("uuid"), occurred_at=ts,
                           summary=_text_content(record), native_session=sid)

    def adapt(self, artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
        if len(artifact_set.artifacts) != 1:
            raise EventContractError(
                f"{self.family} adapter requires exactly one artifact, got {len(artifact_set.artifacts)}"
            )
        artifact = artifact_set.artifacts[0]
        records = list(iter_jsonl_lines(artifact_root / artifact.artifact_id))

        session_id = make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                   None, kind=EventKind.SESSION_LIFECYCLE, native_locator="session")
        events: list[TypedEvent] = []
        relations: list[EventRelation] = []
        warnings: list[str] = []
        by_uuid: dict[str, TypedEvent] = {}
        parent_links: list[tuple[TypedEvent, str, bool]] = []
        native_session = next((
            r.get("session_id") or r.get("sessionId")
            for r in records if r.get("session_id") or r.get("sessionId")
        ), Path(artifact.relative_path).stem)

        for lineno, record in enumerate(records, start=1):
            ev = self._adapt_record(record, artifact, session_id=session_id,
                                    locator=f"{artifact.relative_path}#L{lineno}")
            if ev is None:
                continue
            events.append(ev)
            uuid = record.get("uuid")
            if not uuid:
                continue
            by_uuid[uuid] = ev
            parent = record.get("parentUuid")
            if parent:
                parent_links.append((ev, parent, bool(record.get("isSidechain"))))

        for child, parent_uuid, sidechain in parent_links:
            parent_ev = by_uuid.get(parent_uuid)
            if parent_ev is None:
                warnings.append(f"uuid {parent_uuid!r} has no in-file parent (partial relation)")
                continue
            relations.append(EventRelation(
                relation_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-dag:{child.event_id}:{parent_ev.event_id}"),
                source_event_id=child.event_id, target_event_id=parent_ev.event_id,
                relation_kind=RelationKind.SIDECHAIN if sidechain else RelationKind.PARENT_CHILD,
            ))

        if self.family == "qoder":
            for compact_ev in [e for e in events if e.kind is EventKind.COMPACTION_SUMMARY]:
                earliest = min((e for e in events if e.kind is not EventKind.COMPACTION_SUMMARY),
                               key=lambda e: e.ordinal or 0, default=None)
                if earliest is not None and earliest.event_id != compact_ev.event_id:
                    relations.append(EventRelation(
                        relation_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                                  f"rel-compact:{compact_ev.event_id}"),
                        source_event_id=compact_ev.event_id, target_event_id=earliest.event_id,
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
            family=self.family, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            artifacts=(artifact,), events=tuple(events),
            fidelity=_fidelity(
                STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE,
                RELATION_COMPLETENESS=(
                    FidelityLevel.PARTIAL
                    if parent_links and len(relations) < len(parent_links)
                    else FidelityLevel.COMPLETE
                ),
            ),
            sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
        )


_FAMILIES = {
    "claude": _Family("claude", markers=('"stop_reason"', '"isSidechain"')),
    "qoder": _Family("qoder", markers=('"isCompactSummary"',)),
}


def capability(family: str) -> CapabilityDescriptor:
    return _FAMILIES[family].capability()


def detect(family: str, artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    return _FAMILIES[family].detect(artifact, artifact_root=artifact_root)


def adapt(family: str, artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    return _FAMILIES[family].adapt(artifact_set, artifact_root=artifact_root)
