---
phase: 25-personal-state-and-change-intelligence
plan: 01
subsystem: intelligence-storage
tags: [sqlite, immutable-analysis, snapshot-binding, evidence-provenance, privacy]

requires:
  - phase: 23
    provides: Typed D/S/R/A registry and immutable composite serving snapshots
  - phase: 24
    provides: Evidence eligibility, privacy vetoes and lifecycle authority boundaries
provides:
  - Additive immutable A-layer personal-state run/assertion/evidence/change/risk schema
  - Canonical typed assertion and evidence records with stable checksums
  - Snapshot-member-bound dry-run validation and atomic idempotent publication
affects: [25-02-state-projection, 25-03-change-intelligence, 25-04-interfaces, phase-26]

tech-stack:
  added: []
  patterns: [metadata-only evidence refs, canonical JSON identity, fail-closed atomic publication]

key-files:
  created:
    - src/personal_knowledge/intelligence/__init__.py
    - src/personal_knowledge/intelligence/schema.py
    - src/personal_knowledge/intelligence/runs.py
    - tests/unit/test_personal_state_schema.py
    - tests/integration/test_personal_state_runs.py
  modified:
    - src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py

key-decisions:
  - "Personal-state intelligence is immutable A-layer analysis under a.personal_change, never KU or serving authority."
  - "Run identity binds snapshot ID/hash, the full member-version manifest, producer version and canonical input checksum."
  - "Publication remains dry-run unless write=True and commits the complete run in one SQLite transaction."

patterns-established:
  - "Snapshot-bound analysis: resolve one validated snapshot once and revalidate every evidence version against it."
  - "Privacy-safe persistence: retain typed refs, metadata hashes and uncertainty, never unrestricted evidence bodies."

requirements-completed: [INTEL-01, INTEL-02]

duration: 28min
completed: 2026-07-18
---

# Phase 25 Plan 01: Immutable Personal-State Run Foundation Summary

**Immutable A-layer personal-state records with complete serving-snapshot lineage, privacy-fail-closed evidence validation and atomic idempotent publication**

## Performance

- **Duration:** 28 min
- **Started:** 2026-07-17T20:42:05Z
- **Completed:** 2026-07-17T21:10:00Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added five additive SQLite tables with FK constraints, typed provenance, same-run change/risk references, indexes and immutable-row triggers.
- Added frozen canonical records and stable checksum identities for assertions, evidence, snapshot bindings and runs.
- Implemented read-only planning, full run revalidation and explicit-write atomic publication with deterministic replay and rollback fault injection.
- Bound each run to the complete snapshot member-version manifest and rejected registry drift, cross-snapshot refs, private payloads, secret/blocked evidence and post-plan tampering.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add immutable personal-state analysis tables** - `e45e9e1`
2. **Task 2: Implement canonical snapshot-bound run validation and atomic publication** - `6723a30`

## Files Created/Modified

- `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py` - Additive tables, constraints, indexes and immutable triggers.
- `src/personal_knowledge/intelligence/__init__.py` - Public typed run API exports.
- `src/personal_knowledge/intelligence/schema.py` - Frozen records plus canonical JSON/checksum rules.
- `src/personal_knowledge/intelligence/runs.py` - Snapshot resolution, validation, dry-run planning and atomic publication.
- `tests/unit/test_personal_state_schema.py` - Schema idempotence, FK, constraint and immutability coverage.
- `tests/integration/test_personal_state_runs.py` - Identity, privacy, lineage, replay, tamper and rollback coverage.

## Decisions Made

- The new records remain analysis outputs only; no serving role, KU row, lifecycle event, active pointer or watermark is created or changed.
- The canonical input manifest includes the entire resolved snapshot member map so later inactive-snapshot drift also fails closed.
- Requirements INTEL-01/02 have their storage and lineage foundation here; final requirement acceptance remains pending Plans 25-02 through 25-04 and phase verification.

## Deviations from Plan

None - plan scope and authority boundaries were followed exactly.

## Issues Encountered

- The Luna executor hit provider capacity after Task 1. GSD safe-resume detected the committed task and missing summary; Task 2 was completed inline without repeating or rewriting Task 1.
- The first Task 2 test run exposed that lifecycle tables are initialized independently from the base migration. The test fixture now initializes that existing schema before asserting zero lifecycle mutations.

## Verification

- `python -m pytest tests/unit/test_personal_state_schema.py tests/integration/test_serving_snapshot_schema.py -q` — 13 passed.
- `python -m pytest tests/integration/test_personal_state_runs.py tests/contract/test_evidence_resolver.py tests/unit/test_artifact_registry.py -q` — 13 passed.
- Full plan command across all five test modules — 26 passed.
- `python -m py_compile ...` and `git diff --check` — passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Ready for Plan 25-02 deterministic goal/constraint/observation projection.
- Phase 24 real Gold and human quality gates remain release-blocking and were not modified or synthesized.

## Self-Check: PASSED

- All key files exist and both task commits are present.
- All task acceptance criteria and plan-level verification commands passed.
- No active snapshot, KU/lifecycle authority or watermark mutation is performed by the new API.

---
*Phase: 25-personal-state-and-change-intelligence*
*Completed: 2026-07-18*
