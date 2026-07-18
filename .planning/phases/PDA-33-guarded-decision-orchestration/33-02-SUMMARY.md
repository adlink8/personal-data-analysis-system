---
phase: 33-guarded-decision-orchestration
plan: 02
subsystem: orchestration-generation
tags: [provider, reservation, at-most-once, analysis, replay]
requires:
  - phase: 33-01
    provides: confirmed checksum-chain session core
provides:
  - Durable append-only provider reservation/finalization
  - At-most-once confirmed generation coordinator
  - Adapter to the existing Analysis executor
affects: [33-03-authority-bridges, 33-04-acceptance]
tech-stack:
  added: []
  patterns: [reservation-before-call, unknown-outcome fail closed, terminal abstention]
key-files:
  created:
    - src/personal_knowledge/intelligence/orchestration/generation.py
    - tests/integration/test_orchestration_replay.py
  modified:
    - src/personal_knowledge/intelligence/orchestration/__init__.py
key-decisions:
  - "A reserved-but-unfinalized invocation is never retried automatically."
  - "Reservation and terminal records are separate append-only rows."
requirements-completed: [ORCH-02, ORCH-03]
duration: 20min
completed: 2026-07-19
---

# Phase 33 Plan 02: At-most-once Generation Summary

**Confirmed generation now reserves durably before the provider call, replays completed results, and fails closed on uncertain outcomes without a duplicate call.**

## Accomplishments

- Added reservation → provider → atomic finalize/event coordination.
- Added exact completed/abstained replay and idempotency conflict handling.
- Added an adapter that invokes the existing Analysis executor with `max_attempts=1` and stores only verified references.
- Proved completed replay, terminal abstention and reserved unknown-outcome behavior with a call counter.

## Task Commits

1. **At-most-once generation coordinator** — `a2d10fb`
2. **Generation replay tests** — `8d0dc41`

## Deviations from Plan

None. The selected append-only two-stage reservation model implements the planned crash boundary.

## Issues Encountered

None after implementation.

## Self-Check: PASSED

- Orchestration unit/integration suites: 9 passed.
- Completed and abstained requests call the injected runner once; reserved replay calls it zero times.

---
*Phase: 33-guarded-decision-orchestration*
*Completed: 2026-07-19*
