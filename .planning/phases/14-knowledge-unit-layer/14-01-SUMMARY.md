---
phase: 14-knowledge-unit-layer
plan: "01"
subsystem: rag
tags: [sqlite, chroma, pydantic, frozen-eval, knowledge-units]
requires:
  - phase: 13.5-agentsview-session-integration
    provides: canonical conversation evidence and privacy eligibility boundary
provides:
  - reproducible dev/frozen/merge evaluation datasets and raw retrieval baseline
  - knowledge-unit schema, run manifest, staging publisher, and strict small-sample extraction PoC
  - 33-unit candidate vector index with frozen-test A/B and pointer promote/rollback PoC
affects: [14-02-production-backfill, canonicalization, retrieval-canary, lifecycle]
tech-stack:
  added: [pydantic-v2]
  patterns: [evaluation-first RAG, staging-before-publish, versioned candidate index]
key-files:
  created:
    - integration/scripts/knowledge_unit_pipeline.py
    - integration/scripts/build_knowledge_units.py
    - integration/scripts/evaluate_knowledge_unit_rag.py
  modified:
    - integration/scripts/build_knowledge_unit_vector_store.py
    - integration/scripts/promote_knowledge_index.py
key-decisions:
  - "Frozen evaluation and raw baseline precede knowledge-unit publication."
  - "All extraction output enters staging and candidate indexes remain versioned."
  - "The PoC result does not satisfy production backfill, canonicalization, canary, or incremental lifecycle requirements."
patterns-established:
  - "Knowledge units retain evidence references and are evaluated against a frozen test set."
  - "Candidate index promotion is pointer-based and preserves the previous checkpoint."
requirements-completed: [KU-01, KU-02, KU-03, KU-04]
duration: historical
completed: 2026-07-10
---

# Phase 14 Plan 01 Summary: Knowledge-unit RAG Proof of Concept

**Evaluation-first knowledge-unit PoC improved frozen retrieval from Recall@5 0.50 to 0.85 while preserving zero secret hits and a rollback pointer.**

## Performance

- **Duration:** Historical execution; exact elapsed time was not recorded during migration.
- **Completed:** 2026-07-10 or earlier; summarized during GSD migration on 2026-07-10.
- **Scope:** Legacy Wave 0–2 and candidate-index/A/B PoC from Wave 4.
- **Phase 14 tests:** 40 passed in the recorded implementation run.
- **Full suite:** 210 passed in the recorded implementation run.

## Accomplishments

- Created 20 dev, 20 frozen-test, 20 merge-positive, and 20 hard-negative evaluation cases with zero recorded split leakage.
- Recorded raw retrieval baseline: Recall@5 0.50 and MRR@5 0.4625.
- Added six-table knowledge-unit schema, run manifest, staging publisher, versioned extraction prompt/Pydantic validation, and small-sample extraction gate.
- Built the 33-unit `knowledge_units_a89ebe470357` candidate/index checkpoint and promoted its pointer after the recorded frozen A/B gate.
- Recorded candidate metrics: Recall@5 0.85, MRR@5 0.7392, secret hit 0, p95 15.4 ms; the prior raw p95 was 17.7 ms.

## Verification Evidence

| Evidence | Recorded result |
|---|---:|
| Phase 14 test files | 40 passed |
| Repository full suite | 210 passed |
| Frozen Recall@5 | 0.50 → 0.85 |
| Frozen MRR@5 | 0.4625 → 0.7392 |
| Secret hit | 0 |
| Active pointer recorded in project state | `knowledge_units_a89ebe470357` |

These are migrated historical results. Plan 14-02 and later must rerun their task-local tests and production gates; this summary is not a substitute for new execution evidence.

## Explicitly Not Completed by Plan 01

- KU-05 production backfill: frozen full inventory, durable item ledger, classified retry, response cache, resume, and fail-closed completion gate.
- KU-06 production canonicalization: `canonical_knowledge_units` remains unbuilt in the researched production database; no full positive/hard-negative canonical publish exists.
- KU-07 unified retrieval canary: no candidate-override 30-query canary or privacy-safe feedback closure.
- KU-08 incremental refresh/lifecycle: no affected-subject refresh, delete propagation, lifecycle write, or joint rollback closure.

The active 33-unit index is a PoC rollback baseline built from pre-canonical knowledge units. It must not be treated as proof that canonicalization, production promotion hardening, canary, or lifecycle work is complete.

## Task Commits

Historical commits were not reconstructed during document migration. No new commit was created for this summary.

## Decisions Made

- Preserve the 33-unit active pointer as the rollback baseline while production work builds immutable candidates.
- Treat `KU-01..KU-04` as the completed PoC scope only.
- Execute `KU-05..KU-08` through Plans 14-02 through 14-06 with new tests, checkpoints, and production evidence.

## Deviations from Plan

The legacy plan interleaved completed PoC work with unimplemented production waves. This summary deliberately records only verified PoC delivery and leaves Wave 3, Wave 5–6, and production hardening open.

## Issues Encountered

- The historical requirement text referenced 5,485 records, while current research found 2,237 extractor inputs after cleaning/dedup and 3,248 coarse eligible user messages. Plan 14-02 resolves this through an authoritative frozen inventory.
- The current active PoC index was built from raw knowledge units rather than passed canonical units.

## User Setup Required

None for the completed PoC. Production model availability and paid-run authorization are explicit checkpoints in Plans 14-03 and 14-04.

## Next Phase Readiness

- Evaluation/schema/extraction/index PoC contracts exist and are ready for production hardening.
- Plan 14-02 remains the first incomplete executable plan.
- KU-05, KU-06, KU-07, and KU-08 remain incomplete.

---
*Phase: 14-knowledge-unit-layer*
*Plan: 01*
*Completed: 2026-07-10*
