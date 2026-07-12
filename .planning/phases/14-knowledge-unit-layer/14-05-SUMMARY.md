---
phase: 14-knowledge-unit-layer
plan: "05"
type: execute
wave: 4
status: complete
requirements: [KU-02, KU-04, KU-07]
completed: 2026-07-11
---

# Phase 14 Plan 05 Summary: Retrieval + Feedback + Canary

**Feedback schema (3 tables), knowledge-first unified search, and canary evaluator with privacy-safe contracts. 12 tests passed. 295 total passed.**

## Accomplishments

### Feedback schema
- 3 new tables: `rag_runs`, `rag_retrieval_items`, `rag_feedback`
- Privacy-safe: query_hash only (no raw query, evidence_quote, result_text, credential, token, secret)
- Label CHECK: helpful/wrong/stale/missing only
- 12 tests passed (search contracts + feedback privacy)

### Knowledge-first unified search
- `search_knowledge_units(query, top_k, collection, include_evidence)` backend
- Knowledge-first route with raw fallback on missing/broken active
- Non-current lifecycle units filtered
- Version info included (index/build/canonical/status)

### Canary evaluator
- `generate_canary_queries(n)` from canonical units (query_hash only)
- `run_canary(collection, n_queries)` with active pointer unchanged guarantee
- Canary report with privacy-safe results (hash only, no raw content)

### Production promote/rollback
- Pre-existing `promote_knowledge_index.py` and `rollback_knowledge_checkpoint.py`
- Active pointer management with JSONL audit log
- 5 promotion tests already passed in Plan 04

## Verification Evidence

| Evidence | Result |
|---|---|
| Phase 14 tests | 34 targeted tests passed |
| Full suite | 312 passed (2 pre-existing failures unrelated) |
| Feedback tables | 3 tables, privacy-safe schema |
| Active pointer | knowledge_units_731a6a8a0994_20260710165905 (2,393 items, promoted) |
| Canary gate | PASS (helpful=93.3%, critical=0, fallback=0) |
| Hybrid A/B | Recall@5=0.85, MRR@5=0.71 (ku1+raw4) |

## Completed Checkpoints

- Task 4: 30-query human canary labels — COMPLETED (28 helpful, 2 missing)
- Task 5: Strict canary gate — PASS
- Task 6: Production promote — APPROVED and executed
- Task 7: Journal promote + post-promote reconcile + rollback drill — PASS

## Next Phase Readiness

- Plan 14-06 (incremental refresh + lifecycle) complete
- Active index: 2,393 items, rollback target: 33-item PoC
- Hybrid search (ku1+raw4) wired to CLI/REST/MCP entry points