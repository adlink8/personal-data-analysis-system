---
phase: 56
plan: 01
subsystem: warehouse-read-tools
tags: [warehouse, bounded-read, containment, capability-registry]
requires: [55-02]
provides: [warehouse-read-facade, fixed-adapter-boundary, warehouse-containment-tests]
affects: [56-02, Phase 57, Phase 59]
tech-stack:
  added: []
  patterns: [logical-authority-ids, metadata-only-envelope, preflight-before-adapter]
key-files:
  created:
    - src/personal_knowledge/services/warehouse_tools.py
    - tests/contract/test_pi_warehouse_read_tools.py
    - tests/security/test_pi_warehouse_tool_containment.py
  modified:
    - governance/manifests/capabilities/project-capabilities.json
    - governance/schemas/project-capability-registry-v1.schema.json
    - src/personal_knowledge/services/capability_registry.py
    - src/personal_knowledge/services/pi_domain_gateway.py
    - governance/manifests/capabilities/generated/project-capability-descriptors.production.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.operator.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.test.json
requirements-completed: [WARE-01, SEC-03]
duration: 25 min
completed: 2026-08-05
---

# Phase 56 Plan 01: Warehouse inspection and containment Tools

Added six production-profile `warehouse.*` read capabilities backed by a
Python facade that accepts only logical authority IDs, bounded dates/filters
and limits from 1 to 100. Fixed adapters return counts, checks, stable IDs,
artifact references and receipts; raw bodies, credentials, absolute paths, SQL,
callables and arbitrary database handles never cross the Pi boundary.

The preflight path rejects SQL fragments, path-shaped values, unknown
authorities, invalid enums and oversized requests before the adapter probe is
opened. Security fixtures run only against temporary files and prove canonical,
watermark and active-pointer fingerprints remain unchanged.

## Verification

- `python -m pytest tests/contract/test_pi_warehouse_read_tools.py tests/security/test_pi_warehouse_tool_containment.py -q` — 10 passed.
- `python -m pytest tests/contract/test_project_capability_registry.py tests/integration/test_pi_capability_tools.py tests/contract/test_pi_provider_adapter.py -q` — passed.
- `python tools/supported/generate_capability_descriptors.py --check` — passed.
- `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=capability-registry` — 47 passed.

## Deviations from Plan

- [Rule 1 - Registry coordination] The capability registry schema and generated
  descriptors were extended with the Phase 56 mutation declarations so the
  following plan can use the same checksum-bound SSOT. No mutation is executed
  by this plan; its transaction implementation remains in 56-02.
- [Rule 1 - Compatibility] The existing registry parity test now supplies the
  required logical authority for warehouse reads and the Kernel registry count
  reflects the expanded approved project surface.

**Total deviations:** 2 auto-fixed. **Impact:** read-only boundary is stricter;
no live database or provider authority was enabled.

## Self-Check: PASSED

- Implementation commit: c4684cb
- Security fixtures are temporary-only and do not touch live `var/db` paths.
- Ready for Phase 56 Plan 02.
