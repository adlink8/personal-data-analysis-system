from __future__ import annotations

from dataclasses import replace

import pytest

from personal_knowledge.intelligence.changes import (
    ChangeError,
    change_set_checksum,
    compare_projections,
)
from personal_knowledge.intelligence.schema import ValidatedEvidence, checksum
from personal_knowledge.intelligence.state_projection import (
    FormationStep,
    ProjectedState,
    StateKey,
    StateProjection,
)


SNAPSHOT_ID = "ss_test"
SNAPSHOT_HASH = "snapshot-hash"
KEY = StateKey("goal", "person", "health", "weekly", "exercise_minutes")


def _evidence(ref: str) -> ValidatedEvidence:
    return ValidatedEvidence(ref, "canonical_message", "d.canonical_conversation", "av_1", checksum(ref), "R2")


def _step(
    assertion_id: str,
    value: object,
    *,
    valid_from: str,
    observed_at: str | None = None,
    status: str = "candidate",
    evidence_ref: str | None = None,
) -> FormationStep:
    ref = evidence_ref or f"msg:{assertion_id}"
    return FormationStep(
        run_id=f"run:{assertion_id}",
        assertion_id=assertion_id,
        valid_from=valid_from,
        valid_to=None,
        observed_at=observed_at or valid_from,
        provenance_class="observation",
        lifecycle="current" if status == "candidate" else status,
        status=status,
        confidence=0.9,
        value_checksum=checksum(value),
        evidence_refs=(ref,),
        uncertainty=("source:bounded",),
    )


def _state(
    assertion_id: str | None,
    value: object = None,
    *,
    status: str = "current",
    steps: tuple[FormationStep, ...] = (),
    key: StateKey = KEY,
) -> ProjectedState:
    evidence = (_evidence(f"msg:{assertion_id}"),) if assertion_id else ()
    return ProjectedState(
        key=key,
        status=status,
        current_assertion_id=assertion_id,
        current_value=value,
        provenance_class="observation" if assertion_id else None,
        confidence=0.9 if assertion_id else None,
        uncertainty=("source:bounded",) if assertion_id else ("unknown_no_evidence",),
        evidence=evidence,
        formation_path=steps,
        lifecycle_path=(),
    )


def _projection(as_of: str, states: tuple[ProjectedState, ...]) -> StateProjection:
    return StateProjection(SNAPSHOT_ID, SNAPSHOT_HASH, as_of, states)


def _types(before: StateProjection, after: StateProjection) -> list[str]:
    return [row.change_type for row in compare_projections(before, after).records]


def test_created_updated_and_reaffirmed_have_explicit_lineage() -> None:
    old = _state("a1", 30, steps=(_step("a1", 30, valid_from="2026-01-01T00:00:00Z"),))
    new = _state("a2", 45, steps=old.formation_path + (_step("a2", 45, valid_from="2026-02-01T00:00:00Z"),))
    same = _state("a3", 45, steps=new.formation_path + (_step("a3", 45, valid_from="2026-03-01T00:00:00Z"),))

    created = compare_projections(_projection("2025-12-01T00:00:00Z", ()), _projection("2026-01-01T00:00:00Z", (old,))).records[0]
    updated = compare_projections(_projection("2026-01-01T00:00:00Z", (old,)), _projection("2026-02-01T00:00:00Z", (new,))).records[0]
    reaffirmed = compare_projections(_projection("2026-02-01T00:00:00Z", (new,)), _projection("2026-03-01T00:00:00Z", (same,))).records[0]

    assert (created.change_type, updated.change_type, reaffirmed.change_type) == ("created", "updated", "reaffirmed")
    assert updated.before_assertion_ids == ("a1",)
    assert updated.after_assertion_ids == ("a2",)
    assert updated.before_value_checksum == checksum(30)
    assert updated.after_value_checksum == checksum(45)
    assert updated.evidence_refs == ("msg:a1", "msg:a2")


def test_stale_requires_explicit_expiry_or_lifecycle_evidence() -> None:
    current = _state("a1", 30, steps=(_step("a1", 30, valid_from="2026-01-01T00:00:00Z"),))
    expired_step = replace(current.formation_path[0], valid_to="2026-02-01T00:00:00Z", status="expired")
    stale = _state(None, status="expired", steps=(expired_step,))
    missing = _state(None, status="unknown", steps=())

    assert _types(_projection("2026-01-01T00:00:00Z", (current,)), _projection("2026-03-01T00:00:00Z", (stale,))) == ["stale"]
    assert _types(_projection("2026-01-01T00:00:00Z", (current,)), _projection("2026-03-01T00:00:00Z", (missing,))) == []


