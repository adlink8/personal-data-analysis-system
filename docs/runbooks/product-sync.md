# Product sync runbook

**Status:** supported (2026-07-17)
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

# Other source products (all dry-run by default)
pk-sync turns                    # preview Turn vector rebuild
pk-sync turns --write            # publish only after retrieval probe succeeds
pk-sync google                   # preview normalized + assertion lifecycle
pk-sync google --write           # publish only after privacy gate succeeds
pk-sync status --json            # read-only versions/watermarks/drift
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
- A successful `--write` appends immutable artifact versions and source
  watermarks. Repeating unchanged input is a metadata no-op. Dry-run, build
  failure, privacy failure, or retrieval-probe failure does not advance them.
- None of these commands calls paid KU extraction or activates a composite
  serving snapshot.

## Composite serving authority (Phase 23)

`var/db/personal_system.sqlite` is the authority for the active immutable
snapshot. `var/db/knowledge_index_active.txt` is only a compatibility
projection. When they differ, SQLite wins and `doctor` fails closed.

### Schema and safe current-state bootstrap

```powershell
# Inspect first; no write when --write is absent
python -m personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables --inspect
python -m personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables --write

# Read-only proof inventory; does not create or activate a snapshot
python -m personal_knowledge.application.serving.snapshots bootstrap `
  --eval-gate <passing-eval-gate.json>

# Explicitly write a complete DRAFT only; still no active change
python -m personal_knowledge.application.serving.snapshots bootstrap `
  --eval-gate <passing-eval-gate.json> --write
```

Bootstrap fails with `missing_proofs` until Conversation, Turn, Google and KU
publications all have version-bound watermarks. It also records the tracked
retrieval contract and named evaluation artifact only on explicit `--write`.

### Validate, activate, roll back, recover

```powershell
python -m personal_knowledge.application.serving.snapshots validate --snapshot <ss_id>
python -m personal_knowledge.application.serving.snapshots activate --snapshot <ss_id>
python -m personal_knowledge.application.serving.snapshots status

# Roll back by reactivating an existing validated immutable snapshot
python -m personal_knowledge.application.serving.snapshots rollback --snapshot <prior_ss_id>

# Inspect pointer drift, then explicitly repair projection from SQLite authority
python -m personal_knowledge.application.serving.snapshots repair-pointer
python -m personal_knowledge.application.serving.snapshots repair-pointer --write

# Full read-only product integrity gate; critical failure exits 1
pk-ku doctor --json --skip-ports
python -m personal_knowledge.governance.preflight --ci
```

Validation verifies all required registry roles, Chroma count/checksum, a
passing eval gate, typed evidence resolution and watermark ordering. Failed
validation never changes active authority. Activation commits SQLite first;
pointer projection failure is reported as drift and is repaired separately.
Normal `status`, `doctor`, validation diagnostics and repair dry-runs are
read-only.

### After conversation sync (optional)

| Need | Command / module (not via rag-pipeline) |
|------|----------------------------------------|
| Conversation source pointer | `python -m personal_knowledge.application.conversation.rollback_agent_conversation_source --to canonical --write` |
| Session summaries (LLM) | `python -m personal_knowledge.application.conversation.summary --write` |
| Turn vectors | `pk-sync turns --write` |
| **Knowledge unit incremental** | **See [ku-incremental.md](ku-incremental.md)** — start with `pk-ku inspect`; full chain: prepare → extract → extract-gate → canonical → publish → vector → canary → promote → watermark |
| Promote KU | After eval; see ku-incremental.md Step E (`pk-ku promote` / `pk-ku watermark`) |

**Do not** chain `pk-sync` into `build_knowledge_inventory --write` + `build_knowledge_units_prod --start`.  
That freezes the **full** eligible set and re-queues old evidence (banned for daily use).

### Phase 42：稳定会话键改造后的顺序与复检

涉及会话去重键或 evidence 口径的改动，必须先用现行代码执行一次常规
`pk-sync conversations --write` 消化 normalized 数据积压，再切换新键重建
canonical；否则 `pk-ku inspect` 的 delta 无法归因。改键首轮之后，`deleted_refs`
突增属于 superseded/合并副本退出 eligible 集的真实口径修正，双 watermark 轨
（`committed` / `committed_assistant`）各执行一次受控 `inspect → prepare` 即可。
只有“inspect 有 delta 而 prepare 为 no_op”才是 Gate B 真异常，应立即 STOP。

重建后日常复检可运行 `pk-ku doctor --skip-ports`；其中 `session_dedup` 是
warn-only 观测项，不阻断产品健康检查。正式 canonical 库可执行以下三条零重复 SQL：

```sql
-- A. 一个源会话只归属一个 canonical session
SELECT COUNT(*) FROM (SELECT source, source_session_id FROM session_source_links
  GROUP BY 1,2 HAVING COUNT(DISTINCT canonical_session_id)>1);
-- B. active 稳定键唯一
SELECT COUNT(*) FROM (SELECT s.source, s.source_session_id FROM session_source_links s
  JOIN canonical_sessions c USING(canonical_session_id)
  WHERE c.lifecycle IS NULL OR c.lifecycle='active'
  GROUP BY 1,2 HAVING COUNT(DISTINCT s.canonical_session_id)>1);
-- C. 消息键唯一
SELECT COUNT(*) FROM (SELECT canonical_session_id, ordinal FROM canonical_messages
  GROUP BY 1,2 HAVING COUNT(*)>1);
```

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
