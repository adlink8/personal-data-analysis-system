"""Phase 62-02: Workbuddy / Kimi / Kimi-work JSONL adapters.

Workbuddy exports message/reasoning/function_call/function_call_result
records; reasoning and call/result survive as separate linked typed events.
Kimi/Kimi-work use a loop protocol with turn prompt, context append and
loop/task lifecycle records — loop and task boundaries become first-class
episode hints (``loop_boundary`` / ``turn_boundary``) rather than prose.
Each family keeps its own detector, capability contract and fidelity
outcomes; unknown kinds stay ``unknown_native``.
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

# Workbuddy record kind -> typed event kind.
_WORKBUDDY_KINDS = {
    "message": None,  # decided by role
    "reasoning": EventKind.REASONING,
    "function_call": EventKind.TOOL_CALL,
    "function_call_result": EventKind.TOOL_RESULT,
}


def _fidelity(**overrides) -> FidelityProfile:
    levels = dict(_COMPLETE)
    for key, value in overrides.items():
        levels[FidelityDimension[key]] = value
    return FidelityProfile.from_levels(levels)


class _Family:
    """Shared JSONL adapter machinery for one family of this module."""

    def __init__(self, family: str, *, markers: tuple[str, ...], kinds: dict | None):
        self.family = family
        self.markers = markers
        self.kinds = kinds or {}

    def capability(self) -> CapabilityDescriptor:
        kinds = {k for k in (self.kinds.values() if self.kinds else ()) if k is not None}
        if self.family == "workbuddy":
            kinds |= {EventKind.USER_MESSAGE, EventKind.ASSISTANT_MESSAGE,
                      EventKind.REASONING, EventKind.TOOL_CALL, EventKind.TOOL_RESULT}
            relations = {RelationKind.CALL_RESULT}
        else:  # kimi / kimi-work
            kinds |= {EventKind.TURN_BOUNDARY, EventKind.LOOP_BOUNDARY,
                      EventKind.FILE_CONTEXT, EventKind.USER_MESSAGE,
                      EventKind.ASSISTANT_MESSAGE}
            relations = set()
        kinds.add(EventKind.SESSION_LIFECYCLE)
        kinds.add(EventKind.UNKNOWN_NATIVE)
        return CapabilityDescriptor(
            family=self.family, adapter_version=ADAPTER_VERSION,
            contract_version=CONTRACT_VERSION,
            supported_event_kinds=tuple(sorted(kinds, key=lambda k: k.value)),
            supported_relation_kinds=tuple(sorted(relations, key=lambda r: r.value)),
            fidelity_dimensions=tuple(FidelityDimension),
            capabilities={
                "native_shape": "jsonl_event_stream",
                "lifecycle": "loop_and_task_boundaries" if self.family != "workbuddy" else "call_result_pairing",
            },
        )

    def detect(self, artifact: SourceArtifact, *, artifact_root: Path) -> bool:
        if not (artifact.relative_path or "").lower().endswith(".jsonl"):
            return False
        try:
            with (artifact_root / artifact.artifact_id).open("r", encoding="utf-8") as h:
                for raw in h:
                    line = raw.strip()
                    if line and any(m in line for m in self.markers):
                        return True
        except OSError:
            return False
        return False

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

    def _record_kind(self, record: dict) -> EventKind | None:
        if self.family == "workbuddy":
            rtype = record.get("type")
            if rtype == "message":
                return EventKind.USER_MESSAGE if record.get("role") == "user" else (
                    EventKind.ASSISTANT_MESSAGE if record.get("role") == "assistant" else None)
            return _WORKBUDDY_KINDS.get(rtype)
        rtype = record.get("type")
        return {
            "turn_start": EventKind.TURN_BOUNDARY,
            "user_prompt": EventKind.USER_MESSAGE,
            "assistant_message": EventKind.ASSISTANT_MESSAGE,
            "loop_iteration": EventKind.LOOP_BOUNDARY,
            "context_append": EventKind.FILE_CONTEXT,
            "task_complete": EventKind.TURN_BOUNDARY,
        }.get(rtype)

    def _adapt_record(self, record: dict, artifact, *, session_id, locator) -> TypedEvent | None:
        kind = self._record_kind(record)
        ts = record.get("timestamp")
        sid = record.get("session_id")
        mid = record.get("message_id") or record.get("task_id")
        if kind is None:
            return self._event(artifact, session_id=session_id, kind=EventKind.UNKNOWN_NATIVE,
                               locator=locator, native_id=mid, occurred_at=ts,
                               fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL,
                                                  RELATION_COMPLETENESS=FidelityLevel.UNKNOWN,
                                                  CONTENT_AVAILABILITY=FidelityLevel.PARTIAL),
                               native_session=sid)
        summary = str(record.get("content") or record.get("result") or "")[:2048] or None
        return self._event(artifact, session_id=session_id, kind=kind, locator=locator,
                           native_id=mid, occurred_at=ts, summary=summary, native_session=sid)

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
        by_call_id: dict[str, tuple[TypedEvent | None, TypedEvent | None]] = {}
        native_session = next((r.get("session_id") for r in records if r.get("session_id")), None)

        for lineno, record in enumerate(records, start=1):
            ev = self._adapt_record(record, artifact, session_id=session_id,
                                    locator=f"{artifact.relative_path}#L{lineno}")
            if ev is None:
                continue
            events.append(ev)
            if self.family == "workbuddy":
                call_id = record.get("call_id")
                if call_id:
                    start, _end = by_call_id.setdefault(call_id, (None, None))
                    if ev.kind is EventKind.TOOL_CALL:
                        by_call_id[call_id] = (ev, _end)
                    elif ev.kind is EventKind.TOOL_RESULT:
                        by_call_id[call_id] = (start, ev)

        if self.family == "workbuddy":
            for call_id, (start, end) in by_call_id.items():
                if start is None or end is None:
                    warnings.append(f"call {call_id!r} missing start/result (partial)")
                    continue
                relations.append(EventRelation(
                    relation_id=make_event_id(self.family, artifact.artifact_id, CONTRACT_VERSION,
                                              f"rel-call:{call_id}"),
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

        return AdaptationResult(
            family=self.family, adapter_version=ADAPTER_VERSION, contract_version=CONTRACT_VERSION,
            artifacts=(artifact,), events=tuple(events),
            fidelity=_fidelity(STRUCTURE_COMPLETENESS=FidelityLevel.PARTIAL if unknown else FidelityLevel.COMPLETE),
            sessions=tuple(sessions), relations=tuple(relations), warnings=tuple(warnings),
        )


_FAMILIES = {
    "workbuddy": _Family("workbuddy", markers=("function_call_result",), kinds=_WORKBUDDY_KINDS),
    "kimi": _Family("kimi", markers=("loop_iteration", "context_append", "task_complete"), kinds=None),
    "kimi-work": _Family("kimi-work", markers=("loop_iteration", "context_append", "task_complete"), kinds=None),
}


def capability(family: str) -> CapabilityDescriptor:
    return _FAMILIES[family].capability()


def detect(family: str, artifact: SourceArtifact, *, artifact_root: Path) -> bool:
    return _FAMILIES[family].detect(artifact, artifact_root=artifact_root)


def adapt(family: str, artifact_set: SourceArtifactSet, *, artifact_root: Path) -> AdaptationResult:
    return _FAMILIES[family].adapt(artifact_set, artifact_root=artifact_root)
