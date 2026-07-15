---
phase: 18
plan: "03"
subsystem: repository-governance
tags: [portability, runtime-config, paths, shims, entrypoints]
requires: [18-01, 18-02]
provides:
  - fail-closed machine-path policy and baseline
  - portable runtime and dependency discovery
  - shim/tool registry and baseline-only-down gate
affects: [18-05, 18-06]
requirements-completed: [GOV-05, GOV-06, GOV-08]
checkpoint-status: pending-human-approval
completed-auto-tasks: 2026-07-13
---

# Phase 18 Plan 03: Source Portability and Compatibility Governance

Production source is free of user/Desktop/fixed-drive literals, runtime
dependencies now resolve through environment/discovery, and the complete legacy
entrypoint surface is registered behind a baseline-only-down gate. The human
shim-retirement checkpoint remains intentionally open.

## Delivery

- Added `governance/baselines/path_hits.yaml`, a policy contract that separates
  production violations from documentation templates, private source locators,
  historical reports, test fixtures and migration tools.
- Added `check_path_policy.py`; every current machine-path hit is classified and
  any production hit fails the gate. Current result: 2 classified documentation
  templates, 0 production violations.
- Added `core/runtime_config.py` for Vertex project/location/model, gcloud token,
  local embedding model and semantic API discovery. Environment variables are
  authoritative; conventional model discovery preserves the existing machine
  without encoding a drive letter.
- Migrated knowledge extraction, production extraction, the LLM probe, local
  embedding, MCP configuration, backfill DB lookup and generated search examples
  away from machine-specific paths.
- Redirected the legacy L1/L2 comparison HTML from Desktop to the governed
  project analysis directory.
- Added `governance/manifests/entrypoints.yaml` and `check_shim_budget.py`.
  Resolution currently covers 86/86 shims, 22/22 tools and two registered
  non-standard entrypoints; all shim targets exist and pass static delegation
  parity.

## Human checkpoint

No shim was moved, deleted, disabled or retired. The proposed five-member leaf
library cohort is documented in `18-03-SHIM-RETIREMENT-PREVIEW.md` and remains
`pending-human-approval` because consumer telemetry and an approved rollback
manifest do not yet exist. This satisfies the non-destructive part of task
18-03-03 only; physical retirement is deferred.

## Verification

```text
python -m pytest -q tests/test_governance_paths.py tests/test_governance_shims.py
PASS — 6 passed

python integration/scripts/governance/check_path_policy.py --check --json
PASS — 2 classified; production_source=0

python integration/scripts/governance/check_shim_budget.py --check --preview --json
PASS — 86 shims; 22 tools; 86/86 target/static parity

python -m pytest -q tests -k 'project_paths or runtime_config or mcp or knowledge'
PASS — 235 selected tests displayed as passed; exit code 0

python -m pytest -q tests/test_governance_inventory.py tests/test_governance_report.py tests/test_governance_architecture.py tests/test_governance_planning.py tests/test_governance_paths.py tests/test_governance_shims.py
PASS — 21 passed, 1 skipped (Windows symlink privilege fixture)

python integration/scripts/governance/build_project_inventory.py --check --private-output integration/runtime/governance/file_inventory.json
PASS — 16,131 nodes; coverage/completeness/lineage 100%; deepest depth 18

python -m py_compile <all changed Python governance/runtime files>
PASS
```

The Python 3.14 filtered test run still printed the repository's pre-existing
native `pyarrow/sklearn` access-violation stack during interpreter shutdown.
All selected tests had completed and the process returned 0; this remains an
environment/test-matrix risk for Plan 18-05.

## Safety

- No production database, active pointer or private body was read or written.
- No file was moved, deleted, archived or committed.
- Existing unrelated dirty-worktree changes were preserved.

## Next

Plan 18-05 can wire `path-policy` and `shim-budget` into CI. Shim cohort 01 must
not proceed until its four approval conditions are independently satisfied.
