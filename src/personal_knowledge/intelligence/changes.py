"""Deterministic, metadata-only change intelligence over typed projections.

The functions in this module are pure.  They compare immutable projections and
emit checksums, assertion IDs and evidence references; source bodies never enter
the change manifest.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .schema import canonical_json, checksum
from .state_projection import FormationStep, ProjectedState, StateKey, StateProjection


CHANGE_ALGORITHM_VERSION = "personal_state_changes_v1"
BASE_CHANGE_RULE_ID = "typed_state_delta"
BASE_CHANGE_RULE_VERSION = "1"
BASE_CHANGE_TYPES = frozenset(
    {"created", "updated", "reaffirmed", "stale", "conflict", "resolved"}
)


class ChangeError(ValueError):
    """Stable fail-closed error for change derivation."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True)
class ChangeRecord:
    change_id: str
    change_type: str
    key: StateKey
    before_assertion_ids: tuple[str, ...]
    after_assertion_ids: tuple[str, ...]
    before_value_checksum: str | None
    after_value_checksum: str | None
    effective_at: str
    evidence_refs: tuple[str, ...]
    rule_id: str
    rule_version: str
    confidence: float
    uncertainty: tuple[str, ...]


@dataclass(frozen=True)
class ChangeSet:
    algorithm_version: str
    snapshot_id: str
    snapshot_hash: str
    before_as_of: str
    after_as_of: str
    records: tuple[ChangeRecord, ...]
    manifest_checksum: str


