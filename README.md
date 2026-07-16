# Personal Knowledge System

Local, privacy-first pipeline that normalizes personal activity and conversations,
distils evidence-backed knowledge units, and exposes evaluated retrieval interfaces.

## Quick start

```powershell
pip install -r requirements-dev.txt
# package layout: src/personal_knowledge (console scripts after editable install)
pip install -e .
python -m pytest -q

# Product sync: AgentsView → canonical conversation SSOT
pk-sync conversations           # dry-run
pk-sync conversations --write   # publish
pk-ku workflow                  # knowledge unit daily flow
pk-ku inspect                   # free delta

rag-search stats --json
```

> **Note:** `rag-pipeline` (integrated steps 1–12 / personal_events + memory batch) is
> **retired** from product use. It exits with a redirect message unless
> `PK_ALLOW_LEGACY_PIPELINE=1` and `--legacy-integrated` are set (forensics only).

Production data is private. Do not commit databases, raw exports, runtime reports,
credentials, or private evaluation cases.

## Physical layout (Phase 20)

| Tree | Role |
|------|------|
| `src/personal_knowledge/` | Product source (see layer table below) |
| `data/` | Private data: raw / staging / canonical / imports |
| `var/` | DB, runtime, reports, logs, cache, migration journals |
| `archive/` | Quarantine (`_recycle`), planning (`.gsd`), vendor-reference |
| `assets/` | Versioned prompts, public eval fixtures, vendor assets |
| `governance/` | Policies, manifests, sanitized baselines |
| `tests/` | Unit / contract / governance tests |
| `.planning/` | Authoritative GSD roadmap and phase artifacts |

### Source layers (Phase 21)

| Path | Role |
|------|------|
| `core/` | Foundation (`project_paths`, `privacy_guard`, **`llm`**) |
| `domains/*/` | Domain rules/models/constants (+ temporary re-export facades → 2026-08-13) |
| `application/*/` | **Canonical** build / lifecycle orchestration |
| `evaluation/*/` | **Canonical** eval / compare / audit (incl. `evaluation/vector/`) |
| `retrieval/` | Vector/search I/O; eval scripts are facades to `evaluation/vector/` |
| `services/` | REST + MCP delivery |

**Path resolution:** `src/personal_knowledge/core/project_paths.py` prefers Phase 20
locations and falls back to legacy paths only if the new path is absent.

**Never relocate:** `%USERPROFILE%/.agentsview/sessions.db` (AgentsView live WAL, read-only).

## Authoritative runtime surfaces

| Surface | Path |
|---------|------|
| Unified DB | `var/db/personal_system.sqlite` |
| Active KU pointer | `var/db/knowledge_index_active.txt` |
| Agent conversation DB | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Google light DB | `data/canonical/google/structured/db/google_data.sqlite` |
| Analysis / eval reports | `var/reports/analysis/` |
| Migration journals | `var/phase20-journals/` |

## Repository navigation

- **[Agent operating manual](docs/AGENTS.md)** — full product workflow for AI/human operators
- [Product sync runbook](docs/runbooks/product-sync.md) — `pk-sync conversations`
- [KU incremental runbook](docs/runbooks/ku-incremental.md) — delta-only knowledge extract (no full inventory daily)
- [Repository zones](docs/architecture/repository-zones.md)
- [Domains slimming (Phase 21)](docs/architecture/domains-slimming.md)
- [Retrieval SSOT](docs/architecture/retrieval-ssot.md)
- [Data tree](data/README.md) · [Var tree](var/README.md)
- [Integration notes](integration/README.md) (legacy narrative; paths updated for Phase 20)
- [Current roadmap](.planning/ROADMAP.md) — `.planning/` is authoritative
- [Governance policies](governance/policies/architecture.yaml)
- [Test guide](tests/README.md)
- Workspace short instructions: [AGENTS.md](AGENTS.md)

Major source modules live under `src/personal_knowledge/`. Historical planning (`.gsd`)
and soft-deleted trees live under `archive/`. Compatibility backups from Phase 20 cutover
are named `*.bak-phase20` and remain only for the recovery window.

## Governance checks

```powershell
python -m personal_knowledge.governance.preflight --ci
python -m pytest -q tests/governance/
```
