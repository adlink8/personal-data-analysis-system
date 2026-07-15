# Application pipelines

## Responsibility

Compose ingestion, domain builds, lifecycle, and controlled publication.
**After Phase 21 this package owns all former `domains/*/build_*` orchestration.**

## Layout

```
application/
  conversation/   # summary, vector store, agentsview, graph helpers, …
  graph/          # relation candidates, merge layer, triple store, judge, query
  knowledge/      # KU pipeline, refresh, promote, rollback, …
  memory/         # memory store/graph, promotions, lifecycle, …
  run_pipeline.py # STEP_MODULES → application.* canonical paths
  …               # google / import / integrated system entrypoints
```

## Boundaries

- Orchestration only — domain rules stay under `domains/` (or constants like `SCHEMA_SQL`).
- Shared LLM client lives in `core/llm.py`, not in conversation domain modules.
- Invokes evaluation gates when promoting (e.g. knowledge index).

## Entry points

```powershell
python -m personal_knowledge.application.run_pipeline --help
python -m personal_knowledge.application.conversation.summary --dry-run
python -m personal_knowledge.application.knowledge.refresh_knowledge_units --help
```

## Tests

Dry-run, idempotency, failure and lifecycle tests under `tests/`.

## Ownership

Owner: application. Status: supported. Last layout review: Phase 21 (2026-07-15).
