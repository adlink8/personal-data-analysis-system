---
phase: 23
plan: 04
subsystem: product-sync-and-governance
tags: [artifact-versions, watermarks, doctor, preflight, serving-operations]
requires: [23-02, 23-03]
provides: [versioned product sync, composite integrity gate, safe snapshot operations]
affects: [24, pk-sync, pk-ku, retrieval]
tech-stack:
  added: []
  patterns: [dry-run-first-publication, immutable-version-watermark, sqlite-authority-projection]
key-files:
  created:
    - src/personal_knowledge/application/serving/versions.py
    - tests/unit/test_product_sync_versions.py
    - tests/governance/test_artifact_layer_policy.py
  modified:
    - src/personal_knowledge/application/sync.py
    - src/personal_knowledge/application/serving/snapshots.py
    - src/personal_knowledge/application/knowledge/doctor_ku.py
    - src/personal_knowledge/governance/preflight.py
    - docs/runbooks/product-sync.md
key-decisions:
  - Product publication metadata is append-only, version-bound and never activates a snapshot implicitly.
  - Live current-state bootstrap requires all ten proofs and remains draft-only until separate validation and activation.
  - SQLite serving authority wins; the text pointer is a repairable compatibility projection.
requirements-completed: [FOUND-01, FOUND-02, FOUND-03, FOUND-04, FOUND-05]
duration: 90 min
completed: 2026-07-17
---

# Phase 23 Plan 04: Product Versions and Composite Integrity Summary

Productized Conversation, Turn, Google and KU publication versions/watermarks, added safe composite snapshot operations, and made Doctor/Preflight fail closed on registry, member, pointer, evidence or watermark drift.

## Tasks Completed

1. Added immutable, idempotent artifact publication and watermark recording; extended `pk-sync` with dry-run-first `turns`, `google` and JSON `status`; bound successful KU activation to canonical/index publication metadata — commit `7642890`.
2. Added complete current-state bootstrap, validate/activate/rollback/projection-repair operations; enforced registry, manifest/member, Chroma count/checksum, evidence and watermark checks in Doctor and governance — commit `bc1bb08`.
3. Documented exact bootstrap, activation, rollback, recovery and failure semantics — commit `bd6a70e`.

## Live Target A Evidence

- Migrated the live unified DB idempotently to the Phase 23 serving schema.
- Discovered and bound all 10 required roles in validated snapshot `ss_1590353394c948b908a5d675`.
- Active knowledge collection remained `knowledge_units_ir_4cd8af4ad_20260716020508`; compatibility pointer projection succeeded.
- Doctor: `ok=true`, `critical_fail=0`; knowledge count/checksum `32184 / 599280…`; Turn count/checksum `3601 / f52959…`; source watermarks current and version-bound.
- `pk-sync status --json`: `ok=true`, `drift=[]` across Conversation, Turn, Google and KU.

## Verification

- Plan-specific product sync, Doctor, snapshot, governance and KU CLI suites: 58 passed.
- Full repository: all tests passed, 2 skipped; only two pre-existing invalid-escape SyntaxWarnings remain.
- `python -m personal_knowledge.governance.preflight --ci`: all 13 gates passed, including `artifact-layer-registry`.
- `git diff --check`: clean.

## Deviations from Plan

**[Rule 2 - Missing operation surface]** Added an explicit snapshot CLI (`status`, `bootstrap`, `validate`, `activate`, `rollback`, `repair-pointer`) so the runbook commands are executable rather than tribal Python snippets.

**[Rule 1 - Path correctness]** Corrected the Turn summary source from the retired `integration/analysis` path to the Phase 20 `AI_CONTEXT_DIR` authority.

**[Rule 1 - Test isolation]** Preserved the retrieval authority injection hook so contract tests do not inherit the machine's live snapshot; production still resolves and enforces the same SQLite authority.

**Total deviations:** 3 auto-fixed. **Impact:** required operations became reproducible, the current physical layout is authoritative, and live state no longer contaminates isolated contracts.

## Issues Encountered

Python 3.14 can emit a third-party pyarrow/sklearn shutdown access-violation trace in narrow retrieval runs while still exiting 0. The final full repository run completed normally with exit 0.

## Self-Check: PASSED

All plan artifacts exist, all FOUND-01..05 gates have direct code/test/live evidence, and the active composite authority passes Doctor and Preflight.

## Next Phase Readiness

Phase 23 and Target A are complete. Ready to plan Phase 24 evaluation closure and lifecycle adoption against the active serving snapshot.