def test_conflict_requires_simultaneous_incompatible_current_claims() -> None:
    base = _state("a1", 30, steps=(_step("a1", 30, valid_from="2026-01-01T00:00:00Z"),))
    conflict_steps = base.formation_path + (
        _step("a2", 45, valid_from="2026-02-01T00:00:00Z"),
        _step("a3", 60, valid_from="2026-02-01T00:00:00Z"),
    )
    conflict = _state(None, status="conflict", steps=conflict_steps)
    duplicate = _state(None, status="conflict", steps=conflict_steps[:-1] + (replace(conflict_steps[-1], value_checksum=checksum(45)),))

    record = compare_projections(_projection("2026-01-01T00:00:00Z", (base,)), _projection("2026-02-01T00:00:00Z", (conflict,))).records[0]
    assert record.change_type == "conflict"
    assert record.after_assertion_ids == ("a2", "a3")
    assert _types(_projection("2026-01-01T00:00:00Z", (base,)), _projection("2026-02-01T00:00:00Z", (duplicate,))) == []


def test_resolution_requires_later_evidence_not_disappearance() -> None:
    conflict = _state(
        None,
        status="conflict",
        steps=(
            _step("a1", 30, valid_from="2026-02-01T00:00:00Z"),
            _step("a2", 45, valid_from="2026-02-01T00:00:00Z"),
        ),
    )
    resolved = _state(
        "a3",
        45,
        steps=conflict.formation_path + (_step("a3", 45, valid_from="2026-03-01T00:00:00Z"),),
    )
    absent = _state(None, status="unknown", steps=conflict.formation_path)

    assert _types(_projection("2026-02-01T00:00:00Z", (conflict,)), _projection("2026-03-01T00:00:00Z", (resolved,))) == ["resolved"]
    assert _types(_projection("2026-02-01T00:00:00Z", (conflict,)), _projection("2026-03-01T00:00:00Z", (absent,))) == []


def test_incompatible_scope_never_compares_and_missing_predecessor_is_uncertainty() -> None:
    other_key = replace(KEY, scope="monthly")
    before = _state("a1", 30, steps=(_step("a1", 30, valid_from="2026-01-01T00:00:00Z"),))
    after = _state("a2", 45, key=other_key, steps=(_step("a2", 45, valid_from="2026-02-01T00:00:00Z"),))
    result = compare_projections(_projection("2026-01-01T00:00:00Z", (before,)), _projection("2026-02-01T00:00:00Z", (after,)))
    assert [row.change_type for row in result.records] == ["created"]
    assert all(row.change_type not in {"updated", "resolved", "conflict"} for row in result.records)


def test_reordered_states_and_tied_steps_replay_identically() -> None:
    key2 = replace(KEY, predicate="sleep_hours")
    a = _state("a1", 30, steps=(_step("a1", 30, valid_from="2026-01-01T00:00:00Z"),))
    b = _state("b1", 7, key=key2, steps=(_step("b1", 7, valid_from="2026-01-01T00:00:00Z"),))
    a2_steps = (
        _step("a3", 60, valid_from="2026-02-01T00:00:00Z"),
        _step("a2", 45, valid_from="2026-02-01T00:00:00Z"),
        *a.formation_path,
    )
    a2 = _state(None, status="conflict", steps=a2_steps)
    b2 = _state("b2", 8, key=key2, steps=b.formation_path + (_step("b2", 8, valid_from="2026-02-01T00:00:00Z"),))

    first = compare_projections(_projection("2026-01-01T00:00:00Z", (a, b)), _projection("2026-02-01T00:00:00Z", (a2, b2)))
    second = compare_projections(_projection("2026-01-01T00:00:00Z", (b, a)), _projection("2026-02-01T00:00:00Z", (b2, replace(a2, formation_path=tuple(reversed(a2_steps))))))
    assert first == second
    assert first.manifest_checksum == change_set_checksum(first)


def test_out_of_order_projection_or_cross_snapshot_fails_closed() -> None:
    empty_later = _projection("2026-02-01T00:00:00Z", ())
    empty_earlier = _projection("2026-01-01T00:00:00Z", ())
    with pytest.raises(ChangeError, match="invalid_projection_order"):
        compare_projections(empty_later, empty_earlier)
    with pytest.raises(ChangeError, match="incompatible_snapshot"):
        compare_projections(empty_earlier, replace(empty_later, snapshot_hash="different"))
