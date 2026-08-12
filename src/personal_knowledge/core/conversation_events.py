"""Phase 62: loss-aware typed event / relation / provenance / fidelity contracts.

This is the deterministic core of the unified canonical event authority
(Phase 62 CONTEXT D-10..D-14). It owns cross-source semantic invariants only:

  - :class:`EventKind` — the locked set of semantic event kinds (D-10)
  - :class:`RelationKind` — first-class relations (D-12)
  - :class:`FidelityProfile` — explicit ``complete|partial|unknown|unavailable``
    fidelity dimensions that can never be reported as complete when lossy (D-13)
  - :class:`FieldDisposition` / :class:`FieldDispositionRecord` — explicit
    field mapping decisions (D-07); unmodeled fields are preserved by reference,
    never silently dropped
  - :class:`Provenance` — every event/session resolves to an immutable source
    artifact and a native locator (D-05/D-06)
  - :class:`TypedEvent` / :class:`EventRelation` / :class:`AdaptedSession` —
    validated frozen records; events without artifact/native locator are
    rejected by construction (D-04)
  - :func:`make_event_id` — stable identity that prefers native identity and
    always includes family/artifact/contract-version collision domains;
    order/ordinal fields are never part of identity (D-11)

Deterministic local types only: no I/O, no network, no provider calls (D-31).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Mapping


class EventContractError(ValueError):
    """A typed conversation record violates the loss-aware contract."""


class EventKind(str, Enum):
    """Locked semantic event kinds (Phase 62 D-10)."""

    SESSION_LIFECYCLE = "session_lifecycle"
    USER_MESSAGE = "user_message"
    ASSISTANT_MESSAGE = "assistant_message"
    DEVELOPER_MESSAGE = "developer_message"
    SYSTEM_MESSAGE = "system_message"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    USAGE = "usage"
    COMPACTION_SUMMARY = "compaction_summary"
    TURN_BOUNDARY = "turn_boundary"
    LOOP_BOUNDARY = "loop_boundary"
    SUBAGENT_BOUNDARY = "subagent_boundary"
    FILE_CONTEXT = "file_context"
    UNKNOWN_NATIVE = "unknown_native"


class RelationKind(str, Enum):
    """First-class relation kinds between events (Phase 62 D-12)."""

    PARENT_CHILD = "parent_child"
    CALL_RESULT = "call_result"
    BRANCH = "branch"
    SIDECHAIN = "sidechain"
    SUBAGENT = "subagent"
    COMPACTED_RANGE = "compacted_range"
    RETAINED_FROM = "retained_from"
    TURN_MEMBERSHIP = "turn_membership"
    SOURCE_SESSION_CROSSWALK = "source_session_crosswalk"


class FidelityDimension(str, Enum):
    """Fidelity dimensions every session/event exposes (Phase 62 D-13)."""

    SOURCE_AVAILABILITY = "source_availability"
    STRUCTURE_COMPLETENESS = "structure_completeness"
    ORDERING_CONFIDENCE = "ordering_confidence"
    RELATION_COMPLETENESS = "relation_completeness"
    CONTENT_AVAILABILITY = "content_availability"
    COMPACTION_VISIBILITY = "compaction_visibility"
    NATIVE_ID_STABILITY = "native_id_stability"


class FidelityLevel(str, Enum):
    """Valid fidelity states. ``partial/unknown/unavailable`` are never complete."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"
    UNAVAILABLE = "unavailable"


class FieldDisposition(str, Enum):
    """Explicit decision for every native field (Phase 62 D-07)."""

    MAPPED = "mapped"
    PRESERVED_BY_REFERENCE = "preserved_by_reference"
    REDACTED = "redacted"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class FieldDispositionRecord:
    """One native field's mapping decision. Unmodeled fields stay explicit."""

    field_name: str
    disposition: FieldDisposition
    reason: str = ""


@dataclass(frozen=True)
class FidelityProfile:
    """Per-dimension fidelity for a session or event.

    ``is_complete()`` is True only when every dimension is ``complete``;
    a profile that contains ``partial/unknown/unavailable`` can never be
    presented as complete (D-13).
    """

    dimensions: tuple[FidelityDimension, ...]
    levels: tuple[FidelityLevel, ...]

    def __post_init__(self) -> None:
        if len(self.dimensions) != len(self.levels):
            raise EventContractError(
                "fidelity dimensions and levels must be parallel"
            )
        for dim, level in zip(self.dimensions, self.levels):
            if not isinstance(dim, FidelityDimension):
                raise EventContractError(f"invalid fidelity dimension: {dim!r}")
            if not isinstance(level, FidelityLevel):
                raise EventContractError(f"invalid fidelity level: {level!r}")

    @classmethod
    def complete(cls) -> "FidelityProfile":
        """A profile where every canonical dimension is ``complete``."""
        dims = tuple(FidelityDimension)
        return cls(dims, tuple([FidelityLevel.COMPLETE] * len(dims)))

    @classmethod
    def from_levels(
        cls, levels: Mapping[FidelityDimension, FidelityLevel]
    ) -> "FidelityProfile":
        """Build a profile over the full canonical dimension set.

        Dimensions not supplied default to ``unknown`` so absence is explicit
        instead of silently being treated as complete.
        """
        dims = tuple(FidelityDimension)
        return cls(
            dims,
            tuple(levels.get(d, FidelityLevel.UNKNOWN) for d in dims),
        )

    def level(self, dim: FidelityDimension) -> FidelityLevel:
        index = self.dimensions.index(dim)
        return self.levels[index]

    def is_complete(self) -> bool:
        return all(l is FidelityLevel.COMPLETE for l in self.levels)

    def has_loss(self) -> bool:
        return any(l is not FidelityLevel.COMPLETE for l in self.levels)

    def to_dict(self) -> dict:
        return {d.value: l.value for d, l in zip(self.dimensions, self.levels)}

    @classmethod
    def from_dict(cls, data: Mapping[str, str]) -> "FidelityProfile":
        levels = {
            FidelityDimension(k): FidelityLevel(v) for k, v in data.items()
        }
        return cls.from_levels(levels)


