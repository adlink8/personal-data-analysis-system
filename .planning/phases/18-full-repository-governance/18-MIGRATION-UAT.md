---
phase: 18
plan: "06"
checkpoint: exact-migration-manifest
status: complete
generated: 2026-07-13
---

# Phase 18 Migration UAT

This checkpoint authorizes no physical operation. The executor is dry-run only
until a later, exact cohort approval is recorded.

## Recorded decisions

| Cohort | Decision | Executable operations |
|---|---|---:|
| active-or-source | keep | 0 |
| private-databases | keep | 0 |
| raw-and-imports | keep | 0 |
| derived-reports | deferred | 0 |
| ephemeral-caches | deferred | 0 |
| recycle-quarantine | deferred | 0 |
| shim-cohort-01-leaf-libraries | deferred | 0 |

## Exact preview

- Operations: **0**
- Inverse operations: **0**
- Unauthorized delete operations: **0**
- Actions executed: **0**
- Shadow verification: expected PASS with an empty physical delta.
- Existing dirty worktree paths are preserved. Any future source/target overlap
  is marked `blocked-dirty-overlap` and fails closed.

The local machine-readable preview is
`integration/runtime/governance/migration_preview.json`. It contains only the
cohort decisions and zero path-level operations, so no private leaf path is
copied into this tracked checkpoint.

## Future approval contract

A deferred cohort needs a new exact path-level manifest, prerequisites from
`18-ARCHIVE-UAT.md`, prestate checks, inverse operations, and a separate human
approval. Approval of this document does not approve `--apply`, move, delete,
archive, shim retirement, or rollback. Phase 18 closeout remains pending.

## Approval result

**Approved 2026-07-13:** empty manifest only (`operations=0`). Proceed with verification and closeout. All deferred cohorts require a new exact manifest and separate approval.
