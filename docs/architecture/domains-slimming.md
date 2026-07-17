# Domains slimming (Phase 21) + facade debt clearance

**Status:** Phase 21 complete (2026-07-15); **application→domains real imports cleared (2026-07-16)**  
**Planning:** `.planning/phases/21-architectural-alignment-domains-slimming/`
**Inventory:** `.planning/phases/22-ku-lifecycle-growth-line/22-FACADE-INVENTORY.md`

## Goal

Move build/eval orchestration out of `domains/` into `application/` and
`evaluation/`, delete confirmed dead code, and break the cross-domain LLM hub
coupling in `build_conversation_summary`.

## Layout (current)

```
src/personal_knowledge/
  core/llm.py                          # generic LLM client + retry (D-01)
  application/
    conversation/   # build + summary orchestration
    graph/
    knowledge/      # includes migrate_add_knowledge_unit_tables (SCHEMA_SQL canonical)
    memory/
    ku.py / sync.py # product CLI surfaces (pk-ku / pk-sync)
  evaluation/
    conversation/
    graph/
    knowledge/
    memory/
    vector/         # was retrieval/evaluate_* + compare_*
  domains/
    {conversation,graph,knowledge,memory}/
      *.py          # re-export facades → application/evaluation (optional external compat)
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
| **Schema SQL / migrate** | **`personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables`** |
| Legacy path (tests / `tools/compat` / old scripts) | `personal_knowledge.domains.<subdomain>.…` (**facade only**) |

### Application tree policy (2026-07-16)

- **`application/**` must not `from personal_knowledge.domains…` import** (count **0**; verified by `pk-ku doctor`).
- Product CLI (`pk-ku`, `pk-sync`) never imports domains.
- `domains/*` may remain as **re-export shims** for external/compat callers until package removal.
- Optional later: delete entire `domains/` package when external consumers are zero.

## Deleted

- `domains/graph/build_graph_relation_candidates_v2.py` (dead; broken internal import)

## Product sync vs retired pipeline

| Entry | Role |
|-------|------|
| **`pk-sync conversations [--write]`** | **Product** — AgentsView → normalized → canonical conversation SSOT |
| **`pk-ku …`** | **Product** — incremental KU lifecycle (see `docs/runbooks/ku-incremental.md`) |
| `rag-pipeline` / `run_pipeline` steps 1–12 | **Retired** — blocked unless `PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated` |

## Deferred / residual

| Item | Status |
|------|--------|
| Remove `domains/` package entirely | Optional after consumer graph is empty (was 2026-08-13 window) |
| `retrieval/memory.py` lazy graph imports | Residual non-application path |
| `*.bak-phase20` | **Moved** to `archive/quarantine/bak-phase20-20260716/` (2026-07-16) |
| `tools/compat/v1_1` shims | Separate compat budget (not application facade debt) |

## Verification

```powershell
$env:PYTHONPATH = "<project-root>\src"
python -m personal_knowledge.application.ku doctor --skip-ports
# expect: facade imports (application → domains): 0 lines in 0 files
python -m pytest -q tests --tb=line
```

Historical Phase 21 notes: `21-VERIFICATION.md` in the phase directory.
