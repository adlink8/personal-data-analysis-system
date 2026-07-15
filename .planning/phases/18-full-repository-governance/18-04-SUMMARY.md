---
phase: 18
plan: "04"
subsystem: repository-governance
tags: [privacy, retention, artifacts, storage, lifecycle]
requires: [18-01, 18-02]
provides:
  - fail-closed R1-R4 privacy policy
  - zone/kind retention and deletion-lineage policy
  - metadata-only artifact and storage audit
  - non-executable archive/disposal preview
affects: [18-05, 18-06]
requirements-completed: [GOV-02, GOV-03, GOV-07, GOV-11, GOV-12]
status: code_complete_human_checkpoint_open
completed: 2026-07-13
---

# Phase 18 Plan 04: Data and Artifact Lifecycle Governance

Privacy, retention, storage budgets, sidecars, backup/restore expectations, and
deletion lineage are now governed by machine-readable policies. The artifact audit
uses only the Phase 18 filesystem metadata inventory and cannot execute physical
disposition actions.

## Delivery

- Added `governance/policies/privacy.yaml` with fail-closed R1-R4 rules. R3/R4
  cannot be tracked or packaged; tracked reports are aggregate-only.
- Added `governance/policies/retention.yaml` covering every logical zone plus
  generated/runtime kinds, WAL/SHM/backup inheritance, restore requirements, and
  raw-to-archive deletion propagation evidence.
- Added `governance/baselines/storage_budgets.yaml`; exceeding a budget reports a
  finding and never triggers deletion.
- Added `integration/scripts/governance/audit_artifacts.py`. It classifies authority,
  rebuildability, sidecars, orphan status, storage use, and approval cohorts without
  opening artifact bodies.
- Generated ignored local reports:
  `integration/runtime/governance/artifact_audit.json` and
  `integration/runtime/governance/archive_disposal_preview.json`.
- Added `18-ARCHIVE-UAT.md`; all cohort decisions remain pending.

## Metadata-only baseline

- Total governed file bytes: 6,116,761,942 B; 10 GiB budget not exceeded.
- Archive: 4,462,287,605 B; 6 GiB budget not exceeded.
- Data: 1,314,439,844 B; 3 GiB budget not exceeded.
- Var: 327,348,554 B; 6 GiB budget not exceeded.
- Privacy policy violations: 0.
- Orphaned nodes: 0.
- Sidecar nodes: 74.
- Authoritative mutable private-store files: 54.
- Derived files with rebuildability/run-manifest evidence still unverified: 237.
- Oversized generated files: 0.
- Actions executed: 0; private content opened: false.

## Verification

```text
python -m pytest -q tests/test_governance_privacy.py tests/test_governance_artifacts.py
PASS — 6 passed

python integration/scripts/governance/audit_artifacts.py --check --no-content
PASS — metadata-only; privacy violations=0; over-budget=[]; actions=0
```

## Human checkpoint

The following cohorts require explicit per-cohort decisions in `18-ARCHIVE-UAT.md`:

- `active-or-source`: keep (1,265 nodes)
- `derived-reports`: archive candidate (238 nodes; rebuildability evidence required)
- `ephemeral-caches`: delete-candidate (41 nodes; process/lock check required)
- `private-databases`: keep (3 preview nodes; backup/restore evidence required)
- `raw-and-imports`: keep (1,156 nodes)
- `recycle-quarantine`: archive candidate (13,419 nodes; backup and rollback required)

No approval is inferred from plan execution. No move/delete/rewrite command exists
in the audit tool; physical work remains gated to Plan 18-06.

## Deviation

Direct CLI execution initially lacked the repository package on `sys.path`. A
local-module import fallback was added, then the exact planned command passed.

