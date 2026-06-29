# Phase 07 Wave 9/10 Conflict Audit

**Date:** 2026-06-28
**Scope:** Check whether newly planned Wave 9/10 conflicts with Phase 04-06 memory layer, Phase 07 Wave 1-8, and current repository scripts.

## Verdict

Wave 9/10 does **not** conflict with Phase 04-06 if the new design keeps three boundaries:

1. Do not write graph-judge output into `memory_items` / `memory_relations`.
2. Do not merge `conversation_turns` into `personal_events` until vector evaluation proves it is safe.
3. Do not reuse the deprecated `conversation_graph.duckdb` pseudo-relation graph.

The main conflicts are stale Phase 07 plan text and executable entrypoints that still expose old pseudo-graph behavior.

## Conflict Table

| ID | Area | Conflict | Status | Required Action |
| --- | --- | --- | --- | --- |
| C-01 | Wave 7 docs | PLAN still referenced missing `build_conversation_event_layer.py` and `unified_events` writeback, but actual design chose independent `conversation_turns`. | Fixed in PLAN | Keep Wave 7 on `build_conversation_vector_store.py`; do not add event-layer writeback in this phase. |
| C-02 | Wave 9/10 order | Graph candidate generation depends on vector health/eval, but plan numbering put graph before vector evaluation. | Fixed in PLAN/CONTEXT by dependency note | Execute `Wave 10.1/10.2 -> Wave 9 -> Wave 10.3`. |
| C-03 | Phase 06 boundary | Phase 06 is a sidecar deep profile and explicitly does not write `memory_items`; Wave 9 graph could be mistaken as replacing it. | No conflict if isolated | Keep Wave 9 graph separate from Phase 06 deep profile; optionally use Phase 06 insights only as evaluation examples, not as graph facts. |
| C-04 | Memory store contract | Phase 04/05 memory layer owns `memory_items` / `memory_links` / `memory_relations`; Wave 9 proposes new graph judgments. | No conflict if new tables used | Store candidates/judgments in separate tables: `graph_relation_candidates`, `graph_relation_judgments`, `graph_relation_review_queue`. |
| C-05 | Deprecated graph script | `build_triple_store.py` still has runnable DuckDB pseudo-graph write path (`e_next_turn`, `e_session_topic`). | Fixed | `--only duckdb` 已改为直接报 deprecated，并指向 `build_conversation_graph.py --write`。 |
| C-06 | Pipeline behavior | `run_pipeline.py` includes step 13 `build_conversation_vector_store --write`; full pipeline can fail if Chroma/embedding is offline, despite comments implying step 13 is optional. | Fixed | 已新增 `--include-conversation-turns`; 默认全量管道回到稳定步骤 1-12。 |
| C-07 | Chroma source of truth | Wave 9 candidates depend on `conversation_turns`; if collection is stale relative to `conversation_summaries.json`, graph candidates will be stale. | Fixed | `build_graph_relation_candidates.py` 已增加 collection-summary 一致性门禁(expected_count / actual_count / metadata sample)。 |
| C-08 | LLM relation hallucination | LLM relation judge could create unsupported semantic edges. | Planned mitigation | Gate on whitelist, confidence, source_refs, `no_relation`, review queue. |
| C-09 | Docs / README drift | README and architecture docs document Phase 07 up to vector回流, not Wave 9/10 graph-judge flow. | Fixed | README / PLAN / 废弃说明 已同步到当前 Wave 9/10 真相。 |

## Deletions / Reductions Recommended

- Do not resurrect `build_conversation_event_layer.py` in Phase 07.
- Do not write turn summaries into `unified_events` during this phase.
- Do not use `build_triple_store.py --only duckdb` for graph output before Wave 9 rewrite.
- Do not let vector similarity directly create graph edges.
- Do not push LLM graph judgments into `memory_items` or `memory_relations`.

## Additions Required Before Execution

1. Vector preflight:
   - `evaluate_vector_collections.py`
   - `vector_retrieval_eval_set.json`
   - `evaluate_vector_retrieval.py`

2. Graph candidate and judge:
   - `build_graph_relation_candidates.py`
   - `prompts/graph_relation_judge/v1_main.md`
   - `prompts/graph_relation_judge/v1_schema.md`
   - `judge_graph_relations.py`

3. Gate and graph build:
   - `evaluate_graph_relation_judgments.py`
   - `graph_relation_review_queue`
   - `build_conversation_graph.py`
   - `query_conversation_graph.py --smoke`

4. Safety hardening:
   - Disable deprecated DuckDB pseudo-graph write path in `build_triple_store.py`.
   - Make `run_pipeline.py` step 13 opt-in or clearly optional.

## Recommended Execution Order

```text
Wave 10.1 / 10.2: vector health + retrieval eval
-> Wave 9.1: graph relation candidates
-> Wave 9.2: LLM relation judge
-> Wave 9.3: evidence gate + review queue
-> Wave 9.4: DuckDB graph rebuild from accepted judgments only
-> Wave 10.3: user-facing cross-collection ranking
```

## Current Safe State

- Phase 06 remains completed and isolated.
- Phase 07 Wave 8 quality report passes: 0 defects / 583 Agent turns, 100% source_refs coverage.
- Deprecated `conversation_graph.duckdb` is preserved as an experiment artifact and must not be used as graph truth.
- New Wave 9/10 plan has now been executed through Wave 10.3 closure items; former open conflicts C-05/C-06/C-07 are fixed.
