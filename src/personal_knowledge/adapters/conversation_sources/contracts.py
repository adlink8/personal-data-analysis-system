"""Phase 62: family adapter capability / probe / result public seam.

One explicit contract per agent family (D-02). A family adapter consumes an
immutable :class:`SourceArtifactSet` plus a versioned :class:`CapabilityDescriptor`
and produces an :class:`AdaptationResult` containing sessions, typed events,
first-class relations, fidelity, field dispositions, warnings and a
deterministic dataset digest.

The capture seam (:mod:`.snapshots`) produces :class:`SourceArtifact` objects;
family parsers (later plans) are the only producers of :class:`AdaptationResult`.
This module never parses native formats and never publishes data.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping

from personal_knowledge.core.conversation_events import (
    AdaptedSession,
    dataset_digest,
    EventContractError,
    EventKind,
    EventRelation,
    FieldDispositionRecord,
    FidelityDimension,
    FidelityProfile,
    Provenance,
    RelationKind,
    TypedEvent,
)


@dataclass(frozen=True)
class SourceArtifact:
    """A content-addressed immutable source artifact (Phase 62 D-05/D-09).

    ``artifact_id`` is content-addressed; ``content_hash`` is the byte hash.
    ``schema_digest``/``privacy_dispositions`` are metadata-only — never bodies
    or credentials.
    """

    artifact_id: str
    family: str
    source_kind: str  # 'file' | 'directory' | 'sqlite'
    content_hash: str
    capture_method: str
    relative_path: str
    byte_size: int
    schema_digest: str | None = None
    privacy_dispositions: tuple[str, ...] = ()


@dataclass(frozen=True)
class SourceArtifactSet:
    """Immutable set of source artifacts handed to a family adapter."""

    artifacts: tuple[SourceArtifact, ...] = ()

    def digest(self) -> str:
        """Deterministic digest over the artifact set (stable under ordering)."""
        payload = "|".join(
            a.artifact_id for a in sorted(self.artifacts, key=lambda a: a.artifact_id)
        )
        return hashlib.sha256(f"artifacts|{payload}".encode("utf-8")).hexdigest()

    def by_id(self) -> dict[str, SourceArtifact]:
        return {a.artifact_id: a for a in self.artifacts}


@dataclass(frozen=True)
class CapabilityDescriptor:
    """Versioned capability contract of one family adapter (D-02).

    ``digest()`` is stable for identical capabilities and changes when the
    adapter or contract version changes, enabling schema/version gates.
    """

    family: str
    adapter_version: str
    contract_version: str
    supported_event_kinds: tuple[EventKind, ...] = ()
    supported_relation_kinds: tuple[RelationKind, ...] = ()
    fidelity_dimensions: tuple[FidelityDimension, ...] = ()
    capabilities: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.family:
            raise EventContractError("capability requires a family")
        if not self.adapter_version or not self.contract_version:
            raise EventContractError(
                "capability requires adapter and contract versions"
            )

    def digest(self) -> str:
        payload = {
            "family": self.family,
            "adapter_version": self.adapter_version,
            "contract_version": self.contract_version,
            "event_kinds": sorted(k.value for k in self.supported_event_kinds),
            "relation_kinds": sorted(k.value for k in self.supported_relation_kinds),
            "fidelity_dimensions": sorted(
                d.value for d in self.fidelity_dimensions
            ),
            "capabilities": dict(sorted(self.capabilities.items())),
        }
        return hashlib.sha256(
            f"cap|{payload}".encode("utf-8")
        ).hexdigest()


@dataclass(frozen=True)
class AdaptationResult:
    """The full output of one family adaptation run.

    Validation (constructor): every event must carry resolvable provenance and
    every relation endpoint must reference a known event in the same result —
    a complete-looking but unprovenanced/lossy record cannot be emitted (D-04).

    ``dataset_digest`` is a deterministic property recomputed from the contents,
    so replay of identical input always yields the same digest.
    """

    family: str
    adapter_version: str
    contract_version: str
    artifacts: tuple[SourceArtifact, ...]
    events: tuple[TypedEvent, ...]
    fidelity: FidelityProfile
    sessions: tuple[AdaptedSession, ...] = ()
    relations: tuple[EventRelation, ...] = ()
    field_dispositions: tuple[FieldDispositionRecord, ...] = ()
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.family or not self.adapter_version or not self.contract_version:
            raise EventContractError(
                "adaptation result requires family, adapter and contract versions"
            )
        for event in self.events:
            if not event.provenance.resolvable():
                raise EventContractError(
                    f"event {event.event_id} is unprovenanced (no artifact/native locator)"
                )
        known = {e.event_id for e in self.events}
        for relation in self.relations:
            if (
                relation.source_event_id not in known
                or relation.target_event_id not in known
            ):
                raise EventContractError(
                    f"relation {relation.relation_id} references an event "
                    "outside this adaptation result"
                )
        if not isinstance(self.fidelity, FidelityProfile):
            raise EventContractError("adaptation result requires a fidelity profile")

    @property
    def dataset_digest(self) -> str:
        return dataset_digest(
            family=self.family,
            adapter_version=self.adapter_version,
            contract_version=self.contract_version,
            artifacts=self.artifacts,
            sessions=self.sessions,
            events=self.events,
            relations=self.relations,
        )


__all__ = [
    "AdaptationResult",
    "CapabilityDescriptor",
    "SourceArtifact",
    "SourceArtifactSet",
]
