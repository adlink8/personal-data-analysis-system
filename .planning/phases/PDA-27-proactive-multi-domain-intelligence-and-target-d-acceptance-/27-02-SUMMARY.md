---
phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance
plan: 02
subsystem: proactive-ranking-noise-governance
tags: [proactive, ranking, novelty, deduplication, cooldown, privacy, sqlite]
requires:
  - phase: 27-01
    provides: Immutable proactive run authority and exact Phase 25/26 binding
provides:
  - Deterministic evidence-bound proactive candidate importance and novelty
  - Immutable reason-coded deduplication, cooldown, quiet-period and noise-budget evaluation
  - Atomic candidate/support/evaluation publication with fail-closed replay and tamper checks
affects: [27-03, 27-04]
tech-stack:
  added: []
  patterns: [canonical-json-sha256, abstention-before-ranking, deterministic-budget-order, begin-immediate]
key-files:
  created:
    - src/personal_knowledge/intelligence/proactive/ranking.py
    - tests/unit/test_proactive_ranking.py
    - tests/integration/test_proactive_privacy.py
  modified:
    - src/personal_knowledge/intelligence/proactive/schema.py
    - src/personal_knowledge/intelligence/proactive/runs.py
    - tests/contract/test_proactive_boundaries.py
    - tests/integration/test_proactive_runs.py
key-decisions:
  - "Privacy, evidence and explicit trust vetoes are evaluated before importance, criticality, quiet periods or numeric budgets."
  - "Candidate dedup identity includes a material-change signature, while cooldown uses a separate stable class/subject/scope/domain key."
  - "Quiet periods only emit deferred_until metadata; no scheduler, sender or external action is created."
requirements-completed: [PRO-02]
completed: 2026-07-18
release_status: release_blocked
---

# Phase 27 Plan 02: Important-change Ranking and Noise Governance Summary

**Deterministic evidence-bound inbox/digest candidates with immutable privacy-first ranking and reason-coded noise suppression**

## Accomplishments

- Added all seven closed candidate classes as metadata-only `inbox_item`/`digest_item` proposals with exact typed support IDs, source/run/snapshot checksums and explicit fixture-only usefulness labels.
- Added a versioned eight-component importance vector with bounded values, stable weighted score, threshold abstention and candidate-ID tie breaking. Private, sensitive, ineligible-evidence, mixed-snapshot and explicit trust inputs fail closed before ranking.
- Added canonical material novelty from severity/urgency bands, new eligible evidence, goal/constraint relation version and prior expiry. Stable candidate identity and payload checksums make replay byte-identical.
- Published candidate, support and evaluation rows atomically with the parent proactive run under the existing `BEGIN IMMEDIATE` source/frontier revalidation transaction. Exact replay is idempotent; candidate/evaluation faults and tamper leave zero partial rows.
- Added explicit `as_of`, timezone and evaluation windows; stable deduplication, surfaced/acknowledged-only cooldown, quiet deferral, global/per-domain rolling budgets, deterministic boundary ordering and reason-coded suppression counts.
- Added metadata-only digest proposals that retain every support manifest and never merge contradictory evidence. No scheduler, connector, recipient, notification sender, executable payload, network or paid call was introduced.

## Task Commits

1. **Task 1: GREEN candidate, importance and privacy-veto behavior** — `750bd7f`
2. **Task 2: Novelty and atomic candidate publication** — `077bc52`
3. **Task 3: Deduplication, cooldown, quiet periods, digest and noise budgets** — `95f39e0`

Task 1 preserved the requested test-first evidence: the first focused run failed at collection because `proactive.ranking` did not exist; the completed implementation made the same suite pass.

## Verification

- Phase 27-01/02 targeted suite: **49 passed**.
- Phase 25/26 adjacent regression: **37 passed**.
- Governance preflight: **13/13 PASS**.
- Full repository: **841 passed, 2 skipped**; only two pre-existing `SyntaxWarning` messages.
- `git diff --check`: PASS.

All database tests used disposable SQLite fixtures. No live migration/write, lifecycle apply, serving snapshot/pointer/watermark mutation, notification delivery, external action, network call or paid call occurred.

## Preserved Release Boundary

Phase 24 remains unchanged and product release remains `release_blocked`:

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`

This plan completes the PRO-02 technical contract only. Fixture behavior is not real-user accuracy, usefulness, adoption or causal policy improvement.

## Deviations from Plan

None - plan executed exactly as written.

## Next Phase Readiness

Phase 27 is **2/4 plans complete**. Plan 27-03 may add append-only user trust controls and reversible scope lifecycle over the immutable candidate/evaluation authority.

## Self-Check: PASSED

- All planned artifacts and three task commits exist.
- Targeted, adjacent, governance and full-repository tests pass.
- Candidate and evaluation persistence remains append-only and source-bound.
- Protected Phase 24, KU/lifecycle, serving and watermark authority remained unchanged.

---
*Phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance*
*Completed: 2026-07-18*