def _parse_time(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ChangeError("invalid_time", field) from exc
    if parsed.tzinfo is None:
        raise ChangeError("invalid_time", f"{field}:timezone_required")
    return parsed


def _ordered_steps(state: ProjectedState | None) -> tuple[FormationStep, ...]:
    if state is None:
        return ()
    return tuple(
        sorted(
            state.formation_path,
            key=lambda row: (
                _parse_time(row.valid_from, "valid_from"),
                _parse_time(row.observed_at, "observed_at"),
                row.assertion_id,
                row.run_id,
            ),
        )
    )


def _latest_steps(state: ProjectedState | None) -> tuple[FormationStep, ...]:
    ordered = _ordered_steps(state)
    if not ordered:
        return ()
    latest = max(
        (_parse_time(row.valid_from, "valid_from"), _parse_time(row.observed_at, "observed_at"))
        for row in ordered
    )
    return tuple(
        row
        for row in ordered
        if (
            _parse_time(row.valid_from, "valid_from"),
            _parse_time(row.observed_at, "observed_at"),
        )
        == latest
    )


def _assertion_ids(state: ProjectedState | None) -> tuple[str, ...]:
    if state is None:
        return ()
    if state.current_assertion_id:
        return (state.current_assertion_id,)
    return tuple(sorted(row.assertion_id for row in _latest_steps(state)))


def _evidence_refs(
    before: ProjectedState | None,
    after: ProjectedState | None,
) -> tuple[str, ...]:
    refs: set[str] = set()
    for state in (before, after):
        if state is None:
            continue
        refs.update(item.ref for item in state.evidence)
        refs.update(ref for row in _latest_steps(state) for ref in row.evidence_refs)
    return tuple(sorted(refs))


def _latest_time(state: ProjectedState | None, fallback: str) -> str:
    steps = _latest_steps(state)
    if not steps:
        return fallback
    return max(steps, key=lambda row: (_parse_time(row.valid_from, "valid_from"), _parse_time(row.observed_at, "observed_at"))).observed_at


def _has_evidenced_resolution(before: ProjectedState, after: ProjectedState) -> bool:
    before_steps = _latest_steps(before)
    after_steps = _latest_steps(after)
    if not after.current_assertion_id or not after_steps:
        return False
    before_moment = max(
        (
            _parse_time(row.valid_from, "valid_from"),
            _parse_time(row.observed_at, "observed_at"),
        )
        for row in before_steps
    ) if before_steps else None
    after_moment = max(
        (
            _parse_time(row.valid_from, "valid_from"),
            _parse_time(row.observed_at, "observed_at"),
        )
        for row in after_steps
    )
    later_assertion = before_moment is not None and after_moment > before_moment
    reviewed_event = any(
        trace.event_type in {"correct", "restore", "supersede", "rollback"}
        and bool(trace.event_id)
        for trace in after.lifecycle_path
    )
    return later_assertion or reviewed_event


def _classify(
    before: ProjectedState | None,
    after: ProjectedState | None,
) -> tuple[str, tuple[str, ...]] | None:
    if after is None:
        return None
    if after.status == "conflict":
        latest = _latest_steps(after)
        if len(latest) >= 2 and len({row.value_checksum for row in latest}) >= 2:
            if before is None or before.status != "conflict":
                return "conflict", tuple(sorted(set(after.uncertainty)))
        return None
    if before is not None and before.status == "conflict":
        if after.status in {"current", "uncertain"} and _has_evidenced_resolution(before, after):
            return "resolved", tuple(sorted(set(before.uncertainty + after.uncertainty)))
        return None
    if before is None or not before.current_assertion_id:
        if after.current_assertion_id and after.status in {"current", "uncertain"}:
            return "created", tuple(sorted(set(after.uncertainty)))
        return None
    if after.status in {"stale", "expired"} and _latest_steps(after):
        return "stale", tuple(sorted(set(after.uncertainty + ("no_current_evidence",))))
    if not after.current_assertion_id or after.status not in {"current", "uncertain"}:
        return None
    before_value = canonical_json(before.current_value)
    after_value = canonical_json(after.current_value)
    change_type = "reaffirmed" if before_value == after_value else "updated"
    return change_type, tuple(sorted(set(before.uncertainty + after.uncertainty)))


def _record(
    change_type: str,
    before: ProjectedState | None,
    after: ProjectedState,
    *,
    effective_at: str,
    uncertainty: tuple[str, ...],
) -> ChangeRecord:
    before_checksum = (
        checksum(before.current_value)
        if before is not None and before.current_assertion_id
        else None
    )
    after_checksum = checksum(after.current_value) if after.current_assertion_id else None
    confidence_values = [
        value
        for value in (
            before.confidence if before is not None else None,
            after.confidence,
        )
        if value is not None
    ]
    fields = {
        "change_type": change_type,
        "key": after.key,
        "before_assertion_ids": _assertion_ids(before),
        "after_assertion_ids": _assertion_ids(after),
        "before_value_checksum": before_checksum,
        "after_value_checksum": after_checksum,
        "effective_at": effective_at,
        "evidence_refs": _evidence_refs(before, after),
        "rule_id": BASE_CHANGE_RULE_ID,
        "rule_version": BASE_CHANGE_RULE_VERSION,
        "confidence": min(confidence_values) if confidence_values else 0.0,
        "uncertainty": uncertainty,
    }
    return ChangeRecord(
        change_id=f"psc_{checksum({'algorithm_version': CHANGE_ALGORITHM_VERSION, **fields})[:24]}",
        **fields,
    )


def compare_projections(
    before: StateProjection,
    after: StateProjection,
    *,
    algorithm_version: str = CHANGE_ALGORITHM_VERSION,
) -> ChangeSet:
    """Compare two compatible projections and return a stable metadata manifest."""
    if algorithm_version != CHANGE_ALGORITHM_VERSION:
        raise ChangeError("unsupported_algorithm_version", algorithm_version)
    if (
        before.snapshot_id != after.snapshot_id
        or before.snapshot_hash != after.snapshot_hash
    ):
        raise ChangeError("incompatible_snapshot")
    if _parse_time(before.as_of, "before_as_of") > _parse_time(after.as_of, "after_as_of"):
        raise ChangeError("invalid_projection_order")
    before_by_key = {state.key: state for state in before.states}
    after_by_key = {state.key: state for state in after.states}
    if len(before_by_key) != len(before.states) or len(after_by_key) != len(after.states):
        raise ChangeError("duplicate_state_key")

    records: list[ChangeRecord] = []
    for key in sorted(set(before_by_key) | set(after_by_key)):
        before_state = before_by_key.get(key)
        after_state = after_by_key.get(key)
        if after_state is None:
            continue
        classified = _classify(before_state, after_state)
        if classified is None:
            continue
        change_type, uncertainty = classified
        records.append(
            _record(
                change_type,
                before_state,
                after_state,
                effective_at=_latest_time(after_state, after.as_of),
                uncertainty=uncertainty,
            )
        )
    ordered = tuple(
        sorted(
            records,
            key=lambda row: (
                _parse_time(row.effective_at, "effective_at"),
                row.key,
                row.change_type,
                row.change_id,
            ),
        )
    )
    manifest = {
        "algorithm_version": algorithm_version,
        "snapshot_id": after.snapshot_id,
        "snapshot_hash": after.snapshot_hash,
        "before_as_of": before.as_of,
        "after_as_of": after.as_of,
        "records": ordered,
    }
    return ChangeSet(
        **manifest,
        manifest_checksum=checksum(manifest),
    )


def change_set_checksum(value: ChangeSet) -> str:
    """Recompute the manifest checksum for validation and replay tests."""
    return checksum(
        {
            "algorithm_version": value.algorithm_version,
            "snapshot_id": value.snapshot_id,
            "snapshot_hash": value.snapshot_hash,
            "before_as_of": value.before_as_of,
            "after_as_of": value.after_as_of,
            "records": value.records,
        }
    )
