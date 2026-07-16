# Documentation

## Responsibility

Architecture, operational contracts, and runbooks for the personal knowledge system.

## Boundaries

- Repository architecture and SSOT docs live under `docs/`.
- Planning state lives only in `.planning/`.
- Private evidence never belongs in docs (R1/R2 text only).

## Entry points

| Doc | Topic |
|-----|--------|
| **[AGENTS.md](AGENTS.md)** | **Agent 全流程操作手册（产品路径 + 禁令 + checklist）** |
| [runbooks/product-sync.md](runbooks/product-sync.md) | `pk-sync conversations` 对话增量 runbook |
| [architecture/repository-zones.md](architecture/repository-zones.md) | Physical + logical zones (Phase 20–21) |
| [architecture/domains-slimming.md](architecture/domains-slimming.md) | Phase 21 application/evaluation layout |
| [architecture/retrieval-ssot.md](architecture/retrieval-ssot.md) | Three-layer SSOT and hybrid retrieval |
| [runbooks/dependency-governance.md](runbooks/dependency-governance.md) | Dependency / preflight gates |
| [runbooks/tooling/tools.md](runbooks/tooling/tools.md) | Tooling notes |
| [../data/README.md](../data/README.md) | Private data tree |
| [../var/README.md](../var/README.md) | Runtime / DB / reports tree |
| [../.planning/ROADMAP.md](../.planning/ROADMAP.md) | Authoritative roadmap |

## I/O and privacy

R1/R2 only; never embed personal evidence or credentials.

## Tests

Docs coverage and governance planning checks validate maintained entries.

## Ownership

Owner: documentation. Status: supported. Last layout review: 2026-07-16 (pk-sync + agent manual).
