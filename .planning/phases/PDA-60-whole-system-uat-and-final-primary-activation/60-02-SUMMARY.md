---
phase: 60
plan: 02
subsystem: activation-gate
tags: [activation, rollback, legacy, readiness, human-checkpoint]
requires: [60-01]
provides: [honest-primary-block, synthetic-downgrade-evidence]
requirements-completed: []
completed: 2026-08-05
---

# Phase 60 Plan 02: Final primary activation and exact rollback

The readiness validator rejected the current Phase 53 evidence before any
route change. The automated drill verified shadow → declared failure → exact
legacy downgrade with append-only activation history. Primary and canary were
not activated; fresh mode remains `legacy`.

The remaining action is explicitly human and external: obtain an independent
paired cohort of at least two valid real cases, accept the frozen contracts,
then separately confirm shadow, canary and primary. This plan records a
blocked-but-honest completion rather than fabricating the missing authority.

## Verification

- `python -m pytest tests/e2e/test_pi_capability_os_activation.py -q` — 4 passed.
- `ops/reports/evidence/pi-capability-os-primary.json` — blocked, zero provider calls, no authority mutation.

## Self-Check: PASSED

- Implementation commit: f47663e
- Primary activation: not performed.
- Automatic upgrade: not allowed.
