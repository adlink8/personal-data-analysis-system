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

from dataclasses import replace
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
    FieldDisposition,
    FieldDispositionRecord,
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
        subtype = record.get("subtype")
        if subtype == "turn_duration":
            return EventKind.USAGE
        if subtype == "compact_boundary":
            return EventKind.COMPACTION_SUMMARY
        if subtype == "api_error":
            return None
        return EventKind.SYSTEM_MESSAGE
    return None


def _text_content(record: dict) -> str | None:
    """Text from content blocks; tool blocks are not treated as prose."""
    message = record.get("message") if isinstance(record.get("message"), dict) else {}
    blocks = record.get("content", message.get("content"))
    if isinstance(blocks, str):
        return blocks
    if isinstance(blocks, list):
        parts: list[str] = []
        saw_text = False
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            saw_text = True
            raw = block.get("text")
            parts.append("" if raw is None else str(raw))
        return " ".join(parts) if saw_text else None
    return None


def _content_blocks(record: dict):
    message = record.get("message")
    if isinstance(message, dict) and "content" in message:
        return message.get("content")
    return record.get("content")


def _nested_text(value) -> str | None:
    """Recover text from a tool/reasoning block without inventing content."""

    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        saw_text = False
        for item in value:
            if isinstance(item, str):
                saw_text = True
                parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                saw_text = True
                raw = item.get("text")
                parts.append("" if raw is None else str(raw))
        return " ".join(parts) if saw_text else None
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
            EventKind.REASONING,
            EventKind.TOOL_CALL, EventKind.TOOL_RESULT,
            EventKind.USAGE,
            EventKind.COMPACTION_SUMMARY, EventKind.UNKNOWN_NATIVE,
        }
        relations = {
            RelationKind.PARENT_CHILD, RelationKind.SIDECHAIN,
            RelationKind.CALL_RESULT,
        }
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
               occurred_at=None, content=None, summary=None, fidelity=None,
               native_session=None, ordinal=None, native_payload_ref=None,
               field_dispositions=()) -> TypedEvent:
        return TypedEvent(
            event_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                   native_id or locator, kind=kind, session_id=session_id,
                                   native_locator=locator),
            session_id=session_id, kind=kind,
            provenance=Provenance(
                artifact_id=artifact.artifact_id, artifact_hash=artifact.content_hash,
                native_locator=locator, native_session_id=native_session or None,
                native_event_id=native_id, contract_version=CONTRACT_VERSION,
            ),
            fidelity=fidelity or _fidelity(), occurred_at=occurred_at,
            ordinal=ordinal, native_payload_ref=native_payload_ref,
            content=content, summary=summary,
            field_dispositions=tuple(field_dispositions),
        )

    def _adapt_record(
        self, record: dict, artifact, *, session_id, locator, ordinal_start: int,
    ) -> tuple[list[TypedEvent], list[tuple[str, str, TypedEvent]]]:
        """Map one envelope, expanding each native content block separately."""

        kind = _record_kind(record)
        ts = record.get("timestamp")
        sid = record.get("session_id") or record.get("sessionId")
        if kind is None:
            dispositions = ()
            if record.get("type") in ("system", "system_message"):
                dispositions = (FieldDispositionRecord(
                    "error", FieldDisposition.PRESERVED_BY_REFERENCE,
                    "non-text system error envelope preserved by native locator",
                ),)
            return [self._event(
                artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                locator=locator, native_id=record.get("uuid"), occurred_at=ts,
                ordinal=ordinal_start,
                fidelity=_fidelity(
                    STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                    RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                    CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                ),
                native_session=sid, native_payload_ref=locator,
                field_dispositions=dispositions,
            )], []
        is_message = kind in {
            EventKind.USER_MESSAGE,
            EventKind.ASSISTANT_MESSAGE,
            EventKind.SYSTEM_MESSAGE,
        }
        if not is_message:
            text = _text_content(record)
            return [self._event(
                artifact, session_id=session_id, kind=kind, locator=locator,
                native_id=record.get("uuid"), occurred_at=ts,
                ordinal=ordinal_start,
                content=None, summary=text, native_session=sid,
                native_payload_ref=locator,
            )], []

        blocks = _content_blocks(record)
        if isinstance(blocks, str) or blocks is None:
            content = blocks if isinstance(blocks, str) else None
            fidelity = (
                _fidelity()
                if blocks is not None
                else _fidelity(CONTENT_AVAILABILITY=FidelityLevel.UNAVAILABLE)
            )
            dispositions = () if blocks is not None else (
                FieldDispositionRecord(
                    "content", FieldDisposition.UNAVAILABLE,
                    "message envelope has no native content field",
                ),
            )
            return [self._event(
                artifact, session_id=session_id, kind=kind, locator=locator,
                native_id=record.get("uuid"), occurred_at=ts,
                ordinal=ordinal_start, content=content, native_session=sid,
                fidelity=fidelity, field_dispositions=dispositions,
            )], []

        if not isinstance(blocks, list):
            blocks = [blocks]
        if not blocks:
            return [self._event(
                artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                locator=f"{locator}/content", native_id=record.get("uuid"),
                occurred_at=ts, ordinal=ordinal_start, native_session=sid,
                native_payload_ref=f"{locator}/content",
                fidelity=_fidelity(
                    STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                    CONTENT_AVAILABILITY=FidelityLevel.UNAVAILABLE,
                ),
                field_dispositions=(FieldDispositionRecord(
                    "content", FieldDisposition.PRESERVED_BY_REFERENCE,
                    "empty non-text message envelope preserved by locator",
                ),),
            )], []

        events: list[TypedEvent] = []
        call_links: list[tuple[str, str, TypedEvent]] = []
        envelope_id = record.get("uuid")
        for block_index, block in enumerate(blocks):
            block_locator = f"{locator}/content/{block_index}"
            block_native_id = (
                f"{envelope_id}:content:{block_index}" if envelope_id else None
            )
            block_type = block.get("type") if isinstance(block, dict) else None
            block_kind = EventKind.UNKNOWN_NATIVE
            block_content = None
            block_summary = None
            block_fidelity = _fidelity()
            dispositions: tuple[FieldDispositionRecord, ...] = ()
            call_link: tuple[str, str] | None = None

            if block_type == "text":
                block_kind = kind
                raw = block.get("text")
                block_content = None if raw is None else str(raw)
                dispositions = (FieldDispositionRecord(
                    f"content[{block_index}].text", FieldDisposition.MAPPED,
                    "mapped exactly to message content",
                ),)
            elif block_type in ("thinking", "reasoning"):
                block_kind = EventKind.REASONING
                raw = block.get("thinking", block.get("text"))
                text = None if raw is None else str(raw)
                block_summary = text[:2048] if text else None
            elif block_type == "tool_use":
                block_kind = EventKind.TOOL_CALL
                call_id = block.get("id")
                block_summary = str(block.get("name") or "tool_use")[:256]
                if call_id:
                    call_link = (str(call_id), "call")
                else:
                    block_fidelity = block_fidelity.with_at_least(
                        FidelityDimension.RELATION_COMPLETENESS,
                        FidelityLevel.PARTIAL,
                    )
                    dispositions = (FieldDispositionRecord(
                        "tool_call_id", FieldDisposition.UNAVAILABLE,
                        "native tool call block has no recoverable call id",
                    ),)
            elif block_type == "tool_result":
                block_kind = EventKind.TOOL_RESULT
                call_id = block.get("tool_use_id") or block.get("call_id")
                text = _nested_text(block.get("content"))
                block_summary = text[:2048] if text else None
                if call_id:
                    call_link = (str(call_id), "result")
                else:
                    block_fidelity = block_fidelity.with_at_least(
                        FidelityDimension.RELATION_COMPLETENESS,
                        FidelityLevel.PARTIAL,
                    )
                    dispositions = (FieldDispositionRecord(
                        "tool_call_id", FieldDisposition.UNAVAILABLE,
                        "native tool result block has no recoverable call id",
                    ),)
            else:
                block_fidelity = _fidelity(
                    STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                    CONTENT_AVAILABILITY=FidelityLevel.PARTIAL,
                )
                dispositions = (FieldDispositionRecord(
                    f"content[{block_index}]",
                    FieldDisposition.PRESERVED_BY_REFERENCE,
                    f"unsupported native content block type {block_type!r}",
                ),)

            event = self._event(
                artifact, session_id=session_id, kind=block_kind,
                locator=block_locator, native_id=block_native_id,
                occurred_at=ts, ordinal=ordinal_start + len(events),
                native_session=sid, native_payload_ref=block_locator,
                content=block_content, summary=block_summary,
                fidelity=block_fidelity, field_dispositions=dispositions,
            )
            events.append(event)
            if call_link is not None:
                call_links.append((call_link[0], call_link[1], event))
        return events, call_links

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
        by_call_id: dict[str, dict[str, list[TypedEvent]]] = {}
        native_session = next((
            r.get("session_id") or r.get("sessionId")
            for r in records if r.get("session_id") or r.get("sessionId")
        ), Path(artifact.relative_path).stem)

        for lineno, record in enumerate(records, start=1):
            record_events, call_links = self._adapt_record(
                record, artifact, session_id=session_id,
                locator=f"{artifact.relative_path}#L{lineno}",
                ordinal_start=len(events),
            )
            if not record_events:
                continue
            events.extend(record_events)
            for call_id, role, event in call_links:
                by_call_id.setdefault(
                    call_id, {"call": [], "result": []}
                )[role].append(event)
            uuid = record.get("uuid")
            if uuid:
                by_uuid[uuid] = record_events[0]
            parent = record.get("parentUuid")
            if parent:
                parent_links.extend(
                    (event, parent, bool(record.get("isSidechain")))
                    for event in record_events
                )

        missing_parent = False
        for child, parent_uuid, sidechain in parent_links:
            parent_ev = by_uuid.get(parent_uuid)
            if parent_ev is None:
                missing_parent = True
                warnings.append(f"uuid {parent_uuid!r} has no in-file parent (partial relation)")
                continue
            relations.append(EventRelation(
                relation_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                          f"rel-dag:{child.event_id}:{parent_ev.event_id}"),
                source_event_id=child.event_id, target_event_id=parent_ev.event_id,
                relation_kind=RelationKind.SIDECHAIN if sidechain else RelationKind.PARENT_CHILD,
            ))

        unmatched_tool_ids: set[str] = set()
        for call_id, endpoints in by_call_id.items():
            calls = endpoints["call"]
            results = endpoints["result"]
            for pair_index, (call, result) in enumerate(zip(calls, results)):
                relations.append(EventRelation(
                    relation_id=make_event_id(
                        self.family, artifact.artifact_id, CONTRACT_VERSION,
                        f"rel-call:{call_id}:{pair_index}",
                    ),
                    source_event_id=call.event_id,
                    target_event_id=result.event_id,
                    relation_kind=RelationKind.CALL_RESULT,
                ))
            unmatched = (*calls[len(results):], *results[len(calls):])
            if unmatched:
                unmatched_tool_ids.update(event.event_id for event in unmatched)
                warnings.append(
                    f"tool call id {call_id!r} has unmatched call/result block(s)"
                )

        if unmatched_tool_ids:
            marked: list[TypedEvent] = []
            for event in events:
                if event.event_id not in unmatched_tool_ids:
                    marked.append(event)
                    continue
                missing_field = (
                    "tool_result_relation"
                    if event.kind is EventKind.TOOL_CALL
                    else "tool_call_relation"
                )
                marked.append(replace(
                    event,
                    fidelity=event.fidelity.with_at_least(
                        FidelityDimension.RELATION_COMPLETENESS,
                        FidelityLevel.PARTIAL,
                    ),
                    field_dispositions=event.field_dispositions + (
                        FieldDispositionRecord(
                            missing_field, FieldDisposition.UNAVAILABLE,
                            "native call id has no matching block in this artifact",
                        ),
                    ),
                ))
            events = marked

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
                    if missing_parent or unmatched_tool_ids or any(
                        event.kind in {EventKind.TOOL_CALL, EventKind.TOOL_RESULT}
                        and event.fidelity.level(
                            FidelityDimension.RELATION_COMPLETENESS
                        ) is not FidelityLevel.COMPLETE
                        for event in events
                    )
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
