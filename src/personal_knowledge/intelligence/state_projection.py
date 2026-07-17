"""Pure normalization and projection for snapshot-bound personal state.

This module accepts already-extracted, evidence-backed metadata.  It performs no
network access and never writes source, knowledge, lifecycle, or serving state.
"""
from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Iterable, Mapping

from .schema import (
    ASSERTION_KINDS,
    PRIVACY_CLASSES,
    PROVENANCE_CLASSES,
    EvidenceReference,
    SnapshotBinding,
    StateAssertion,
    canonical_json,
    checksum,
)


NORMALIZABLE_KINDS = frozenset({"goal", "constraint", "observation"})
DERIVATION_PROVENANCE = {
    "canonical_fact": "fact",
    "occurrence": "observation",
    "synthesis": "inference",
}
_FORBIDDEN_PAYLOAD_KEYS = frozenset(
    {"content", "body", "raw_text", "evidence_quote", "prompt", "response_text"}
)
_SECRET_RE = re.compile(
    r"(?i)(?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*[^\s${][^\s]*"
)


class ProjectionError(ValueError):
    """Stable fail-closed error for normalization/projection contracts."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _required(record: Mapping[str, Any], field: str) -> Any:
    if field not in record or record[field] is None or record[field] == "":
        raise ProjectionError("missing_field", field)
    return record[field]


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ProjectionError("invalid_time", field) from exc
    if parsed.tzinfo is None:
        raise ProjectionError("invalid_time", f"{field}:timezone_required")
    return parsed


def _reject_private_payload(value: Any, path: str = "candidate") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            label = str(key)
            if label.lower() in _FORBIDDEN_PAYLOAD_KEYS:
                raise ProjectionError("private_payload", f"{path}.{label}")
            _reject_private_payload(item, f"{path}.{label}")
    elif isinstance(value, (tuple, list)):
        for index, item in enumerate(value):
            _reject_private_payload(item, f"{path}[{index}]")
    elif isinstance(value, str) and _SECRET_RE.search(value):
        raise ProjectionError("secret_payload", path)


def _normalize_evidence(
    rows: Any,
    *,
    snapshot: SnapshotBinding,
) -> tuple[EvidenceReference, ...]:
    if not isinstance(rows, (tuple, list)) or not rows:
        raise ProjectionError("evidence_required")
    evidence: list[EvidenceReference] = []
    for index, raw in enumerate(rows):
        if not isinstance(raw, Mapping):
            raise ProjectionError("invalid_evidence", str(index))
        if str(_required(raw, "snapshot_id")) != snapshot.snapshot_id or str(
            _required(raw, "snapshot_hash")
        ) != snapshot.snapshot_hash:
            raise ProjectionError("mixed_snapshot", str(index))
        role = str(_required(raw, "serving_role"))
        version_id = str(_required(raw, "artifact_version_id"))
        member = snapshot.members.get(role)
        if member is None or str(member.get("artifact_version_id") or "") != version_id:
            raise ProjectionError("evidence_version_mismatch", str(index))
        privacy = str(_required(raw, "privacy_class"))
        if privacy not in PRIVACY_CLASSES or privacy != str(
            member.get("privacy_class") or ""
        ):
            raise ProjectionError("evidence_privacy_mismatch", str(index))
        evidence.append(
            EvidenceReference(
                ref=str(_required(raw, "ref")),
                artifact_type=str(_required(raw, "artifact_type")),
                serving_role=role,
                artifact_version_id=version_id,
                checksum=str(raw.get("checksum") or ""),
                privacy_class=privacy,
            )
        )
    ordered = tuple(
        sorted(
            evidence,
            key=lambda item: (
                item.artifact_type,
                item.ref,
                item.serving_role,
                item.artifact_version_id,
            ),
        )
    )
    keys = {(row.artifact_type, row.ref) for row in ordered}
    if len(keys) != len(ordered):
        raise ProjectionError("duplicate_evidence")
    return ordered


def normalize_candidates(
    candidates: Iterable[Mapping[str, Any]],
    *,
    snapshot: SnapshotBinding,
) -> tuple[StateAssertion, ...]:
    """Normalize extracted candidates into deterministic typed assertions."""
    normalized: list[StateAssertion] = []
    for ordinal, raw in enumerate(candidates):
        if not isinstance(raw, Mapping):
            raise ProjectionError("invalid_candidate", str(ordinal))
        _reject_private_payload(raw, f"candidate[{ordinal}]")
        if str(_required(raw, "snapshot_id")) != snapshot.snapshot_id or str(
            _required(raw, "snapshot_hash")
        ) != snapshot.snapshot_hash:
            raise ProjectionError("mixed_snapshot", str(ordinal))
        assertion_kind = str(_required(raw, "assertion_kind"))
        if assertion_kind not in NORMALIZABLE_KINDS or assertion_kind not in ASSERTION_KINDS:
            raise ProjectionError("invalid_assertion_kind", assertion_kind)
        provenance = str(_required(raw, "provenance_class"))
        if provenance not in PROVENANCE_CLASSES:
            raise ProjectionError("invalid_provenance_class", provenance)
        derivation = str(_required(raw, "derivation"))
        expected = DERIVATION_PROVENANCE.get(derivation)
        if expected is None:
            raise ProjectionError("invalid_derivation", derivation)
        if provenance != expected:
            raise ProjectionError(
                "provenance_rule_violation", f"{derivation}:{provenance}"
            )
        if assertion_kind == "observation" and provenance == "fact":
            raise ProjectionError("observation_as_fact")

        valid_from = str(_required(raw, "valid_from"))
        observed_at = str(_required(raw, "observed_at"))
        valid_from_dt = _parse_time(valid_from, "valid_from")
        _parse_time(observed_at, "observed_at")
        valid_to = str(raw["valid_to"]) if raw.get("valid_to") else None
        if valid_to and _parse_time(valid_to, "valid_to") < valid_from_dt:
            raise ProjectionError("invalid_time_interval")
        confidence = float(_required(raw, "confidence"))
        if not 0.0 <= confidence <= 1.0:
            raise ProjectionError("invalid_confidence", str(confidence))
        uncertainty = str(_required(raw, "uncertainty_reason")).strip()
        if not uncertainty:
            raise ProjectionError("missing_field", "uncertainty_reason")
        values = {
            field: str(_required(raw, field)).strip()
            for field in ("subject", "domain", "scope", "predicate")
        }
        if any(not value for value in values.values()):
            raise ProjectionError("missing_identity_field")
        normalized.append(
            StateAssertion(
                assertion_kind=assertion_kind,
                provenance_class=provenance,
                subject=values["subject"],
                domain=values["domain"],
                scope=values["scope"],
                predicate=values["predicate"],
                value=_required(raw, "value"),
                valid_from=valid_from,
                valid_to=valid_to,
                observed_at=observed_at,
                confidence=confidence,
                uncertainty=uncertainty,
                lifecycle=str(raw.get("lifecycle") or "current"),
                evidence=_normalize_evidence(raw.get("evidence"), snapshot=snapshot),
            )
        )
    ordered = tuple(sorted(normalized, key=lambda item: checksum(item)))
    if not ordered:
        raise ProjectionError("candidates_required")
    if len({canonical_json(item) for item in ordered}) != len(ordered):
        raise ProjectionError("duplicate_candidate")
    return ordered

