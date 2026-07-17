from __future__ import annotations

from copy import deepcopy

import pytest

from personal_knowledge.intelligence.schema import (
    PersonalStateRun,
    SnapshotBinding,
    ValidatedAssertion,
    ValidatedEvidence,
    canonical_json,
    checksum,
)
from personal_knowledge.intelligence.state_projection import (
    ProjectionError,
    StateKey,
    normalize_candidates,
    project_current_state,
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


def _validated(
    assertion_id: str,
    *,
    value: object,
    valid_from: str,
    observed_at: str,
    assertion_kind: str = "goal",
    predicate: str = "complete_target",
    confidence: float = 0.9,
    lifecycle: str = "current",
    artifact_version_id: str = "av1",
) -> ValidatedAssertion:
    return ValidatedAssertion(
        assertion_id=assertion_id,
        assertion_kind=assertion_kind,
        provenance_class="observation",
        subject="user",
        domain="work",
        scope="personal",
        predicate=predicate,
        value=value,
        valid_from=valid_from,
        valid_to=None,
        observed_at=observed_at,
        confidence=confidence,
        uncertainty="fixture evidence",
        lifecycle=lifecycle,
        evidence=(
            ValidatedEvidence(
                ref=f"ku-{assertion_id}",
                artifact_type="knowledge_unit",
                serving_role="canonical_knowledge",
                artifact_version_id=artifact_version_id,
                evidence_checksum=checksum(assertion_id),
                privacy_class="R4",
            ),
        ),
        payload_checksum=checksum([assertion_id, value]),
    )


def _run(run_id: str, *assertions: ValidatedAssertion) -> PersonalStateRun:
    input_manifest = {"run": run_id}
    output_manifest = {"assertions": [item.assertion_id for item in assertions]}
    return PersonalStateRun(
        run_id=run_id,
        registry_id="a.personal_change",
        snapshot=_snapshot(),
        producer_version="projection-test",
        input_manifest=input_manifest,
        input_manifest_checksum=checksum(input_manifest),
        output_manifest=output_manifest,
        output_manifest_checksum=checksum(output_manifest),
        assertions=tuple(assertions),
    )


def test_current_state_and_formation_path_replay_deterministically() -> None:
    old = _validated(
        "a-old",
        value="A",
        valid_from="2026-01-01T00:00:00Z",
        observed_at="2026-01-01T01:00:00Z",
    )
    current = _validated(
        "a-current",
        value="D",
        valid_from="2026-06-01T00:00:00Z",
        observed_at="2026-06-01T01:00:00Z",
    )
    left = project_current_state(
        [_run("run-new", current), _run("run-old", old)],
        as_of="2026-07-18T00:00:00Z",
    )
    right = project_current_state(
        [_run("run-old", old), _run("run-new", current)],
        as_of="2026-07-18T00:00:00Z",
    )
    assert canonical_json(left) == canonical_json(right)
    state = left.current_goals[0]
    assert state.current_value == "D"
    assert [step.assertion_id for step in state.formation_path] == ["a-old", "a-current"]
    assert state.evidence[0].ref == "ku-a-current"


def test_unknown_expired_and_low_confidence_remain_explicit() -> None:
    expired = _validated(
        "expired",
        value="old",
        valid_from="2026-01-01T00:00:00Z",
        observed_at="2026-01-01T01:00:00Z",
        lifecycle="expired",
    )
    low = _validated(
        "low",
        value="tentative",
        valid_from="2026-06-01T00:00:00Z",
        observed_at="2026-06-01T01:00:00Z",
        predicate="tentative_goal",
        confidence=0.4,
    )
    missing = StateKey("constraint", "user", "work", "personal", "budget")
    projection = project_current_state(
        [_run("run", expired, low)],
        as_of="2026-07-18T00:00:00Z",
        expected_keys=[missing],
    )
    by_predicate = {row.key.predicate: row for row in projection.states}
    assert by_predicate["complete_target"].status == "expired"
    assert "no_current_evidence" in by_predicate["complete_target"].uncertainty
    assert by_predicate["tentative_goal"].status == "uncertain"
    assert "low_confidence" in by_predicate["tentative_goal"].uncertainty
    assert by_predicate["budget"].status == "unknown"
    assert by_predicate["budget"].uncertainty == ("unknown_no_evidence",)


def test_simultaneous_contradiction_is_not_silently_selected() -> None:
    first = _validated(
        "a1",
        value="A",
        valid_from="2026-06-01T00:00:00Z",
        observed_at="2026-06-01T01:00:00Z",
    )
    second = _validated(
        "a2",
        value="B",
        valid_from="2026-06-01T00:00:00Z",
        observed_at="2026-06-01T01:00:00Z",
    )
    state = project_current_state(
        [_run("run", first, second)], as_of="2026-07-18T00:00:00Z"
    ).states[0]
    assert state.status == "conflict"
    assert state.current_assertion_id is None
    assert state.current_value is None
    assert "unresolved_conflict" in state.uncertainty


def test_historical_conflict_does_not_override_newer_current_evidence() -> None:
    old_conflict = _validated(
        "old-conflict",
        value="A",
        valid_from="2026-01-01T00:00:00Z",
        observed_at="2026-01-01T01:00:00Z",
        lifecycle="conflict",
    )
    current = _validated(
        "current",
        value="D",
        valid_from="2026-06-01T00:00:00Z",
        observed_at="2026-06-01T01:00:00Z",
    )
    state = project_current_state(
        [_run("run", old_conflict, current)], as_of="2026-07-18T00:00:00Z"
    ).states[0]
    assert state.status == "current"
    assert state.current_assertion_id == "current"
