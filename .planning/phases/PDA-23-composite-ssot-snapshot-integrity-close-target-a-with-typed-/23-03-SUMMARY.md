---
phase: 23
plan: 03
subsystem: retrieval-and-evidence
tags: [serving-snapshot, evidence, privacy, fallback]
requires: [23-01, 23-02]
provides: [snapshot-aware shared retrieval, typed evidence drilldown]
affects: [23-04, REST, MCP, CLI]
tech-stack:
  added: []
  patterns: [resolve-snapshot-once, typed-evidence-adapters]
key-files:
  created:
    - src/personal_knowledge/retrieval/serving.py
    - src/personal_knowledge/retrieval/evidence.py
    - tests/contract/test_evidence_resolver.py
    - tests/contract/test_serving_snapshot_retrieval.py
  modified:
    - src/personal_knowledge/retrieval/semantic_search.py
key-decisions:
  - Snapshot-backed product reads skip unbound fallback layers with explicit reasons.
  - REST/MCP gain snapshot and evidence metadata through their existing shared backend; no duplicate delivery implementation was added.
requirements-completed: [FOUND-03, FOUND-05]
duration: 20 min
completed: 2026-07-17
---

# Phase 23 Plan 03: Snapshot Retrieval and Evidence Summary

Bound layered retrieval to one resolved serving snapshot and added a typed, privacy-aware evidence resolver for KU, canonical messages, Turns and Google signals.

## Tasks Completed

1. Added typed evidence adapters with metadata-only defaults, eligibility checks and explicit missing/ineligible/unknown semantics — commit `e04ae6b`.
2. Added serving authority resolution, pointer drift detection, per-layer versions, snapshot-consistency metadata, safe skipping of unbound layers and shared evidence drilldown — commit `0a0959a`.

## Verification

- Evidence, snapshot retrieval and legacy knowledge-search contracts: 26 passed.
- Combined evidence/snapshot/search/apps contract run: 31 passed.
- Compile and diff checks passed.
- Python 3.14 emitted a known third-party pyarrow/sklearn shutdown access-violation trace after pytest reported success; pytest process exit remained 0. Python 3.12 is installed but has no pytest environment, so full validation remains on the configured environment.

## Deviations from Plan

**[Rule 1 - Compatibility]** Retained the pre-snapshot `_read_knowledge_active_collection` hook so legacy installations and existing contract monkeypatches continue to work. Snapshot-backed reads still use SQLite authority. Commit: `0a0959a`.

**Total deviations:** 1 auto-fixed. **Impact:** backwards compatibility without weakening snapshot enforcement.

## Issues Encountered

No product test failures remain. The Python 3.14 third-party shutdown trace is environment debt and does not change test exit status.

## Self-Check: PASSED

All required artifacts exist and snapshot/evidence contract assertions pass.

## Next Phase Readiness

Ready for 23-04 source versions, product sync, doctor and governance enforcement.
