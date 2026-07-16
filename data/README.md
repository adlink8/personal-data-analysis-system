# data/ — Phase 20 private data roots

| Path | Content |
|------|---------|
| `raw/google/` | Google Takeout-style raw exports |
| `staging/` | Intermediate import staging (reserved) |
| `canonical/agent/` | Agent structured + conversation DBs |
| `canonical/google/structured/` | Google structured SQLite/CSV |
| `imports/` | Import batches / quarantine |

## Key files

| File | Role |
|------|------|
| `canonical/agent/structured/db/agent_conversations.sqlite` | Dialogue SSOT (canonical messages) |
| `canonical/agent/structured/db/agent_data.sqlite` | Agent structured store |
| `canonical/google/structured/db/google_data.sqlite` | Google light / activities |

Legacy roots `Agent/`, `Google/`, `imports/` were cut over on **2026-07-13**.  
Resolve paths only through `personal_knowledge.core.project_paths`.  
Cutover backups: repo-root `*.bak-phase20` (recovery window only).

## Conversation refresh (product)

```powershell
pk-sync conversations --write
```

Rebuilds `agentsview_normalized.sqlite` + `agent_conversations.sqlite` from
AgentsView live (read-only). See `docs/runbooks/product-sync.md` and `docs/AGENTS.md`.
