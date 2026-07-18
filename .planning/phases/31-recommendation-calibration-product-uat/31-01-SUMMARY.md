---
phase: 31-recommendation-calibration-product-uat
plan: 01
subsystem: decision-intelligence
tags: [calibration, preregistration, cohort, sqlite, immutable]
requires:
  - phase: 30-low-risk-project-decision-pilot
    provides: real case and completed outcome stream
provides: [independent calibration authority, frozen paired protocol, exact cohort lineage]
affects: [31-02, 31-03]
tech-stack:
  added: []
  patterns: [preregister-before-request, separate metrics, honest minimum evidence]
key-files:
  created: [src/personal_knowledge/intelligence/calibration/schema.py, src/personal_knowledge/intelligence/calibration/protocols.py, tests/unit/test_calibration_protocols.py, tests/integration/test_calibration_authority.py]
  modified: []
key-decisions:
  - "Minimum evidence is 2 while the real cohort is 1, so the final verdict must remain INCONCLUSIVE."
patterns-established:
  - "Protocol, cohort, generation parity, thresholds and failure rules freeze before arm requests."
requirements-completed: [PDI-08]
duration: 14min
completed: 2026-07-18
---

# Phase 31 Plan 01: Immutable Calibration Protocol Summary

**A real protocol now freezes one Phase 30 cohort member, equal GPT-5.4 arm controls, ten separate metrics and mandatory small-sample inconclusiveness.**

## Performance

- **Duration:** 14 min
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added seven append-only calibration tables and fourteen mutation-blocking triggers.
- Frozen protocol `calp_2dc7078cfc7fec88a75826b0` / checksum `2dc7078cfc7fec88a75826b0ceb593bb99d62fdecc8fed96edbdbb22d3ec44e0`.
- Bound exact Phase 30 case and outcome checksums before either arm request.
- Declared minimum evidence 2 against real cohort size 1, preventing a fitted PASS.

## Task Commits

1. **Create append-only calibration schema** - `d5cbca2`
2. **Validate preregistered protocol** - `69c5979`

## Deviations from Plan

None - plan executed exactly as written.

## Verification

- Protocol/authority suite: 7 passed.
- Live schema: integrity `ok`, FK violations `0`, triggers `14`.
- Live protocol and cohort freeze completed before paired requests.

## Self-Check: PASSED

The protocol is immutable, reproducible and cannot produce PASS from the current sample size.

## Next Phase Readiness

Ready for exactly two bounded ChatGPT/Codex GPT-5.4 arm calls under the frozen checksum.
