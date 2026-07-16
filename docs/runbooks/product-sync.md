# Product sync runbook

**Status:** supported (2026-07-16)  
**Audience:** humans and coding agents operating this repo

## Goal

Keep **local conversation evidence** and (separately) **knowledge units** current
without running the retired integrated batch (`rag-pipeline` steps 1–12).

## Canonical product entry

```powershell
cd <project-root>
pip install -e .   # once / after entrypoint changes
$env:PYTHONPATH = "<project-root>\src"   # if not using installed package

# Dialogue SSOT: AgentsView live → normalized → canonical
pk-sync conversations           # dry-run (default)
pk-sync conversations --write   # publish DBs
```

Equivalent module form:

```powershell
python -m personal_knowledge.application.sync conversations --write
```

### What `pk-sync conversations` does

| Step | Module | Writes |
|------|--------|--------|
| 1 Inventory | `application.conversation.import_agentsview_sessions` | report only under `var/reports/analysis/ai_context/` |
| 2 Normalized | `application.conversation.build_agentsview_normalized` | `data/canonical/agent/structured/db/agentsview_normalized.sqlite` (with `--write`) |
| 3 Canonical | `application.conversation.build_canonical_agent_conversations` | `data/canonical/agent/structured/db/agent_conversations.sqlite` (with `--write`) |

- **Never writes** `%USERPROFILE%\.agentsview\sessions.db` (protected-external, read-only).
- Privacy gates: secret sessions get no message bodies; local PII/credential scan.

### After conversation sync (optional)

| Need | Command / module (not via rag-pipeline) |
|------|----------------------------------------|
| Conversation source pointer | `python -m personal_knowledge.application.conversation.rollback_agent_conversation_source --to canonical --write` |
| Session summaries (LLM) | `python -m personal_knowledge.application.conversation.summary --write` |
| Turn vectors | `python -m personal_knowledge.application.conversation.build_conversation_vector_store --write` |
| **Knowledge unit incremental** | **See [ku-incremental.md](ku-incremental.md)** — start with `refresh_knowledge_units --inspect` only |
| Promote KU | After eval; see ku-incremental.md Step E |

**Do not** chain `pk-sync` into `build_knowledge_inventory --write` + `build_knowledge_units_prod --start`.  
That freezes the **full** eligible set and re-queues old evidence (banned for daily use).

## Retired: integrated pipeline

| Entry | Status |
|-------|--------|
| `rag-pipeline` | **Retired product entry** — prints redirect, **exit 2** |
| `run_pipeline` steps 1–12 | **Blocked** without `--legacy-integrated` |
| Emergency only | `PK_ALLOW_LEGACY_PIPELINE=1` + `--legacy-integrated` |

Those steps rebuild `personal_system.sqlite` / memory / `personal_events` vectors.
They are **not** the knowledge SSOT path (KU is). Prefer never for day-to-day work.

## Verify after sync

```powershell
# Counts / presence
python -c "from pathlib import Path; from personal_knowledge.core.project_paths import AGENT_CONVERSATIONS_DB, AGENTSVIEW_NORMALIZED_DB; print(AGENT_CONVERSATIONS_DB, Path(AGENT_CONVERSATIONS_DB).exists())"

# Optional: services for MCP/search
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8789/health
```

## Related docs

- Agent operating manual: [../AGENTS.md](../AGENTS.md)
- **KU incremental (delta only):** [ku-incremental.md](ku-incremental.md)
- Retrieval SSOT: [../architecture/retrieval-ssot.md](../architecture/retrieval-ssot.md)
- Zones: [../architecture/repository-zones.md](../architecture/repository-zones.md)
