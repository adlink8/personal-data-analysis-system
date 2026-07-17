---
phase: 24
plan: 01
subsystem: evaluation-and-retrieval
tags: [evidence-support, abstention, snapshot-binding, privacy, calibration]
requires: [23-04]
provides: [typed evidence support decisions, snapshot-bound evaluation manifests, private development calibration]
affects: [24-02, 24-04, product retrieval, evaluation gate]
tech-stack:
  added: []
  patterns: [three-state-evidence-support, explicit-evidence-condition, immutable-serving-binding]
key-files:
  created:
    - src/personal_knowledge/retrieval/relevance.py
    - tests/unit/test_evidence_support.py
  modified:
    - src/personal_knowledge/retrieval/evidence.py
    - src/personal_knowledge/retrieval/semantic_search.py
    - src/personal_knowledge/evaluation/retrieval_adapters.py
    - src/personal_knowledge/evaluation/run_knowledge_eval.py
    - src/personal_knowledge/evaluation/calibrate_abstention.py
key-decisions:
  - Runtime support decisions never inspect frozen labels or expected_abstain.
  - Explicit query evidence conditions are checked against resolved source content; missing conditions fail closed.
  - Score thresholds remain diagnostics only; no similarity threshold is deployed.
  - Evaluation run identity and manifests bind snapshot ID, manifest hash and every serving member version before and after.
requirements-progressed: [QUAL-01, QUAL-02]
duration: 35 min
completed: 2026-07-17
---

# Phase 24 Plan 01: Evidence-aware Relevance and Snapshot-bound Evaluation Summary

Implemented deterministic supported/unsupported/uncertain decisions, enforced privacy/lifecycle/provenance and explicit evidence conditions across KU and fallback retrieval, and bound evaluation runs to the immutable composite serving authority.

## Tasks Completed

1. Added typed evidence support decisions with stable reason codes and evidence IDs; product and evaluation retrieval now suppress explicit unsupported candidates without consulting evaluation labels — commit `be59f2e`.
2. Captured and validated active snapshot ID/hash, required evidence roles, active/candidate/L2 source collection, and per-role versions in every evaluation mode and `run_manifest.json`; before/after drift fails closed — commit `be59f2e`.
3. Replaced deployable score-threshold calibration with an evidence-policy calibration while retaining score analysis as diagnostics only — commit `be59f2e`.

## Calibration Evidence

- Runtime report: `var/reports/analysis/evaluations/abstention_calibration_v1.json`.
- Snapshot: `ss_1590353394c948b908a5d675`, manifest `a2ce76eb…`, active collection unchanged.
- 29 hard-negative cases: emission false-positive rate `0.0` in all five modes.
- 3 currently evidence-eligible positives: result retention `1.0` in all five modes.
- 26 legacy positive Gold cases have ineligible primary canonical evidence and are explicitly listed for 24-02 review; they were not relabeled or counted as valid positives.
- `similarity_threshold_deployed: null`; evidence policy PASS.

## Verification

- Plan-specific unit/integration/contract suites: 49 passed.
- Live negative-condition smoke: `route=abstain`, zero results, same snapshot.
- `pk-sync status --json`: `ok=true`, `drift=[]`; active serving authority unchanged.
- Mixed collection and L2-source fixtures fail; one-snapshot fixture and run manifest before/after equality pass.
- `git diff --check`: clean. Ruff unavailable in the local Python environment.

## Deviations from Plan

**[Rule 1 - Evidence correctness]** Extended the typed resolver to recover canonical KU primary evidence through `canonical_unit_members`; canonical rows do not store `source_message_ref` directly.

**[Rule 3 - Evaluation data defect]** The private development set contained 26 positive Gold units backed by currently ineligible canonical evidence. The calibration now audits and excludes these invalid positives instead of weakening the privacy veto; 24-02 owns genuine replacement/review.

**Total deviations:** 2 auto-fixed. **Impact:** runtime privacy remains fail-closed and the next human-review packet has an explicit defect cohort.

## Issues Encountered

Python 3.14 narrow pytest invocations can print a third-party pyarrow/sklearn shutdown access-violation trace after all tests pass with exit code 0. This pre-existing runner issue did not affect assertions or process status.

## Self-Check: PASSED

All planned code artifacts exist, the private calibration passes without a deployed score threshold, fault-injection tests cover mixed versions and evidence vetoes, and live serving authority remains unchanged.

## Next Plan Readiness

Ready for 24-02. The 26 invalid-positive case IDs are persisted in the private calibration report and must enter the genuine human Gold review workflow; no agent-generated labels may replace human judgments.
