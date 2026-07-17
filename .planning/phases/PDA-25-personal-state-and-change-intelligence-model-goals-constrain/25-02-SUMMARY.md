---
phase: 25-personal-state-and-change-intelligence
plan: 02
subsystem: intelligence-projection
tags: [state-projection, provenance, temporal-history, lifecycle-lineage, uncertainty]

requires:
  - phase: 25-01
    provides: Immutable snapshot-bound run, assertion and evidence records
  - phase: 24-03
    provides: Reviewed lifecycle event ledger and explicit pending human checkpoint
provides:
  - Deterministic normalization of typed goal, constraint and observation candidates
  - Current-state projection with ordered formation and applied-lifecycle paths
  - Explicit unknown, expired, stale, conflict and low-confidence states
affects: [25-03-change-intelligence, 25-04-interfaces, phase-26]

tech-stack:
  added: []
  patterns: [pure deterministic projection, stable reason codes, run-context assertion identity]

key-files:
  created: []
  modified:
    - src/personal_knowledge/intelligence/state_projection.py
    - src/personal_knowledge/intelligence/runs.py
    - tests/unit/test_personal_state_projection.py
    - tests/contract/test_personal_state_provenance.py
    - tests/integration/test_personal_state_runs.py

key-decisions:
  - "Only canonical facts retain fact provenance; occurrences remain observations and synthesis remains inference."
  - "Projection requires an explicit as_of timestamp so replay never depends on wall-clock time."
  - "Only stored lifecycle events with reviewer and actor evidence affect formation paths; pending proposals have zero effect."

patterns-established:
  - "Unknown is evidence absence, not a negative fact."
  - "Current-state selection is ordered by valid time, observed time, assertion ID and run ID."

requirements-completed: [INTEL-01, INTEL-02]

duration: 13min
completed: 2026-07-18
---

# Phase 25 Plan 02: Typed State Projection Summary

**Deterministic goal, constraint and observation normalization with evidence-backed current state, formation paths and explicit uncertainty**

## Performance

- **Duration:** 13 min
- **Started:** 2026-07-17T21:11:00Z
- **Completed:** 2026-07-17T21:24:01Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added order-independent normalization that enforces explicit derivation/provenance rules, temporal fields, snapshot metadata and sorted eligible evidence refs.
- Added multi-run current-state projection with deterministic formation paths, current goals/constraints/observations and explicit unknown/expired/stale/conflict/low-confidence states.
- Added metadata-only lifecycle explanations that require applied event evidence and completely ignore Phase 24 pending proposals.
- Made assertion IDs run-context-scoped so distinct producer/input runs can persist the same semantic assertion without collision while exact replay remains idempotent.

## Task Commits

Each task was committed atomically:

1. **Task 1: Normalize typed state assertions from snapshot-bound inputs** - `11c5eb3`
2. **Task 2: Reconstruct current state and its formation path** - `7a1480d`

## Files Created/Modified

- `src/personal_knowledge/intelligence/state_projection.py` - Candidate normalization, state keys, formation/lifecycle traces and deterministic projection.
- `src/personal_knowledge/intelligence/runs.py` - Run-context assertion IDs and replay validation.
- `tests/unit/test_personal_state_projection.py` - Golden replay, ordering, uncertainty, conflict and current-state tests.
- `tests/contract/test_personal_state_provenance.py` - Provenance, cross-snapshot, pending-review and lifecycle-lineage contracts.
- `tests/integration/test_personal_state_runs.py` - Multiple distinct immutable runs with repeated semantic assertions.

## Decisions Made

- Projection accepts immutable `PersonalStateRun` records and rejects mixed snapshots or member versions before deriving state.
- `as_of` is mandatory and timezone-aware; a default wall clock would make golden replay nondeterministic.
- Lifecycle reasons are represented by checksums, while applied event IDs and state transitions remain drill-down metadata.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Correctness] Prevented cross-run assertion primary-key collisions**
- **Found during:** Task 2 (versioned formation path)
- **Issue:** Semantic assertion IDs were identical across different producer/input runs in one snapshot, so the second immutable run could not be published.
- **Fix:** Scoped assertion IDs to a deterministic run context digest while retaining the semantic payload checksum.
- **Files modified:** `runs.py`, `test_personal_state_runs.py`
- **Verification:** Three runs spanning producer and snapshot changes publish as three runs/assertions/evidence rows; exact replay remains one run.
- **Committed in:** `7a1480d`

---

**Total deviations:** 1 auto-fixed correctness issue. **Impact on plan:** Required for the versioned history and formation-path objective; no authority or scope expansion.

## Issues Encountered

None beyond the auto-fixed identity collision above.

## Verification

- Plan command: projection/provenance/history/lifecycle — 35 passed.
- 25-01 run/schema/serving/evidence/registry regression — 26 passed.
- Combined targeted evidence — 61 passed.
- `python -m py_compile ...` and `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 25-03 change, conflict, trend, risk and explanation derivation over deterministic formation histories.
- INTEL-01/02 final acceptance remains pending Plans 25-03/04 and phase verification.
- Phase 24 human review remains pending and has zero projection effect.

## Self-Check: PASSED

- Both task commits exist and all declared artifacts are present.
- Stable reason codes cover provenance, temporal, privacy and snapshot failures.
- Golden projection replay is byte-identical and pending Phase 24 proposals have zero effect.

---
*Phase: 25-personal-state-and-change-intelligence*
*Completed: 2026-07-18*
