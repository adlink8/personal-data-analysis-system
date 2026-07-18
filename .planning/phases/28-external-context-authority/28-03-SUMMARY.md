---
phase: 28
plan: 03
status: complete
completed_at: 2026-07-18T18:15:00+08:00
requirements: [PDI-03, PDI-04]
requirements-completed: [PDI-03, PDI-04]
---

# Phase 28 Plan 03 Summary

## Delivered

- Added independent append-only External Snapshot, member, watermark, authority
  history and event tables; no role was added to personal serving authority.
- Implemented dry-run prepare, exact validate, activate, rollback and
  forward-restore with immutable manifests and fault-injection rollback.
- Added metadata-only read service for active snapshot and bound facts.
- Added typed DecisionContextBinding with exact Personal and External snapshot
  ID/hash plus region, freshness and conflict policy.
- Revalidates both authorities on create/read; drift, expired facts, non-current
  lifecycle, unresolved conflict, region mismatch and stale source watermark
  all fail closed.

## Review fixes

- Removed an invalid uniqueness constraint that prevented one immutable source
  watermark/run from being reused by later snapshots.
- Freshness now uses the oldest bound source watermark, so a fresh source cannot
  hide another stale source.
- Snapshot validation now compares valid_from/valid_to and uses the lifecycle
  event projection as current authority instead of the immutable creation state.

## Verification

- Phase 28 adjacent registry/ingest/snapshot/binding suite: 44 passed.
- All SQLite reads use mode=ro/query_only; no Personal/External cross-write.
- Fault injection preserves authority/event counts at every switch boundary.
- No network, LLM or live `var/db` write occurred.
