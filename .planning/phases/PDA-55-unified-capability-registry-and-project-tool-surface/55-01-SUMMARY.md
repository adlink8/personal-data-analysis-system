---
phase: 55
plan: 01
subsystem: capability-registry
tags: [registry, descriptors, governance, deterministic-generation]
requires: [Phase 51 provider/entrypoint baseline]
provides: [project capability registry, strict validator, deterministic REST/MCP/Pi descriptor bundles]
affects: [55-02, Phase 56, Phase 57, Phase 58]
tech-stack:
  added: []
  patterns: [canonical SHA-256 checksums, profile filtering, fail-closed validation]
key-files:
  created:
    - governance/manifests/capabilities/project-capabilities.json
    - governance/schemas/project-capability-registry-v1.schema.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.production.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.operator.json
    - governance/manifests/capabilities/generated/project-capability-descriptors.test.json
    - src/personal_knowledge/services/capability_registry.py
    - tools/supported/generate_capability_descriptors.py
    - tests/contract/test_project_capability_registry.py
  modified: []
key-decisions:
  - "The registry is the single source of truth; consumer descriptors carry its checksum."
  - "The initial surface contains only bounded, provider-free read operations."
requirements-completed: [CAP-01, CAP-02]
duration: 20 min
completed: 2026-08-05
---

# Phase 55 Plan 01: Capability registry and deterministic descriptors

Implemented a strict Project Capability Registry with 18 namespaced read capabilities covering knowledge, retrieval, state, external context, decisions, outcomes, evidence, wiki, data quality and runtime health. Each operation declares profile, privacy, authority, side-effect, timeout, budget, idempotency, confirmation and receipt metadata; registry and operation checksums are validated before load.

## Verification

- `python -m pytest tests/contract/test_project_capability_registry.py -q` — 18 passed.
- `python tools/supported/generate_capability_descriptors.py --check` — passed.
- Generator writes byte-stable production/operator/test bundles and rejects seeded descriptor drift.
- `git diff --check` — passed for plan files.

## Deviations from Plan

None — plan executed as written.

## Self-Check: PASSED

- Implementation commit: `eb09ab7`
- All created key files exist.
- Ready for Phase 55 Plan 02.
