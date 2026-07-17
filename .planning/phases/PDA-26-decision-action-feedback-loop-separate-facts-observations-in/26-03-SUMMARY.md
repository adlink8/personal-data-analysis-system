---
phase: 26-decision-action-feedback-loop
plan: 03
subsystem: decision-intelligence-effectiveness
tags: [sqlite, outcomes, effectiveness, observational, append-only, calibration]
requires:
  - phase: 26-02
    provides: Genesis-rooted human confirmation and action-attestation streams
provides:
  - Typed user-reported and evidence-measured outcome observations
  - Immutable versioned non-causal effectiveness assessments
  - Minimum-sample observational cohort summaries isolated by policy/domain/kind
affects: [26-04-interfaces, phase-27]
tech-stack:
  added: []
  patterns: [terminal-action outcome binding, explicit inconclusive semantics, Wilson interval cohort summaries]
key-files:
  created:
    - src/personal_knowledge/intelligence/decision/effectiveness.py
    - tests/unit/test_decision_effectiveness.py
    - tests/integration/test_decision_feedback_privacy.py
  modified:
    - src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py
    - src/personal_knowledge/intelligence/decision/schema.py
    - src/personal_knowledge/intelligence/decision/state_machine.py
    - tests/contract/test_decision_cognition_boundaries.py
    - tests/integration/test_decision_feedback_concurrency.py
key-decisions:
  - "Outcome is a typed user/system observation bound to a terminal action, never a fact or effectiveness claim."
  - "Every effectiveness record is an immutable inference with causal_claim=false; unsafe or insufficient inputs are inconclusive."
  - "Calibration is a read-only aggregate isolated by policy version, domain and recommendation kind after a declared minimum sample."
requirements-completed: [DEC-01, DEC-02]
duration: 14min
completed: 2026-07-18
---

# Phase 26 Plan 03: Outcome, Effectiveness and Calibration Summary

**Typed append-only outcome observations and observationally honest effectiveness over the existing recommendation stream**

## Performance

- **Duration:** 14 min
- **Completed:** 2026-07-18
- **Tasks:** 3
- **Files modified:** 8

## Accomplishments

- Added frozen outcome records that preserve `user_reported` versus `evidence_measured`, bind an immutable terminal action and recommendation checksum, and accept only same-snapshot typed Phase 25 evidence manifests.
- Extended the genesis-rooted event stream with atomic outcome and assessment writes under `BEGIN IMMEDIATE`, caller `expected_sequence`, idempotency keys, checksum replay and rollback.
- Added versioned pure assessment rules that separate adoption, action/adherence, observed result and effectiveness; missing, mismatched, non-adherent, confounded or concurrent evidence returns `inconclusive`.
- Kept every assessment as `cognitive_type=inference`, `causal_claim=false`, with exact action/outcome checksums and explicit observational limitations.
- Added read-only cohort summaries grouped by policy version/domain/recommendation kind, gated by a named minimum sample and reporting verdict counts, rate and Wilson interval without changing historical records or rules.

## Task Commits

1. **Task 1: Failing outcome/effectiveness/privacy/concurrency contracts** — `6045e9a`
2. **Task 2: Typed append-only outcome observations** — `25d108f`
3. **Task 3: Immutable non-causal effectiveness and bounded calibration** — `5a6e946`

## Decisions Made

- No outcome is synthesized when evidence is absent; unknown stays absent/unknown rather than becoming failure.
- Rejection and non-adherence affect acceptability/execution context only and cannot establish ineffectiveness.
- `effective`, `ineffective` and `mixed` describe compatible observed goal attainment only, never a counterfactual or causal impact.
- Typed source bodies, unrestricted notes, secrets, cross-snapshot references and unbound evidence fail before any row is published.

## Deviations from Plan

- The additive schema definition remains in the repository's canonical migration module, so that existing temporary-database fixtures exercise the real authority schema. No live migration was applied.

## Verification

- Phase 26 plan tests: `38 passed`.
- Phase 25 adjacent change/provenance/explanation regression: `45 passed`.
- Governance preflight: `13/13 PASS`.
- Full repository: `767 passed, 2 skipped`; two pre-existing `SyntaxWarning` messages only.
- `git diff --check`: passed.

All writes ran only against temporary SQLite fixtures. No live migration, outcome/assessment write, lifecycle apply, serving/pointer/watermark change, network call, paid call or external action occurred. Phase 24 remains `release_blocked`.

## Next Phase Readiness

- Ready for 26-04 shared read interfaces, explicit local write CLI and metadata-only zero-mutation acceptance.
- Phase 24 human Gold/Judge/UAT and lifecycle quality gates remain unresolved and release-blocking.

## Self-Check: PASSED

- All three task commits and plan artifacts exist.
- Outcome and assessment streams replay and reject tampered checksums.
- No record claims causality or modifies historical Phase 25, KU, recommendation or policy data.

---
*Phase: 26-decision-action-feedback-loop*
*Completed: 2026-07-18*
