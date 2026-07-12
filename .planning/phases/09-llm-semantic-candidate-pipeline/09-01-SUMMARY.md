---
phase: 09
name: llm_semantic_candidate_pipeline
status: Completed
completed: 2026-07-01
orchestration: GSD subagents
---

# Phase 09 Execution Summary

## Result

Phase 09 is complete. The active memory candidate pipeline now routes structured evidence through `memory_evidence_bundles` and LLM extraction instead of the removed `legacy_evidence_candidate` direct path.

## Implemented Waves

1. LLM candidate contracts
   - Added prompt contracts for graph candidate proposal, memory candidate extraction, and gate repair loop.
   - Each contract requires bounded schema, evidence refs, source refs, prompt metadata, and explicit reject/downgrade/review paths.

2. LLM-assisted graph candidate generation
   - Added `integration/scripts/build_graph_relation_candidates_v2.py`.
   - Script creates coarse recall packages first; LLM proposal is required before a semantic v2 candidate can be written.
   - Current environment has no live LLM key, so proposal rows are recorded as blocked and no fake semantic candidates are written.

3. Legacy direct evidence path removal
   - Removed `legacy_evidence_candidate` from the active promotion candidate builder.
   - Added `integration/scripts/build_memory_evidence_bundles.py`.
   - `memory_items` is only a duplicate/conflict target, not a candidate source.

4. LLM memory candidate extraction
   - Added `integration/scripts/extract_memory_candidates_from_bundles.py`.
   - The script only writes `source_system='llm_memory_candidate'` candidates after LLM output passes schema and evidence gates.
   - With no live LLM key, it reports `blocked:no_live_llm` and writes no fake candidates.

5. Gate repair loop and weighted approval
   - Extended `integration/scripts/evaluate_memory_promotion_candidates.py` with structured failure reasons, score components, final score, hard-risk veto, and `auto_approval_eligible`.
   - Added `integration/scripts/repair_memory_promotion_candidates.py`.
   - Tightened `apply_memory_promotions.py --approved-only` so it only considers `approved && !human_review_required && auto_approval_eligible=true`.

6. Integration and regression
   - Updated `README.md`, `integration/README.md`, and `.planning/codebase/ARCHITECTURE.md`.
   - Updated `integration/analysis/ai_context/memory_decomplexity_plan.md`.
   - Added regression tests covering the new pipeline and inactive source defense.

## Final Database State

- `memory_promotion_candidates`: `graph_relation_candidate=19`
- `legacy_evidence_candidate`: `0`
- `memory_evidence_bundles`: `100`
- `graph_relation_candidate_proposals`: `100 blocked / fallback:no_api_key`
- `semantic_candidate_v2` written to `graph_relation_candidates`: `0`
- Long-term memory tables unchanged:
  - `memory_items=194`
  - `memory_links=1478`
  - `memory_relations=27`

## Verification

Passed:

```powershell
python integration\scripts\build_graph_relation_candidates_v2.py --dry-run --limit 20
python integration\scripts\build_graph_relation_candidates_v2.py --write --limit 100
python integration\scripts\build_memory_evidence_bundles.py --write --limit 100
python integration\scripts\extract_memory_candidates_from_bundles.py --dry-run --limit 10
python integration\scripts\evaluate_memory_promotion_candidates.py --write
python integration\scripts\repair_memory_promotion_candidates.py --dry-run --limit 10
python integration\scripts\apply_memory_promotions.py --dry-run --approved-only
python integration\scripts\run_pipeline.py --dry-run
python tests\test_memory_contracts.py
python -m unittest tests.test_graph_relation_candidates_v2 tests.test_memory_evidence_bundles tests.test_memory_candidate_extraction tests.test_memory_gate_repair_loop tests.test_memory_promotion_candidates tests.test_memory_promotion_review
git diff --check
```

`git diff --check` only reported CRLF warnings for existing Windows line-ending normalization; no diff format errors.

## Remaining Runtime Condition

Live LLM branches are implemented but blocked in this environment because no live LLM API key is configured. This is intentional: graph proposal, memory extraction, and gate repair do not fabricate candidates when the LLM is unavailable.
