# Repository logical and physical zones

Machine-readable authority: `governance/policies/architecture.yaml` and
`governance/policies/paths.yaml`. This page explains intent after **Phase 20**
physical cutover (2026-07-13) and **Phase 21** domains slimming (2026-07-15).

## Zones

| Zone | Physical paths (primary) | Purpose | Mutability |
|------|--------------------------|---------|------------|
| `src` | `src/`, `apps/`, `tools/` | Product code, MCP apps, tooling | reviewed source |
| `tests` | `tests/` | Deterministic tests and synthetic fixtures | reviewed source |
| `assets` | `assets/` | Versioned prompts, public eval contracts, vendor | immutable/versioned |
| `docs` | `docs/`, root `README.md` | Architecture and runbooks | reviewed docs |
| `governance` | `governance/` | Policies, schemas, sanitized baselines | fail-closed control plane |
| `data` | `data/{raw,staging,canonical,imports}/` | Private personal data | private; adapters only |
| `var` | `var/{db,runtime,reports,logs,cache,phase20-journals}/` | DB, runtime, logs, reports | generated / gitignored |
| `archive` | `archive/{quarantine,planning,vendor-reference}/` | Quarantine and historical trees | read-only / retention-bound |
| `planning` | `.planning/` | Current GSD lifecycle | authoritative |

## Phase 20 mapping (legacy → current)

| Legacy | Current |
|--------|---------|
| `Agent/structured/db/` | `data/canonical/agent/structured/db/` |
| `Google/raw/` | `data/raw/google/` |
| `Google/structured/` | `data/canonical/google/structured/` |
| `imports/` | `data/imports/` |
| `integration/db/` | `var/db/` |
| `integration/runtime/` | `var/runtime/` |
| `integration/analysis/` | `var/reports/analysis/` |
| `logs/` | `var/logs/` |
| `_recycle/` | `archive/quarantine/_recycle/` |
| `.gsd/` | `archive/planning/.gsd/` |
| `.ai-bridge/` | `archive/vendor-reference/.ai-bridge/` |

Code resolves paths via `personal_knowledge.core.project_paths` (prefer new, optional legacy fallback). Cutover backups: `*.bak-phase20`.

## Dependency direction

Allowed source direction: delivery → application → domain → foundation, with
infrastructure reached through explicit contracts. Evaluation may read public
domain/retrieval contracts but cannot silently promote. Product source must not
import `_tools`, raw data, runtime outputs, quarantine, or archived planning as
import sources.

## Layer map after Phase 21 (domains slimming)

| Layer | Package path | What lives there |
|-------|--------------|------------------|
| foundation | `core/` | paths, privacy, **`core/llm.py`** (OpenAI-compatible client + retry) |
| infrastructure | `adapters/`, `retrieval/` | source adapters; vector/search I/O |
| domain | `domains/{conversation,graph,knowledge,memory}/` | rules, models, constants only |
| application | `application/{conversation,graph,knowledge,memory}/` | **canonical** build / lifecycle scripts |
| evaluation | `evaluation/{conversation,graph,knowledge,memory,vector}/` | **canonical** eval / compare / audit suites |
| delivery | `services/` | REST / MCP |
| control | `governance/` | preflight, manifests, inventory |

**Facades (cleanup window through 2026-08-13):** every former
`domains/*/build_*.py` / `evaluate_*.py` (and related) is a re-export alias to
the application/evaluation canonical module (`sys.modules[__name__] = canonical`).
Retrieval-layer eval scripts (`evaluate_vector_*`, `compare_*_generations`) are
likewise facades into `evaluation/vector/`.

**Sole non-facade domain logic retained:** `domains/knowledge/migrate_add_knowledge_unit_tables.py`
(`SCHEMA_SQL` DDL constant).

**New code should import from** `application.*` / `evaluation.*` / `core.llm`,
not from `domains.*` facades.

```text
python -m personal_knowledge.application.conversation.summary --dry-run
python -m personal_knowledge.application.knowledge.refresh_knowledge_units --help
python -m personal_knowledge.evaluation.vector.evaluate_vector_collections
```

## External protected path

| Path | Rule |
|------|------|
| `%USERPROFILE%/.agentsview/sessions.db` | **protected-external** — never relocate; open read-only only |
