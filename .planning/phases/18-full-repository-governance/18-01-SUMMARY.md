---
phase: 18
plan: "01"
subsystem: repository-governance
tags: [governance, inventory, privacy, metadata, policy]
requires: []
provides:
  - ordered fail-closed path policy
  - metadata-only complete-tree inventory
  - aggregate-only governance drift baseline
affects: [18-02, 18-03, 18-04, 18-05, 18-06]
tech-stack:
  added: []
  patterns: [ordered-policy-inheritance, metadata-only-private-scan, aggregate-publication]
key-files:
  created:
    - governance/schema/file_inventory.schema.json
    - governance/policies/paths.yaml
    - governance/baselines/inventory_summary.json
    - integration/scripts/governance/build_project_inventory.py
    - integration/scripts/governance/render_governance_report.py
    - tests/test_governance_inventory.py
    - tests/test_governance_report.py
  modified:
    - .gitignore
key-decisions:
  - "R3/R4 inventory uses filesystem metadata only; no content hash or body read."
  - "Privacy-deny wins before numeric priority and specificity; equal precedence fails closed."
  - "Git internals record only the .git exclusion root; other excluded zones retain descendant counts and depth."
requirements-completed: [GOV-01, GOV-02, GOV-03, GOV-07]
duration: 24 min
completed: 2026-07-13
---

# Phase 18 Plan 01: Governance Policy Engine and Complete Inventory Summary

Ordered path governance now classifies every repository node while a metadata-only scanner inventories private and excluded descendants without opening their content.

## Delivery

- Defined the inventory JSON Schema, metadata applicability matrix, ordered policy rules, privacy classes, Git policy, lifecycle and lineage fields.
- Added a fail-closed policy resolver: privacy deny → priority → specificity; ambiguity, case collisions and unclassified paths are errors.
- Added a non-following filesystem scanner for files, directories, empty directories, symlinks and Windows reparse points.
- `.git` descendants are not enumerated; `_recycle`, data, runtime and other excluded/private zones are enumerated only through `os.scandir`/`stat` metadata.
- Added an aggregate renderer whose tracked baseline contains counts only—no node list, leaf paths, private body, reversible summaries or content hashes.
- Added narrow `.gitignore` allowlists for the tracked schema and aggregate baseline. The private expanded inventory remains ignored.

## Verified Baseline

The final repository scan reported:

- 16,072 total governed nodes
- 11,438 files and 4,634 directories
- maximum depth 18
- 14,879 excluded/private descendant nodes represented by metadata
- file/directory policy coverage 100%
- metadata completeness 100%
- generated inventory-lineage field completeness 100%
- 0 paths or private content emitted by the sanitized report

The host did not permit creation of a real directory symlink without elevation, so that integration fixture skipped. A deterministic reparse-point fixture still verified classification without target traversal.

## Verification

```text
python integration/scripts/governance/build_project_inventory.py --check --private-output integration/runtime/governance/file_inventory.json
PASS — schema validated, coverage/completeness 100%

python integration/scripts/governance/render_governance_report.py --inventory integration/runtime/governance/file_inventory.json --output governance/baselines/inventory_summary.json
PASS — aggregate-only baseline rendered

python -m pytest -q tests/test_governance_inventory.py tests/test_governance_report.py
PASS — 9 passed, 1 skipped (host symlink privilege); reparse synthetic fixture passed
```

## Deviations from Plan

**[Rule 3 - Missing critical configuration] Track governance JSON contracts** — `.gitignore` globally ignored JSON, including the required schema and aggregate baseline. Added two exact allowlist entries; private inventory remains ignored.

**Total deviations:** 1 auto-fixed configuration gap. **Impact:** required source-controlled governance contracts are visible to Git without broadening exposure of other JSON/private artifacts.

## Issues Encountered

- Real symlink creation is unavailable on this Windows host; coverage is retained through a synthetic reparse fixture and non-following scanner implementation.
- No files were moved, deleted, archived, committed, or written to production databases.

## Next

Ready for Plan 18-02 module ownership and target architecture documentation.
