---
phase: 30-low-risk-project-decision-pilot
plan: 01
subsystem: decision-intelligence
tags: [sqlite, append-only, checksums, lineage, abstention]
requires:
  - phase: 29-structured-llm-decision-analysis
    provides: admitted evidence-bound project analysis candidate
provides:
  - independent append-only project pilot authority
  - deterministic admitted-option recommendation bridge
  - frozen real Phase 29 candidate and dual-snapshot lineage
affects: [30-02, 30-03, phase-31-calibration]
tech-stack:
  added: []
  patterns: [read-only source validation, fail-closed abstention, fault-atomic publication]
key-files:
  created:
    - src/personal_knowledge/intelligence/pilot/schema.py
    - src/personal_knowledge/intelligence/pilot/cases.py
    - tests/contract/test_project_pilot_cases.py
    - tests/integration/test_project_pilot_authority.py
  modified: []
key-decisions:
  - "Keep a.project_pilot independent from Personal, External and Analysis authorities."
  - "Translate only the explicitly selected admitted option; never promote it to a user decision or action."
patterns-established:
  - "Pilot writes are append-only, checksum-addressed and source-authority preserving."
  - "Any lineage, policy, evidence or active-snapshot drift returns abstain before a pilot write."
requirements-completed: [PDI-07]
duration: 25min
completed: 2026-07-18
---

# Phase 30 Plan 01: Independent Pilot Authority Summary

**An immutable project case now binds the real Phase 29 candidate, its exact dual snapshots and a non-authoritative validate-before-adopt recommendation.**

## Performance

- **Duration:** 25 min
- **Started:** 2026-07-18T12:05:00Z
- **Completed:** 2026-07-18T12:30:00Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added four append-only pilot tables with eight no-update/no-delete triggers, foreign keys, chronology and checksum constraints.
- Validated run, candidate, binding, request, response, claim and evidence lineage read-only before admission.
- Froze real case `ppc_3c81da35094e5260d022f1ef` from run `dar_77843392b266cd0a992cc274` and candidate `dac_8abee23d30d7df2c9df47ab7`.
- Published recommendation `ppr_bbbb25bdeb48c53ea416ad0c` for `opt_validate_then_adopt` with `actions_executed=0` and unchanged Personal, External and Analysis fingerprints.

## Task Commits

1. **Task 1: Establish independent pilot authority** - `5b658d6` (feat)
2. **Task 2: Admit one analysis option as a recommendation candidate** - `4065c77` (test)

## Files Created/Modified

- `src/personal_knowledge/intelligence/pilot/schema.py` - Strict typed contracts and dry-run-first schema migration.
- `src/personal_knowledge/intelligence/pilot/cases.py` - Read-only Phase 29 validation and atomic pilot publication.
- `tests/integration/test_project_pilot_authority.py` - Tamper, retry, drift, atomicity and authority-isolation proof.
- `tests/contract/test_project_pilot_cases.py` - Confirmed-input preservation and abstention contract.

## Decisions Made

- The selected option remains a recommendation candidate until a distinct user decision event exists.
- The original Phase 29 confirmation is preserved, and the Phase 30 case freeze gets a separate confirmation identifier.
- Active Personal and External authority pointers are revalidated at admission time; historical checksum validity alone is insufficient.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- The isolated snapshot-drift fixture initially reused a stable fact identity and invalidated the old snapshot. The fixture was corrected to use a distinct fact identity, then the drift path passed.

## User Setup Required

None - no external service configuration required.

## Verification

- `python -m pytest tests/contract/test_project_pilot_cases.py tests/integration/test_project_pilot_authority.py -q` — 6 passed.
- Live migration — schema applied, integrity `ok`, zero foreign-key violations, eight append-only triggers.
- Live replay — exact case/recommendation checksums published once; source authority fingerprints unchanged.
- `git diff --check` — passed.

## Self-Check: PASSED

- All created key files exist.
- Both task commits exist.
- Plan verification and acceptance criteria pass.
- The real case is reconstructable and contains no final decision or executed action.

## Next Phase Readiness

Plan 30-02 can preregister a metric/window and append user-owned decision/manual-action events. The real action remains intentionally unperformed pending its explicit human-action checkpoint.

---
*Phase: 30-low-risk-project-decision-pilot*
*Completed: 2026-07-18*
