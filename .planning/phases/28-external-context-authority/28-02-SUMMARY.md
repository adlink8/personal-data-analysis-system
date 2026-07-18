---
phase: 28
plan: 02
status: complete
completed_at: 2026-07-18T17:25:00+08:00
requirements: [PDI-01, PDI-02]
requirements-completed: []
---

# Phase 28 Plan 02 Summary

## Delivered

- Added file-first bounded JSON manifest loading and atomic cohort publication
  for the two exact allowlisted source definitions.
- Bound every import to schema version, source definition checksum, quality
  policy version, UTC observation/ingestion/publication/valid times and region.
- Published canonical Observation, Fact and Support rows in one transaction,
  with deterministic IDs, checksums, exact replay no-op and fault rollback.
- Added append-only lifecycle event chaining and deterministic projection for
  current, stale, superseded, conflict and invalid states.
- Added overlapping-value conflict detection that appends conflict events to
  both facts without updating or deleting authoritative history.
- Rejected raw/body-like fields, secret-like fields or values, unbounded text,
  unsupported region/time and unresolved observation provenance before write.
- Kept the implementation file-only and local: no HTTP client, crawler, LLM,
  personal-authority write, live database write or snapshot activation.

## Verification

- `test_external_context_runs.py` + `test_external_context_privacy.py`: 21 passed.
- Registry/schema/interface and 28-02 adjacent suite: 33 passed.
- Governance preflight: 13/13 PASS.
- Explicit tests prove replay no-op, checksum/registry rejection, two injected
  transaction faults with unchanged authority fingerprint, stale/conflict event
  projection, privacy rejection and lifecycle checksum tamper detection.

## Deferred to later plans

External Snapshot/Watermark activation, public query/explain service,
DecisionContext dual binding, Doctor and E2E acceptance remain in 28-03/04.
PDI-02 therefore remains milestone-incomplete until those user-facing query and
explanation surfaces are verified.
