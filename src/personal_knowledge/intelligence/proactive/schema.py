"""Frozen metadata-only records for proactive intelligence."""
from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
import hashlib
import json
from typing import Any, Mapping

CANONICAL_DOMAINS = ("learning", "career", "project", "health", "finance", "relationship", "time", "energy")
DOMAIN_ALIASES = {"study": "learning", "education": "learning", "work": "career", "job": "career", "projects": "project", "relationships": "relationship", "schedule": "time", "capacity": "energy"}
RELATION_TYPES = frozenset({"goal_support", "goal_conflict", "dependency", "resource_competition", "risk_propagation", "opportunity"})
RESOURCE_TYPES = frozenset({"time", "energy", "budget"})
FORBIDDEN_KEYS = frozenset({"content", "body", "raw_text", "note", "credential", "secret", "token", "password", "webhook", "command", "executable", "connector", "recipient", "send_target", "payment_detail"})


def canonical_domain(value: str, *, allow_unclassified: bool = False) -> str:
    normalized = value.strip().lower().replace("-", "_")
    normalized = DOMAIN_ALIASES.get(normalized, normalized)
    if normalized in CANONICAL_DOMAINS:
        return normalized
    if allow_unclassified and normalized == "unclassified":
        return normalized
    raise ValueError(f"unknown_domain:{value}")


def _json_value(value: Any) -> Any:
    if is_dataclass(value):
        return _json_value(asdict(value))
    if isinstance(value, Mapping):
        return {str(k): _json_value(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_json_value(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    raise TypeError(f"unsupported canonical value:{type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(_json_value(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def validate_metadata_payload(value: Any, path: str = "payload") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).strip().lower()
            if normalized in FORBIDDEN_KEYS or any(token in normalized for token in ("credential", "password", "webhook", "send_target")):
                raise ValueError(f"forbidden_payload:{path}.{key}")
            validate_metadata_payload(item, f"{path}.{key}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            validate_metadata_payload(item, f"{path}[{index}]")


@dataclass(frozen=True)
class SupportReference:
    authority_id: str
    record_type: str
    record_id: str
    record_checksum: str
    source_run_id: str
    source_run_checksum: str
    snapshot_id: str
    snapshot_hash: str


@dataclass(frozen=True)
class ResourceClaim:
    resource_type: str
    amount: float
    unit: str
    horizon_start: str
    horizon_end: str
    capacity: float
    source: SupportReference


@dataclass(frozen=True)
class CoordinationDraft:
    relation_type: str
    subject: str
    scope: str
    domains: tuple[str, ...]
    valid_from: str
    valid_to: str | None
    observed_at: str
    rule_id: str
    rule_version: str
    confidence: float
    uncertainty: str
    source_refs: tuple[SupportReference, ...]
    resource_manifest: tuple[ResourceClaim, ...]


@dataclass(frozen=True)
class CoordinationItem:
    coordination_id: str
    run_id: str
    draft: CoordinationDraft
    payload: Mapping[str, Any]
    payload_checksum: str


@dataclass(frozen=True)
class ProactiveRun:
    run_id: str
    registry_id: str
    source_run_id: str
    source_run_checksum: str
    source_publication_sequence: int
    decision_run_id: str | None
    decision_run_checksum: str | None
    decision_event_frontier_checksum: str
    snapshot_id: str
    snapshot_hash: str
    control_frontier_checksum: str
    coordination_policy: str
    ranking_policy: str
    noise_policy: str
    input_manifest: Mapping[str, Any]
    input_manifest_checksum: str
    output_manifest: Mapping[str, Any]
    output_manifest_checksum: str
    run_checksum: str
    coordination_items: tuple[CoordinationItem, ...]
