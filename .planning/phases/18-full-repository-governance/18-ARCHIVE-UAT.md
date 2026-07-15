---
phase: 18
plan: "04"
checkpoint: archive-disposal-approval
status: decisions_recorded
generated: 2026-07-13
---

# Phase 18 Archive and Disposal UAT

This checkpoint is a metadata-only review. No file has been moved, archived,
deleted, rewritten, packaged, or opened for content inspection. The local ignored
manifest is `integration/runtime/governance/archive_disposal_preview.json`.

## Safety conditions

- `actions_executed = 0` and `content_opened = false`.
- `_recycle`, raw/import data, and private databases remain in place.
- Approval applies to one named cohort only; it does not authorize other cohorts.
- Any later physical action needs a new path-level manifest, backup/restore evidence,
  journal, post-check, and rollback rehearsal under Plan 18-06.
- “Delete-candidate” is a classification, not deletion authorization.

## Cohorts awaiting decision

| Cohort | Proposed disposition | Nodes | Size | Privacy | Current decision |
|---|---|---:|---:|---|---|
| active-or-source | keep | 1,265 | 60,192,122 B | R1/R2/R4 | **Approved keep** |
| derived-reports | archive | 238 | 68,369,788 B | R3 | **Deferred** |
| ephemeral-caches | delete-candidate | 41 | 260,149 B | R2 | **Deferred** |
| private-databases | keep | 3 | 211,542,016 B | R4 | **Approved keep** |
| raw-and-imports | keep | 1,156 | 1,314,439,844 B | R4 | **Approved keep** |
| recycle-quarantine | archive | 13,419 | 4,461,909,178 B | R4 | **Deferred** |

The cohort table is intentionally aggregate-only. Private leaf paths remain solely
in ignored local metadata and are not copied into planning documentation.

## Required evidence before approval

### active-or-source — keep

- Confirm mixed R4 nodes are retained under their more specific path policies.
- No physical action is proposed.

### derived-reports — archive

- Resolve or explicitly waive the 237-file rebuildability/run-manifest finding.
- Produce target archive location, retention period, owner, and restore rehearsal.

### ephemeral-caches — delete-candidate

- Confirm no active process, lock, or current run depends on each candidate.
- Provide path-level preview and prove deterministic rebuild.

### private-databases — keep

- Produce consistent backup evidence including WAL/SHM state.
- Complete sandbox restore testing before any later migration.

### raw-and-imports — keep

- Confirm owner/legal/user retention basis and deletion-lineage procedure.
- No move or deletion is proposed in Plan 18-04.

### recycle-quarantine — archive

- Inventory duplicate versus unique material without reading private bodies by default.
- Provide encrypted backup, destination capacity, original-path journal, and rollback.

## Approval record

User approval recorded 2026-07-13. “Approved keep” authorizes no physical action. Deferred cohorts remain in place and cannot enter an executable migration manifest without a new explicit approval backed by the required evidence above. No move/delete/archive action is authorized.
