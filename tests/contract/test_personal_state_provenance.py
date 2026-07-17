from __future__ import annotations

import pytest

from personal_knowledge.intelligence.schema import SnapshotBinding
from personal_knowledge.intelligence.state_projection import (
    ProjectionError,
    normalize_candidates,
)
from tests.unit.test_personal_state_projection import _candidate


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


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"derivation": "synthesis", "provenance_class": "fact"}, "provenance_rule_violation"),
        (
            {
                "assertion_kind": "observation",
                "derivation": "canonical_fact",
                "provenance_class": "fact",
            },
            "observation_as_fact",
        ),
        ({"derivation": "occurrence", "provenance_class": "inference"}, "provenance_rule_violation"),
    ],
)
def test_provenance_classes_cannot_be_silently_promoted(
    overrides: dict, code: str
) -> None:
    with pytest.raises(ProjectionError) as error:
        normalize_candidates([_candidate(**overrides)], snapshot=_snapshot())
    assert error.value.code == code


def test_candidate_and_evidence_must_share_one_snapshot() -> None:
    with pytest.raises(ProjectionError) as candidate:
        normalize_candidates([_candidate(snapshot_id="ss2")], snapshot=_snapshot())
    assert candidate.value.code == "mixed_snapshot"

    row = _candidate()
    row["evidence"][0]["snapshot_hash"] = "other"
    with pytest.raises(ProjectionError) as evidence:
        normalize_candidates([row], snapshot=_snapshot())
    assert evidence.value.code == "mixed_snapshot"


def test_snapshot_member_version_is_authoritative() -> None:
    row = _candidate()
    row["evidence"][0]["artifact_version_id"] = "av-other"
    with pytest.raises(ProjectionError) as error:
        normalize_candidates([row], snapshot=_snapshot())
    assert error.value.code == "evidence_version_mismatch"


def test_only_explicit_canonical_facts_retain_fact_provenance() -> None:
    normalized = normalize_candidates(
        [
            _candidate(
                assertion_kind="constraint",
                derivation="canonical_fact",
                provenance_class="fact",
            )
        ],
        snapshot=_snapshot(),
    )
    assert normalized[0].provenance_class == "fact"


@pytest.mark.parametrize("field", ["snapshot_id", "provenance_class", "observed_at"])
def test_required_lineage_and_temporal_fields_fail_closed(field: str) -> None:
    row = _candidate()
    row.pop(field)
    with pytest.raises(ProjectionError) as error:
        normalize_candidates([row], snapshot=_snapshot())
    assert error.value.code == "missing_field"
    assert error.value.detail == field
