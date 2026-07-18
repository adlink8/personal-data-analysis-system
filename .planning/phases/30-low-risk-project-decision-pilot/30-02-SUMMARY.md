---
phase: 30-low-risk-project-decision-pilot
plan: 02
subsystem: decision-intelligence
tags: [event-stream, idempotency, human-control, outcome-window, non-causal]
requires:
  - phase: 30-low-risk-project-decision-pilot
    provides: frozen pilot case and non-authoritative recommendation candidate
provides:
  - user-owned accept/reject/defer workflow
  - manual action observation stream with zero system execution
  - preregistered non-causal outcome assessment
affects: [30-03, phase-31-calibration]
tech-stack:
  added: []
  patterns: [expected-sequence writes, idempotent event receipts, preregister-before-action]
key-files:
  created:
    - src/personal_knowledge/intelligence/pilot/workflow.py
    - src/personal_knowledge/intelligence/pilot/outcomes.py
    - tests/contract/test_project_pilot_workflow.py
    - tests/integration/test_project_pilot_outcomes.py
  modified: []
key-decisions:
  - "Record the user's decision separately from Codex operator execution and user-reported observation."
  - "Treat a complete compatibility receipt as observational PASS, never as a causal effectiveness claim."
patterns-established:
  - "Every mutable transition is an append-only compensable event with expected sequence and idempotency key."
  - "Metric, baseline, target, source and window are frozen before the manual action starts."
requirements-completed: [PDI-07]
duration: 24min
completed: 2026-07-18
---

# Phase 30 Plan 02: User-owned Decision and Outcome Chain Summary

**The real validate-before-adopt case now has a preregistered metric, user-authorized decision, local operator action, bounded outcome and independent defer control path.**

## Performance

- **Duration:** 24 min
- **Started:** 2026-07-18T12:30:00Z
- **Completed:** 2026-07-18T12:54:00Z
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Implemented distinct append-only preregistration, user-decision, manual-action and observation events.
- Executed the real local compatibility action on Python 3.14.2 and Node.js 24.13.0 after protocol freeze.
- Observed `target_runtime_compatibility_suite_pass_rate=1.0` against target `1.0`; assessment is non-causal `pass` with no confounders.
- Added real control case `ppc_b62f0f3506ca07a074c9ed54`, deferring direct adoption in favor of validation-first.

## Task Commits

1. **Task 1: Implement user-owned workflow and control paths** - `f3aad59` (feat)
2. **Task 2: Perform selected low-risk project action manually** - live event chain `ppe_a3862801f8f8894687082299` through `ppe_d574b126204a5df1ae849116`
3. **Task 3: Record and assess the observation window** - `be0515c` (feat), live observation `ppe_cb8d9c18e486785ca9a8fcfc`

## Files Created/Modified

- `src/personal_knowledge/intelligence/pilot/workflow.py` - Expected-sequence user decisions and manual action observations.
- `src/personal_knowledge/intelligence/pilot/outcomes.py` - Preregistered metrics, bounded observations and non-causal assessment.
- `tests/contract/test_project_pilot_workflow.py` - Sovereignty, control path, idempotency and zero-action contracts.
- `tests/integration/test_project_pilot_outcomes.py` - PASS/FAIL/INCONCLUSIVE window semantics.

## Decisions Made

- Prior explicit user instructions `授权执行` and `无需授权直接进行` are represented only by a hashed authorization reference; no raw message or fabricated user action is stored.
- Codex is recorded as the local operator, while the system reports zero automated external actions.
- Direct adoption is preserved as a separate defer control case rather than conflicting with the accepted validation-first stream.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- `python -m pytest tests/contract/test_project_pilot_workflow.py tests/integration/test_project_pilot_outcomes.py -q` — 5 passed.
- Runtime receipts — Python 3.14.2 and Node.js v24.13.0.
- Combined Phase 30 focused suite — 11 passed.
- Governance preflight — 13/13 PASS; dependency lock confirms no install.
- `git diff --check` — passed.

## Self-Check: PASSED

- Main stream has six checksum-chained events and exact case confirmation.
- Control stream has a separate frozen case plus explicit defer.
- Outcome protocol predates the action and the observation follows the window.
- System external actions, provider calls and cost are zero.

## Next Phase Readiness

Plan 30-03 can add compensating controls, snapshot recovery validation, bounded product reads and final exact-evidence acceptance.

---
*Phase: 30-low-risk-project-decision-pilot*
*Completed: 2026-07-18*