@dataclass(frozen=True)
class Provenance:
    """Stable provenance of an event/session to an immutable source artifact.

    ``artifact_id`` (content-addressed artifact) plus ``native_locator`` make a
    record resolvable back to raw evidence (D-05/D-06).
    """

    artifact_id: str
    artifact_hash: str
    native_locator: str
    native_session_id: str | None = None
    native_event_id: str | None = None
    contract_version: str = "1"

    def resolvable(self) -> bool:
        return bool(self.artifact_id) and bool(self.native_locator)


def make_event_id(
    family: str,
    artifact_id: str,
    contract_version: str,
    native_event_id: str | None,
    *,
    kind: EventKind | None = None,
    session_id: str | None = None,
    native_locator: str | None = None,
) -> str:
    """Derive a stable event identity (Phase 62 D-11).

    Prefers the native event identity when available; the family, artifact and
    contract version always participate as collision domains. When no native
    identity exists, a stable non-ordinal locator/session anchor is required.
    Ordinal/ordering fields are never part of the identity.
    """
    if not family or not artifact_id or not contract_version:
        raise EventContractError(
            "event id requires family, artifact and contract version domains"
        )
    if native_event_id:
        identity = f"{family}|{contract_version}|{artifact_id}|{native_event_id}"
    else:
        if not native_locator and not session_id:
            raise EventContractError(
                "cannot derive a stable event id without native identity or "
                "a stable non-ordinal locator/session anchor"
            )
        parts = [family, contract_version, artifact_id]
        if kind is not None:
            parts.append(kind.value)
        if session_id:
            parts.append(session_id)
        if native_locator:
            parts.append(native_locator)
        identity = "|".join(parts)
    return hashlib.sha256(f"ev|{identity}".encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TypedEvent:
    """A semantic event with explicit provenance, fidelity and dispositions.

    Rejects by construction any event that cannot be resolved to an immutable
    source artifact and native locator (D-04: fail closed, never a
    complete-looking unprovenanced record).
    """

    event_id: str
    session_id: str
    kind: EventKind
    provenance: Provenance
    fidelity: FidelityProfile
    field_dispositions: tuple[FieldDispositionRecord, ...] = ()
    occurred_at: str | None = None
    ordinal: int | None = None
    native_payload_ref: str | None = None
    summary: str | None = None

    def __post_init__(self) -> None:
        if not self.event_id or not self.session_id:
            raise EventContractError("event requires an id and a session id")
        if not isinstance(self.kind, EventKind):
            raise EventContractError(f"invalid event kind: {self.kind!r}")
        if not self.provenance.resolvable():
            raise EventContractError(
                "event without an immutable artifact/native locator is "
                "unprovenanced and cannot be represented"
            )
        if not isinstance(self.fidelity, FidelityProfile):
            raise EventContractError("event requires a fidelity profile")


@dataclass(frozen=True)
class EventRelation:
    """A first-class relation between two events (D-12).

    Endpoints are validated: both non-empty, distinct, and the kind is typed.
    """

    relation_id: str
    source_event_id: str
    target_event_id: str
    relation_kind: RelationKind

    def __post_init__(self) -> None:
        if not self.relation_id:
            raise EventContractError("relation requires an id")
        if not self.source_event_id or not self.target_event_id:
            raise EventContractError(
                "relation endpoints must not be empty"
            )
        if self.source_event_id == self.target_event_id:
            raise EventContractError("self-loop relations are invalid")
        if not isinstance(self.relation_kind, RelationKind):
            raise EventContractError(
                f"invalid relation kind: {self.relation_kind!r}"
            )


@dataclass(frozen=True)
class AdaptedSession:
    """A session produced by a family adapter, with its own fidelity/provenance."""

    session_id: str
    provenance: Provenance
    fidelity: FidelityProfile
    native_session_id: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    field_dispositions: tuple[FieldDispositionRecord, ...] = ()

    def __post_init__(self) -> None:
        if not self.session_id:
            raise EventContractError("session requires an id")
        if not self.provenance.resolvable():
            raise EventContractError(
                "session without an immutable artifact/native locator is "
                "unprovenanced"
            )
        if not isinstance(self.fidelity, FidelityProfile):
            raise EventContractError("session requires a fidelity profile")


def dataset_digest(
    *,
    family: str,
    adapter_version: str,
    contract_version: str,
    artifacts,
    sessions,
    events,
    relations,
) -> str:
    """Deterministic digest over the full adapted dataset.

    Used as the replay/integrity anchor for a generation and as
    ``AdaptationResult.dataset_digest``. Stable for identical inputs regardless
    of insertion order (everything is sorted before hashing).
    """
    parts = [
        family,
        adapter_version,
        contract_version,
        "|".join(sorted(a.artifact_id for a in artifacts)),
        "|".join(sorted(s.session_id for s in sessions)),
        "|".join(sorted(e.event_id for e in events)),
        "|".join(sorted(r.relation_id for r in relations)),
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
