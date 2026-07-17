"""Typed immutable records for the non-serving decision-feedback authority."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from personal_knowledge.intelligence.schema import canonical_json, checksum


SCHEMA_VERSION = "decision_feedback_run_v1"
COGNITIVE_TYPES = frozenset(
    {"fact", "observation", "inference", "recommendation", "user_confirmation"}
)
REFERENCE_TYPES = frozenset({"fact", "observation", "inference"})
GENESIS_SENTINEL = "GENESIS"


class DecisionSchemaError(ValueError):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class CognitionReference:
    cognitive_type: str
    authority_id: str
    record_id: str
    source_run_id: str
    source_run_checksum: str
    source_publication_sequence: int
    snapshot_id: str
    snapshot_hash: str
    provenance_class: str
    evidence_status: str
    uncertainty: str
    record_checksum: str

    def __post_init__(self) -> None:
        if not self.cognitive_type:
            raise DecisionSchemaError("cognitive_type_required")
        if self.cognitive_type not in REFERENCE_TYPES:
            raise DecisionSchemaError("invalid_cognitive_reference", self.cognitive_type)
        if self.authority_id != "a.personal_change":
            raise DecisionSchemaError("invalid_reference_authority", self.authority_id)
        if self.provenance_class != self.cognitive_type:
            raise DecisionSchemaError(
                "cognitive_provenance_mismatch",
                f"{self.cognitive_type}:{self.provenance_class}",
            )
        if self.evidence_status != "eligible":
            raise DecisionSchemaError("support_ineligible", self.record_id)
        if self.source_publication_sequence < 1:
            raise DecisionSchemaError("invalid_publication_sequence")
        for field, value in (
            ("record_id", self.record_id),
            ("source_run_id", self.source_run_id),
            ("snapshot_id", self.snapshot_id),
            ("snapshot_hash", self.snapshot_hash),
        ):
            if not value:
                raise DecisionSchemaError("missing_reference_field", field)
        for field, value in (
            ("source_run_checksum", self.source_run_checksum),
            ("record_checksum", self.record_checksum),
        ):
            if len(value) != 64:
                raise DecisionSchemaError("invalid_checksum", field)


@dataclass(frozen=True)
class RecommendationDraft:
    subject: str
    domain: str
    scope: str
    recommendation_kind: str
    target: str
    horizon: str
    rationale_codes: tuple[str, ...]
    expected_benefit: str
    costs_constraints: tuple[str, ...]
    assumptions: tuple[str, ...]
    contraindications: tuple[str, ...]
    confidence: float
    uncertainty: str
    expires_at: str
    support: tuple[CognitionReference, ...]

    def __post_init__(self) -> None:
        for field, value in (
            ("subject", self.subject), ("domain", self.domain), ("scope", self.scope),
            ("recommendation_kind", self.recommendation_kind), ("target", self.target),
            ("horizon", self.horizon), ("expected_benefit", self.expected_benefit),
            ("expires_at", self.expires_at),
        ):
            if not value.strip():
                raise DecisionSchemaError("missing_recommendation_field", field)
        if not 0.0 <= self.confidence <= 1.0:
            raise DecisionSchemaError("invalid_confidence")
        if not self.support:
            raise DecisionSchemaError("support_required")


@dataclass(frozen=True)
class Recommendation:
    recommendation_id: str
    run_id: str
    source_run_id: str
    source_run_checksum: str
    snapshot_id: str
    snapshot_hash: str
    subject: str
    domain: str
    scope: str
    recommendation_kind: str
    target: str
    horizon: str
    rationale_codes: tuple[str, ...]
    expected_benefit: str
    costs_constraints: tuple[str, ...]
    assumptions: tuple[str, ...]
    contraindications: tuple[str, ...]
    confidence: float
    uncertainty: str
    expires_at: str
    support: tuple[CognitionReference, ...]
    payload: Mapping[str, Any]
    payload_checksum: str


@dataclass(frozen=True)
class RecommendationGenesis:
    event_id: str
    recommendation_id: str
    sequence: int
    event_type: str
    typed_record_id: str
    previous_event_checksum: str
    payload: Mapping[str, Any]
    payload_checksum: str


@dataclass(frozen=True)
class DecisionRun:
    run_id: str
    registry_id: str
    source_run_id: str
    source_run_checksum: str
    source_publication_sequence: int
    snapshot_id: str
    snapshot_hash: str
    policy_id: str
    policy_version: str
    input_manifest: Mapping[str, Any]
    input_manifest_checksum: str
    output_manifest: Mapping[str, Any]
    output_manifest_checksum: str
    run_checksum: str
    recommendations: tuple[Recommendation, ...]
    genesis_events: tuple[RecommendationGenesis, ...]


__all__ = [
    "COGNITIVE_TYPES", "GENESIS_SENTINEL", "REFERENCE_TYPES", "SCHEMA_VERSION",
    "CognitionReference", "DecisionRun", "DecisionSchemaError", "Recommendation",
    "RecommendationDraft", "RecommendationGenesis", "canonical_json", "checksum",
]
