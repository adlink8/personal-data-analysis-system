# Plan 21-01 Summary: Conversation Domain Migration + LLM Primitive Split

**Completed:** 2026-07-15  
**Status:** done  
**Wave:** 1

## What shipped

1. **D-01 LLM split:** `core/llm.py` now owns `make_llm_client`, `_chat_with_retry`, `MAX_RETRY`. Conversation build logic lives at `application/conversation/summary.py`.
2. **D-02 peer rewires:** graph/memory peers import `personal_knowledge.core.llm`; GPT summary + eval-set import `application.conversation.summary`.
3. **Conversation build → application/conversation/** (9 modules + summary): agentsview, graph, segments, vector_store, gpt_summary, patch_summary_meta, query/visualize/rollback + facades.
4. **Conversation eval → evaluation/conversation/** (5 modules): cutover, prompt, quality, compare_summaries, build_conversation_eval_set + facades.
5. **Caller wiring:** `run_pipeline` STEP_MODULES and `evaluate_vector_collections` import/hints point at `application.conversation.*`.
6. **Facade pattern:** domains facades use `sys.modules[__name__] = canonical` so private symbols and module-level monkeypatch (e.g. `SOURCE_POINTER`) keep working.

## Gate results

| Gate | Result |
|------|--------|
| pytest FAILED set | **13** — identical known baseline (8 governance + 5 memory_decomplexity_plan). No new ImportError. |
| architecture-boundary (preflight) | PASS |
| Hub coupling domains.graph/memory → build_conversation_summary | eliminated |

### Known baseline FAILED (unchanged)

- `tests/governance/test_governance_artifacts.py` (1)
- `tests/governance/test_governance_inventory.py` (2)
- `tests/governance/test_governance_shims.py` (1)
- `tests/governance/test_physical_source_layout.py` (4)
- `tests/unit/test_memory_decomplexity_plan.py` (5)

## Deviations

- Facades use **module-alias** (`sys.modules[__name__] = _canonical`) instead of bare `import *`. Required so `import X as mod` monkeypatch and `_`-prefixed symbols work. Still carries `2026-08-13` cleanup marker in docstring.
- Updated `tests/unit/test_vector_collection_eval.py` assertion to new `application.conversation.build_conversation_vector_store` hint path (matches Task 6 string updates).
- Hint string in `build_triple_store.py` updated for hub-decoupling grep cleanliness (cosmetic; file migrates in 21-02).

## Self-Check: PASSED
