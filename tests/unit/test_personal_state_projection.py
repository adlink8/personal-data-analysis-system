from __future__ import annotations

from copy import deepcopy

import pytest

from personal_knowledge.intelligence.schema import SnapshotBinding, canonical_json
from personal_knowledge.intelligence.state_projection import (
    ProjectionError,
    normalize_candidates,
)


def _snapshot() -> SnapshotBinding:
    return SnapshotBinding(
        snapshot_id="ss1",
        snapshot_hash="hash1",
        members={
            "canonical_knowledge": {
                "artifact_version_id": "av1",
                "privacy_class": "R4",
            }
        },
    )


def _candidate(**overrides: object) -> dict:
    value = {
        "snapshot_id": "ss1",
        "snapshot_hash": "hash1",
        "assertion_kind": "goal",
        "provenance_class": "observation",
        "derivation": "occurrence",
        "subject": "user",
        "domain": "work",
        "scope": "personal",
        "predicate": "complete_target",
        "value": "D",
        "valid_from": "2026-07-17T00:00:00Z",
        "valid_to": None,
        "observed_at": "2026-07-17T00:01:00Z",
        "confidence": 0.9,
        "uncertainty_reason": "explicit user statement",
        "evidence": [
            {
                "snapshot_id": "ss1",
                "snapshot_hash": "hash1",
                "ref": "ku2",
                "artifact_type": "knowledge_unit",
                "serving_role": "canonical_knowledge",
                "artifact_version_id": "av1",
                "privacy_class": "R4",
            },
            {
                "snapshot_id": "ss1",
                "snapshot_hash": "hash1",
                "ref": "ku1",
                "artifact_type": "knowledge_unit",
                "serving_role": "canonical_knowledge",
                "artifact_version_id": "av1",
                "privacy_class": "R4",
            },
        ],
    }
    value.update(overrides)
    return value


def test_normalization_is_order_and_evidence_order_deterministic() -> None:
    first = _candidate(predicate="first", value=1)
    second = _candidate(predicate="second", value=2)
    reversed_evidence = deepcopy(first)
    reversed_evidence["evidence"].reverse()
    left = normalize_candidates([first, second], snapshot=_snapshot())
    right = normalize_candidates([second, reversed_evidence], snapshot=_snapshot())
    assert canonical_json(left) == canonical_json(right)
    assert [item.ref for item in left[0].evidence] == ["ku1", "ku2"]


def test_invalid_interval_and_missing_evidence_fail_with_stable_codes() -> None:
    with pytest.raises(ProjectionError) as interval:
        normalize_candidates(
            [_candidate(valid_to="2026-07-16T00:00:00Z")], snapshot=_snapshot()
        )
    assert interval.value.code == "invalid_time_interval"

    with pytest.raises(ProjectionError) as evidence:
        normalize_candidates([_candidate(evidence=[])], snapshot=_snapshot())
    assert evidence.value.code == "evidence_required"


def test_source_bodies_and_secret_like_values_are_rejected() -> None:
    with pytest.raises(ProjectionError) as body:
        normalize_candidates([_candidate(content="raw source body")], snapshot=_snapshot())
    assert body.value.code == "private_payload"

    with pytest.raises(ProjectionError) as secret:
        normalize_candidates(
            [_candidate(value="password=do-not-store")], snapshot=_snapshot()
        )
    assert secret.value.code == "secret_payload"

