---
phase: 33-guarded-decision-orchestration
plan: 03
subsystem: orchestration-authority-bridges
tags: [pilot, calibration, confirmation, replay, authority]
requires:
  - phase: 33-02
    provides: at-most-once confirmed generation
provides:
  - Guarded bridges to Pilot publish, decision, protocol, action and observation authorities
  - Non-causal, no-promotion calibration boundary
  - Exact downstream replay without duplicate effects
affects: [33-04-transports, 34-operator-ux]
tech-stack:
  added: []
  patterns: [authorize-before-effect, idempotent-authority-bridge, explicit-manual-action]
key-files:
  created:
    - src/personal_knowledge/intelligence/orchestration/bridges.py
    - tests/integration/test_orchestration_flow.py
  modified:
    - src/personal_knowledge/intelligence/orchestration/service.py
    - src/personal_knowledge/intelligence/orchestration/__init__.py
key-decisions:
  - "Every authority bridge validates confirmation, actor, binding, state and sequence before the downstream write."
  - "Pilot execution remains user-reported and calibration remains non-causal with no automatic promotion."
requirements-completed: [ORCH-01, ORCH-03, ORCH-04]
duration: 25min
completed: 2026-07-19
---

# Phase 33 Plan 03: Guarded Authority Bridges Summary

**A confirmed session now traverses the real immutable Pilot authorities through calibration while retaining zero automated external actions and no automatic promotion.**

## Accomplishments

- Added publish, decide, outcome preregistration, manual action, observation and calibration bridges.
- Added pre-effect authorization and exact consumed-confirmation replay handling.
- Hardened actor identities to the Pilot authority's 64-character lowercase SHA-256 contract.
- Proved the complete local authority flow, blocked external-action text and single-use confirmation behavior.

## Task Commits

1. **Authority bridges and transition authorization** — `71d8d6d`
2. **Positive and negative integration coverage** — `0b54682`

## Deviations from Plan

The originally compact decide→observe path was expanded with explicit preregister, action-start and action-complete states because those are mandatory immutable Pilot authority transitions.

## Issues Encountered

Replay authorization initially checked the current sequence before recognizing an exact completed event. It now authenticates the consumed token against the original event first and returns the immutable result without re-running the authority write.

## Self-Check: PASSED

- Orchestration unit/integration suites: 12 passed.
- Provider/network/external actions remain zero across the bridge tests.
- Observation and calibration references explicitly retain `causal_claim=false`; promotion remains unavailable.

---
*Phase: 33-guarded-decision-orchestration*
*Completed: 2026-07-19*
