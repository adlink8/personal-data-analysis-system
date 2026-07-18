---
phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance
plan: 03
subsystem: proactive-user-trust-controls
tags: [trust, append-only, controls, rollback, concurrency, sqlite]
requires:
  - phase: 27-01
    provides: Immutable proactive run authority and control-frontier binding
  - phase: 27-02
    provides: Privacy-first proactive ranking and noise governance
provides:
  - User-owned append-only correction, limit, suppression, snooze, revocation and feedback overlays
  - Deterministic exact/domain/policy/global scope projection with compensating restore
  - BEGIN IMMEDIATE sequence, idempotency, tamper and rollback guarantees
  - Exact active-control frontier binding for all future proactive runs
affects: [27-04]
tech-stack:
  added: []
  patterns: [checksum-linked-event-stream, optimistic-sequence, compensating-event, trust-veto-first]
key-files:
  created:
    - src/personal_knowledge/intelligence/proactive/controls.py
    - tests/unit/test_proactive_controls.py
    - tests/integration/test_proactive_concurrency.py
  modified:
    - src/personal_knowledge/intelligence/proactive/runs.py
    - tests/contract/test_proactive_boundaries.py
    - tests/integration/test_proactive_runs.py
key-decisions:
  - "Trust denials are projected before ranking eligibility and cannot be overridden by critical importance."
  - "Restore is a checksum-bound compensating event; it never erases or mutates the original control."
  - "Canonical correction remains canonical_correction_requested and cannot bypass Phase 24 lifecycle review."
requirements-completed: [TRUST-01]
completed: 2026-07-18
release_status: release_blocked
---

# Phase 27 Plan 03: User Trust Controls Summary

**Reversible user-owned trust overlays with immutable history, deterministic precedence and future-run frontier binding**

## Accomplishments

- Added the closed `limit_scope`, `suppress`, `snooze`, `revoke`, `correct`, `mark_not_useful`, `mark_wrong_timing` and `restore` vocabulary. Every append requires actor class `user`, a 64-character user identity hash, exact target authority/type/ID/checksum, explicit scope, expected sequence and idempotency key.
- Added checksum-linked immutable streams under `BEGIN IMMEDIATE`. Exact replay converges, changed-payload idempotency fails, concurrent stale writers fail, and injected faults leave the event frontier unchanged.
- Added deterministic exact-target, domain, policy and global projection. Explicit denial is fail-closed, snooze/expiry uses timezone-aware `as_of`, limit scope is allowlist-based and trust veto executes before critical-budget handling.
- Added compensating restore with `rollback_of_event_id` plus immutable before/after projected checksums. Hydration verifies every row payload, sequence, previous checksum and projected receipt; double restore and semantic tamper fail closed.
- Bound every new proactive run to the exact active-control frontier and revalidated it before publication. Frontier drift rejects the stale run; restored controls affect future projection only and never rewrite prior candidates, evaluations or runs.
- Kept corrections metadata-only. `correct` emits `canonical_correction_requested`; it does not modify Phase 25/26 records, canonical KU, lifecycle manifests/events, serving authority, pointer or watermarks.

## Task Commits

1. **Task 1: Append-only user trust control streams** — `68ab544`
2. **Task 2: Projection, expiry and compensating restore hardening** — `29b7170`
3. **Task 3: Active-control frontier and future-run binding** — `e82093e`

Task 1 preserved the required test-first evidence: the initial focused run failed at collection because `personal_knowledge.intelligence.proactive.controls` did not exist; the minimal implementation made the same focused suite pass.

## Verification

- Phase 27-01..03 targeted suite: **70 passed**.
- Phase 25/26 adjacent decision/lifecycle regression: **38 passed**.
- Governance preflight: **13/13 PASS**.
- Full repository: **862 passed, 2 skipped**; only two pre-existing `SyntaxWarning` messages.
- `git diff --check`: PASS.

All control writes occurred only in disposable SQLite fixtures. No live migration/write, lifecycle apply, serving snapshot/pointer/watermark mutation, network call, paid call, notification or external action occurred.

## Preserved Release Boundary

Phase 24 remains unchanged and product release remains `release_blocked`:

- `24-02-CHECKPOINT`: `awaiting_human`
- `24-03-CHECKPOINT`: `human_verification_required`
- `24-04-CHECKPOINT`: `blocked_on_human_and_quality_gates`

This plan completes the TRUST-01 technical contract only. It does not fabricate a human control, approve canonical lifecycle changes or claim Target D product release.

## Deviations from Plan

None - plan executed within the specified append-only, local-only and no-external-action boundary.

## Next Phase Readiness

Phase 27 is **3/4 plans complete**. Plan 27-04 may expose shared read-only interfaces, a guarded local user-control path and Target D dual-verdict acceptance while preserving the Phase 24 release block.

## Self-Check: PASSED

- All three task commits and planned artifacts exist.
- RED, targeted, adjacent, governance and full-repository verification evidence is recorded.
- User-owned untracked files remain untouched.
- Phase 24, KU/lifecycle, serving and watermark authority remained unchanged.

---
*Phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance*
*Completed: 2026-07-18*
