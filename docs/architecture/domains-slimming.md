# Domains slimming (Phase 21)

**Status:** complete (2026-07-15)  
**Planning:** `.planning/phases/PDA-21-architectural-alignment-domains-slimming/`

## Goal

Move build/eval orchestration out of `domains/` into `application/` and
`evaluation/`, delete confirmed dead code, and break the cross-domain LLM hub
coupling in `build_conversation_summary`.

## Layout

```
src/personal_knowledge/
  core/llm.py                          # generic LLM client + retry (D-01)
  application/
    conversation/   # build + summary orchestration
    graph/
    knowledge/
    memory/
  evaluation/
    conversation/
    graph/
    knowledge/
    memory/
    vector/         # was retrieval/evaluate_* + compare_*
  domains/
    {conversation,graph,knowledge,memory}/
      *.py          # re-export facades → application/evaluation (until 2026-08-13)
      knowledge/migrate_add_knowledge_unit_tables.py  # SCHEMA_SQL stays
  retrieval/
    evaluate_vector_*.py, compare_*_generations.py    # facades → evaluation/vector
```

## Import rules

| Need | Import from |
|------|-------------|
| LLM client / retry | `personal_knowledge.core.llm` |
| Conversation summary build | `personal_knowledge.application.conversation.summary` |
| Any build / lifecycle script | `personal_knowledge.application.<subdomain>.…` |
| Any eval / compare / audit | `personal_knowledge.evaluation.<subdomain|vector>.…` |
| Domain schema constant | `personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables` |
| Legacy path (tests/shims) | `personal_knowledge.domains.<subdomain>.…` (facade) |

## Deleted

- `domains/graph/build_graph_relation_candidates_v2.py` (dead; broken internal import)

## Product sync vs retired pipeline

| Entry | Role |
|-------|------|
| **`pk-sync conversations [--write]`** | **Product** — AgentsView → normalized → canonical conversation SSOT |
| `rag-pipeline` / `run_pipeline` steps 1–12 | **Retired** — integrated personal_events / memory batch; blocked unless `PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated` |

## Deferred

- Remove facades after **2026-08-13**
- Eliminate `retrieval/memory.py` lazy imports of `domains.graph.query_graph`
- Delete `.bak-phase20` backups (separate recovery window)

## Verification

See `21-VERIFICATION.md` in the phase directory. Summary:

- pytest: only known governance/memory_decomplexity baseline failures
- architecture-boundary: PASS
- REST `:8000/health` and MCP `:8789/health`: 200
