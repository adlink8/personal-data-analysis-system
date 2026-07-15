---
phase: 18
plan: "03"
checkpoint: human-verify
status: deferred
generated: 2026-07-13
---

# Shim retirement cohort preview

No shim has been moved, deleted or disabled. This document is a non-destructive
approval preview only.

## Baseline and parity evidence

- 86 root compatibility shims discovered; budget remains baseline-only-down.
- 86/86 targets exist and each wrapper statically delegates to the declared
  target through `import_module`.
- 22 `_tools` scripts registered; no count drift.
- Two non-standard entrypoints are registered separately.

## Cohort proposed for later approval

`shim-cohort-01-leaf-libraries`:

- `integration/scripts/chroma_client.py` → `core.chroma_client`
- `integration/scripts/common.py` → `core.common`
- `integration/scripts/memory_governance.py` → `core.memory_governance`
- `integration/scripts/project_paths.py` → `core.project_paths`
- `integration/scripts/rules.py` → `core.rules`

## Approval conditions not yet satisfied

1. Measure or prove consumer count is zero for every member.
2. Run consumer-level old/new import and CLI parity where a CLI exists.
3. Prepare and approve a concrete rollback manifest.
4. Obtain human approval for this exact cohort.

Until all four conditions pass, cohort status remains
`pending-human-approval`; the shim budget checker must reject additions but
must not remove existing wrappers.

## User decision

**2026-07-13: DEFERRED.** No shim retirement is authorized. Keep all 86 wrappers; continue consumer measurement and parity evidence. Shim budget remains baseline-only-down and additions remain blocked.
