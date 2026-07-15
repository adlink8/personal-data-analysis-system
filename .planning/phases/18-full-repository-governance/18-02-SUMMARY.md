---
phase: 18
plan: "02"
subsystem: repository-governance
tags: [architecture, ownership, documentation, planning]
requires: [18-01]
provides:
  - current-path to logical-zone architecture policy
  - stable-module ownership and documentation coverage gate
  - authoritative planning hierarchy and drift checker
affects: [18-03, 18-04, 18-05, 18-06]
requirements-completed: [GOV-03, GOV-04, GOV-10]
completed: 2026-07-13
---

# Phase 18 Plan 02: Target Architecture, Ownership and Documentation Boundaries

Current repository paths now map to enforceable logical zones and dependency
directions without moving any files. Stable human-facing modules have local
ownership contracts, while the Phase 18 inventory continues to govern every leaf.

## Delivery

- Added `governance/policies/architecture.yaml` and a human-readable repository-zone
  contract covering source, tests, assets, docs, governance, data, var, archive and
  planning.
- Registered 20 stable modules in `governance/stable_modules.yaml`, including owner,
  lifecycle status and an expiry checkpoint for `_tools`.
- Added/updated all plan-listed module READMEs with responsibility, boundaries,
  entry points, I/O/privacy, tests and ownership.
- Reduced the root README to quickstart, privacy rules, navigation and governance
  commands; detailed module facts now live beside their implementation.
- Declared `.planning` authoritative and `.gsd` historical/read-only in
  `governance/policies/planning.yaml`.
- Added fail-closed documentation coverage and planning consistency checkers.
- Reconciled ROADMAP's stale plan labels while preserving Phase 17 as executing:
  code is complete, but real gold, judge calibration and sandbox UAT remain open.

## Verification

```text
python -m pytest -q tests/test_governance_architecture.py tests/test_governance_planning.py
PASS — 6 passed

python integration/scripts/governance/check_docs_coverage.py --check
PASS — stable_modules coverage=100%

python integration/scripts/governance/check_planning_consistency.py --check
PASS — .planning authoritative; Phase 17 remains open

python -m pytest -q tests/test_governance_inventory.py tests/test_governance_report.py tests/test_governance_architecture.py tests/test_governance_planning.py
PASS — 15 passed, 1 skipped (Windows symlink privilege fixture)

python integration/scripts/governance/build_project_inventory.py --check --private-output integration/runtime/governance/file_inventory.json
PASS — 16,104 nodes; coverage/completeness/lineage 100%; deepest depth 18
```

## Safety and scope

- No file was moved, deleted, archived or committed.
- No production database, raw source, private evaluation body or active pointer was
  read or changed.
- The expanded inventory remains private/ignored; only governance contracts and
  sanitized documentation are tracked candidates.

## Deviations

The original root README replacement needed a second patch because the combined
delete/add operation left the file absent. It was restored immediately before any
verification; final documentation and inventory gates pass.

## Next

Ready for Plan 18-03 path portability and compatibility-layer governance.

