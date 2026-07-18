---
phase: 28
plan: 01
status: complete
completed_at: 2026-07-18T16:20:00+08:00
requirements: [PDI-01, PDI-02, PDI-04]
requirements-completed: [PDI-01]
---

# Phase 28 Plan 01 Summary

## Delivered

- Added independent `var/db/external_context.sqlite`; it is not the personal
  unified DB and is not a required role in the personal serving authority.
- Added a tracked two-source `project/technology` allowlist for official Python
  and Node.js release metadata with exact source/type/region/hostname policy,
  provenance, license, four time policies and stable definition checksum.
- Registered `d.external_source_registry`, `d.external_observation` and
  `s.external_fact` as independent R1 D/S artifacts.
- Added strict frozen contracts and an append-only six-table schema with FK,
  checksums, time/lifecycle/confidence checks and UPDATE/DELETE rejection.
- Added dry-run-by-default, explicit `--write`, transactional and idempotent
  migration plus metadata-only source list/get/schema-status CLI/service.

## Verification

- External registry/schema/interface plus artifact policy suite: 18 passed.
- Governance preflight: 13/13 PASS.
- Dry-run does not create or change a DB; write migration is idempotent.
- SQLite integrity is `ok`, FK violations are zero, all authority tables reject
  UPDATE/DELETE, and dangling/duplicate/invalid-confidence writes fail closed.

## Deferred to later plans

Network/file ingest, lifecycle projection on a real cohort, snapshots,
REST/MCP and dual-snapshot binding remain in 28-02/03/04. No source content was
fetched and no live external authority was activated.
