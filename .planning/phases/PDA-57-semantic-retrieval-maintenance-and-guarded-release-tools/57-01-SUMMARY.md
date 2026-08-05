---
phase: 57
plan: 01
subsystem: semantic-retrieval-maintenance
tags: [candidate, evidence-binding, retrieval-generation, reconcile, evaluation]
requires: [56-02]
provides: [semantic-maintenance-tools, isolated-index-tools, evaluation-gate]
affects: [57-02, Phase 58, Phase 60]
tech-stack:
  added: []
  patterns: [candidate-only-staging, new-generation-build, zero-count-reconcile]
key-files:
  created:
    - src/personal_knowledge/services/semantic_maintenance_tools.py
    - src/personal_knowledge/services/retrieval_maintenance_tools.py
    - tests/integration/test_pi_semantic_maintenance.py
    - tests/integration/test_pi_retrieval_maintenance.py
  modified:
    - src/personal_knowledge/services/warehouse_mutations.py
    - src/personal_knowledge/services/pi_domain_gateway.py
    - governance/manifests/capabilities/project-capabilities.json
    - apps/personal_intelligence_kernel/test/capability-registry.test.mjs
    - governance/manifests/capabilities/generated/project-capability-descriptors.production.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.operator.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.test.json
requirements-completed: [WARE-03, PTOOL-02]
duration: 30 min
completed: 2026-08-05
---

# Phase 57 Plan 01: Semantic and retrieval maintenance Tools

Added evidence/model/schema-bound semantic maintenance operations for L1/L2
extraction, repair, conflict detection and backfill. They produce only bounded
Candidate records and require exact source scope, snapshot/watermark, evidence
references, extractor receipt and model receipt. Promotion, lifecycle,
canonical, serving and active-pointer-shaped inputs fail closed.

Added isolated retrieval generation, reconcile and evaluation operations. Index
build derives a deterministic new generation and never changes the active
generation. Reconcile reports missing/orphan/duplicate counts; evaluation is
blocked unless all three are zero and returns a deterministic policy evidence
checksum. The shared Phase 56 ledger provides idempotent build receipts.

## Verification

- `python -m pytest tests/integration/test_pi_semantic_maintenance.py tests/integration/test_pi_retrieval_maintenance.py -q` — 4 passed.
- `python -m pytest tests/integration/test_pi_warehouse_mutations.py tests/e2e/test_pi_warehouse_recovery.py tests/integration/test_pi_capability_tools.py tests/contract/test_project_capability_registry.py -q` — 33 passed.
- `python tools/supported/generate_capability_descriptors.py --write` — passed.
- `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=capability-registry` — 47 passed.
- `python -m compileall -q src/personal_knowledge/services/semantic_maintenance_tools.py src/personal_knowledge/services/retrieval_maintenance_tools.py src/personal_knowledge/services/pi_domain_gateway.py` — passed.

## Deviations from Plan

- [Rule 1 - Isolated fixture adapters] Automated tests use temporary ledger and
  in-memory candidate/generation stores. Existing live extraction/index scripts
  are not invoked, so no provider call, canonical mutation or active pointer
  change occurs.

**Total deviations:** 1 intentional safety boundary. **Impact:** Tool contracts
and gates are verified before any live pipeline authority is connected.

## Self-Check: PASSED

- Implementation commit: 2c98f4c
- Active semantic inventory and active retrieval generation remain unchanged.
- Ready for Phase 57 Plan 02.
