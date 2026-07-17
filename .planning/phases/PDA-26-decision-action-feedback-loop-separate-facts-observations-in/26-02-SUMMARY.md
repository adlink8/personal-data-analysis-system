---
phase: 26-decision-action-feedback-loop
plan: 02
subsystem: decision-intelligence-state-machine
tags: [sqlite, recommendations, append-only, idempotency, concurrency]
requires:
  - phase: 26-01
    provides: Non-serving decision authority, immutable recommendations and publication genesis
provides:
  - Versioned deterministic recommendation rules with explicit abstention
  - Human-only confirmation and action-attestation records
  - Genesis-rooted checksum event streams with idempotent concurrent writes
affects: [26-03-effectiveness, 26-04-interfaces, phase-27]
tech-stack:
  added: []
  patterns: [BEGIN IMMEDIATE expected-sequence writes, checksum-linked pure projection, typed-row plus event transaction]
key-files:
  created:
    - src/personal_knowledge/intelligence/decision/recommendations.py
    - src/personal_knowledge/intelligence/decision/state_machine.py
    - tests/unit/test_decision_state_machine.py
    - tests/integration/test_decision_feedback_concurrency.py
  modified:
    - src/personal_knowledge/intelligence/decision/schema.py
    - src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py
    - tests/contract/test_decision_cognition_boundaries.py
key-decisions:
  - "Recommendation rules are immutable and versioned; unsafe Phase 25 inputs return a reason-coded abstention rather than a proposal."
  - "Confirmation records a human decision only, and action records are non-executable attestations with a separate legal transition path."
  - "Every stream hydrates from exactly one sequence=1 publication genesis and extends under BEGIN IMMEDIATE with caller expected_sequence and idempotency key."
requirements-completed: [DEC-01, DEC-02]
duration: 15min
completed: 2026-07-18
---

# Phase 26 Plan 02: Recommendation, Confirmation and Action State Machine Summary

**Deterministic bounded recommendations and human-only confirmation/action attestations over one concurrency-safe, genesis-rooted checksum stream**

## Performance

- **Duration:** 15 min
- **Started:** 2026-07-17T23:26:22Z
- **Completed:** 2026-07-17T23:41:24Z
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Added immutable rule definitions and deterministic evaluation that abstains on insufficient, stale, conflicting, uncertain, contraindicated, ineligible or cross-snapshot inputs.
- Added pure history projection that revalidates the recommendation, decision run, publication genesis, typed rows, legal transitions and every previous-event checksum.
- Added explicit local append APIs using `BEGIN IMMEDIATE`, human actor hashes, expiry, expected sequence and idempotency keys; stale concurrent writers and changed-payload retries fail closed.
- Kept acceptance separate from action: accept inserts no action, action records reject executable commands/URLs/connectors/credentials/dispatch targets, and no external executor exists.

## Task Commits

1. **Task 1: Failing recommendation, permission, replay and concurrency tests** — `c22afe0`
2. **Task 2: Versioned deterministic recommendation rules** — `0e3cfe4`
3. **Task 3: Append-only confirmation and action streams** — `ad78ef1`

## Decisions Made

- The current sequence is the caller's `expected_sequence`; a successful append reserves `expected_sequence + 1` and binds the prior event checksum.
- `accept`, `reject`, `defer` and `revoke_before_action` are confirmation states only. Actions begin only after accept and are limited to planned/started/completed/abandoned/not_taken attestations.
- Same-key/same-payload retries return the original receipt after full history validation; same-key/changed-payload retries return `idempotency_conflict`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## Verification

- Phase 26 plan and adjacent 26-01 regression: `30 passed`.
- Phase 25 unit/contract/integration regression: `87 passed`.
- Governance preflight: `13/13 PASS`.
- Full repository: `744 passed, 2 skipped`; two pre-existing `SyntaxWarning` messages only.
- `git diff --check`: passed.

All databases used by decision writes were temporary SQLite fixtures. No live migration, confirmation/action write, lifecycle apply, serving/pointer/watermark change, network call, paid call or external action occurred. Phase 24 remains `release_blocked`.

## User Setup Required

None.

## Next Phase Readiness

- Ready for 26-03 typed outcomes, observational non-causal effectiveness and bounded calibration.
- Phase 24 human Gold/Judge/UAT and lifecycle quality gates remain unresolved and release-blocking.

## Self-Check: PASSED

- All created files and task commits exist.
- All plan, regression, governance and full-repository verification commands passed.
- Recommendation/confirmation/action records remain non-serving and non-executable.

---
*Phase: 26-decision-action-feedback-loop*
*Completed: 2026-07-18*
