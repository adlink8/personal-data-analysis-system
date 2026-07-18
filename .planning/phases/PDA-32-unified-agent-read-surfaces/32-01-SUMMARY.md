---
phase: 32-unified-agent-read-surfaces
plan: 01
subsystem: service
tags: [sqlite, checksum, lineage, privacy, decision-intelligence]
requires:
  - phase: 28-31
    provides: immutable External, Analysis, Pilot and Calibration authorities
provides:
  - Checksum-verifying AnalysisReadService
  - Shared schema-versioned four-authority read dispatch
  - Live zero-mutation acceptance coverage
affects: [phase-32-rest-mcp, phase-33-orchestration]
tech-stack:
  added: []
  patterns: [read-only SQLite, typed envelope, fail-closed checksum graph]
key-files:
  created:
    - src/personal_knowledge/intelligence/analysis/service.py
    - src/personal_knowledge/services/decision_intelligence_reads.py
    - tests/unit/test_agent_read_services.py
    - tests/integration/test_agent_read_authority_integrity.py
  modified: []
key-decisions:
  - "Use one shared dispatch contract while preserving existing authority service functions."
  - "Expose provider receipt metadata/checksums but never raw provider request/response bodies."
patterns-established:
  - "Authority read: mode=ro + query_only + checksum graph validation before success."
requirements-completed: [AGENT-01, AGENT-02, AGENT-03, AGENT-04]
duration: 18min
completed: 2026-07-18
---

# Phase 32 Plan 01: Shared Authority Read Services Summary

**A checksum-verifying AnalysisReadService and one bounded four-authority dispatch now expose External, Analysis, Pilot and Calibration metadata without provider bodies or writes.**

## Performance

- **Duration:** 18 min
- **Tasks:** 3
- **Files modified:** 4

## Accomplishments

- Validates the complete Analysis run/candidate/claim/evidence/receipt/event checksum graph.
- Provides stable list/get/explain envelopes for all four v1.2 authority families.
- Proves eight service/integration cases, including live authority fingerprints and honest calibration boundaries.

## Task Commits

1. **Shared services and normalized authority reads** — `6763427`
2. **Authority integrity and zero-mutation tests** — `aaed277`

## Files Created/Modified

- `src/personal_knowledge/intelligence/analysis/service.py` — fail-closed Analysis read graph.
- `src/personal_knowledge/services/decision_intelligence_reads.py` — shared operation dispatch and typed envelope.
- `tests/unit/test_agent_read_services.py` — service bounds, privacy and tamper tests.
- `tests/integration/test_agent_read_authority_integrity.py` — live four-authority fingerprint proof.

## Decisions Made

- Kept External/Pilot/Calibration legacy functions intact and normalized them through an additive shared service.
- Limited default Analysis list rows to metadata; explicit get/explain adds validated candidate/evidence metadata.

## Deviations from Plan

- Existing External/Pilot/Calibration service files required no mutation; the shared wrapper normalized them without duplicating or destabilizing their APIs.

## Issues Encountered

- Calibration protocol ordering uses `frozen_at`, not `created_at`; corrected before tests.

## User Setup Required

None.

## Next Phase Readiness

Ready for additive REST and stdio MCP adapters in Plan 32-02.

## Self-Check: PASSED

`python -m pytest tests/unit/test_agent_read_services.py tests/integration/test_agent_read_authority_integrity.py -q` → 8 passed.

---
*Phase: 32-unified-agent-read-surfaces*
*Completed: 2026-07-18*
