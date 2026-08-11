# Personal Knowledge System — Agent Operating Manual

**Purpose:** Single source of instruction for AI coding agents and CLI agents working
in this repository. Prefer this file over outdated chat memory when procedures conflict.  
**Last updated:** 2026-08-09 (engineering structure + testing contract)
**Workspace root:** project root containing `src/personal_knowledge/`, `data/`, `var/`, `.planning/`.  
**Readiness:** `.planning/PRODUCT-READINESS.md` (~89 weighted daily product-grade approach).

---

## 1. What this project is

Local, privacy-first **personal knowledge system** on Windows:

```text
AgentsView / Google / … (upstream)
        → canonical evidence (conversation, light Google, …)
        → knowledge units (KU) + active vector index
        → hybrid retrieval
        → REST :8000 / MCP :8789 / ChatGPT tunnel :8081
```

**Core value:** personal history → evidence-backed, queryable knowledge with promote/rollback.

**Not:** a generic data warehouse dashboard; not “memory experiments as knowledge SSOT”.

---

## 2. SSOT map (do not confuse)

| Layer | Authority | Path / surface |
|-------|-----------|----------------|
| Dialogue evidence | **Canonical conversation** | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Dialogue live upstream | AgentsView (read-only) | `%USERPROFILE%\.agentsview\sessions.db` — **never relocate, never write** |
| Knowledge | **KU + active collection** | SQLite KU tables + `var/db/knowledge_index_active.txt` |
| Non-dialogue raw (fallback) | personal_events / unified | `var/db/personal_system.sqlite` (transition layer) |
| Memory tables | **Experimental only** | not knowledge SSOT (Phase 08 cancelled) |
| Vector indexes | Retrieval features | Chroma; **not** fact SSOT |
| Path resolution | `project_paths` | `src/personal_knowledge/core/project_paths.py` |

Retrieval order (default layered hybrid): **KU → dialogue → Google PE → optional legacy pad**.  
**Dual-view:** retrieval = `lifecycle=current` only; growth line = `pk-ku history --subject S` (multi-version, no DELETE).  
See `docs/architecture/retrieval-ssot.md`.

---

## 3. Product workflows (use these)

### 3.1 Conversation data update (daily)

```powershell
cd <project-root>
pip install -e .
pk-sync conversations           # dry-run first
pk-sync conversations --write   # publish normalized + canonical
```

Details: `docs/runbooks/product-sync.md`.

### 3.2 Knowledge unit update (when needed) — **incremental only**

**Full runbook:** [`docs/runbooks/ku-incremental.md`](runbooks/ku-incremental.md)  
**Planning intent:** Phase 14 KU-08 = affected / new evidence only; KU-05 full inventory = rare backfill.

#### Required order

```text
1) pk-sync conversations [--write]
2) pk-ku inspect
3) pk-ku prepare --model …   # policy flags only; no code edits
4) pk-ku extract --run ir_*  # only if extract_item_count > 0
5) pk-ku extract-gate --run … [--min-yield 0.7]
6) pk-ku canonical --run … --write
7) pk-ku publish --run … --write   # additive staging→current
8) pk-ku vector --write            # candidate only
9) pk-ku canary --candidate-override … --report …
10) pk-ku canary --report … --label-with-llm   # or human labels
11) pk-ku canary --report … --list-critical / --strict
12) pk-ku promote --collection … --eval-gate …   # default require eval PASS
13) pk-ku watermark --advance --from-canonical --write
# optional lifecycle (never DELETE rows):
# pk-ku reconcile --dry-run | --write --i-know
# pk-ku history --subject S
# pk-ku doctor
```

```powershell
$env:PERSONAL_DATA_GCLOUD = "<path-to-gcloud.bat>"   # if gcloud not on PATH
pk-ku workflow          # print full flow
pk-ku doctor --skip-ports
pk-ku inspect
# prepare / extract flags: pk-ku prepare -h | docs/runbooks/ku-incremental.md
```

**Do not change KU application code for daily policy tweaks** — use `pk-ku prepare` flags (`--since`, `--roles`, `--max-extract-items`, …).

#### Hard rules (KU)

| Rule | Detail |
|------|--------|
| **Only delta** | Daily work extracts **new** evidence by default (`--extract-new-only`), not the full eligible set |
| **inspect vs prepare conflict** | If inspect shows `source_changed` + `new_refs>0` but prepare is `no_op`/`delta_count=0` → **STOP**. Report prepare defect. **Do not** invent another path |
| **Forbidden daily fallback** | `build_knowledge_inventory --write` + `build_knowledge_units_prod --start` on that full inventory = **full re-extract**. Soft-banned without `PK_KU_ALLOW_FULL_INVENTORY_START=1` |
| **No auto paid LLM** | `refresh --write` prints commands with approval; it does not auto-call Vertex |
| **Active last** | Never promote mid-run; promote **defaults to require eval** (`--allow-without-eval` forensics only) |
| **Growth line** | Prefer `lifecycle` supersede/conflict via `pk-ku reconcile`; **never hard-delete** knowledge rows for cleanup |
| **No rag-pipeline** | Retired; wrong layer for KU |
| **Imports** | New code: `application.*` / `evaluation.*` only — **not** `domains.*` (facades optional for legacy only) |

#### Full inventory is not incremental

| Command pair | Meaning |
|--------------|---------|
| `build_knowledge_inventory --write` | Freezes **all** eligible messages (KU-05 backfill input) |
| `build_knowledge_units_prod --start --inventory <full>` | Queues **entire** ledger for extraction |

Use only for **planned production backfill/rebuild**, never after a normal `pk-sync`.

### 3.3 Serve MCP / ChatGPT

```powershell
# One-shot watchdog (keep window open)
pwsh -NoProfile -ExecutionPolicy Bypass -File apps\personal_data_chatgpt\scripts\start-services.ps1
# or: apps\personal_data_chatgpt\scripts\启动服务.bat
```

| Service | Port | Health |
|---------|------|--------|
| REST | 8000 | `http://127.0.0.1:8000/health` |
| MCP Apps | 8789 | `http://127.0.0.1:8789/health` · endpoint `/mcp` |
| Tunnel (ChatGPT) | 8081 | `http://127.0.0.1:8081/healthz` · UI `/ui` |

- Tunnel needs proxy `http://127.0.0.1:7897` for OpenAI control plane.  
- REST/MCP are localhost only; `NO_PROXY` must include localhost for tunnel→MCP.  
- Closing the watchdog PowerShell window **stops all children**.

### 3.4 Search / API (local)

```powershell
rag-search stats --json
rag-api    # usually already started by watchdog
```

---

## 4. Retired / forbidden product paths

| Action | Status |
|--------|--------|
| `rag-pipeline` (steps 1–12 default) | **Retired** — CLI exits 2 with redirect to `pk-sync` |
| Full integrated rebuild for “daily conversation sync” | **Do not** |
| Full KU inventory + `prod --start` as daily “sync after chat” | **Forbidden** (see §3.2 / ku-incremental.md) |
| Ignore inspect≠prepare (no_op) and keep paying LLM | **Forbidden** |
| Resume a mistaken full-inventory run until pending=0 | **Forbidden** |
| Promote without eval when gate is required | **Forbidden** |
| Write AgentsView live DB | **Forbidden** |
| Treat `memory_*` or raw `personal_events` as knowledge SSOT | **Forbidden** |
| Commit `data/**`, `var/**` private content, secrets, `*.sqlite` | **Forbidden** (gitignore) |
| Delete raw/canonical without recovery plan | **Forbidden** |
| Fabricate missing intermediate evidence | **Forbidden** |
| Rewrite Vertex extraction to another LLM “just to run” | **Forbidden** without explicit product decision |

Emergency legacy only:

```powershell
$env:PK_ALLOW_LEGACY_PIPELINE = '1'
python -m personal_knowledge.application.run_pipeline --legacy-integrated --dry-run
```

---

## 5. Repository layout (agent navigation)

| Path | Role |
|------|------|
| `src/personal_knowledge/core/` | Paths, privacy, `llm` |
| `src/personal_knowledge/adapters/` | Source adapters (AgentsView RO) |
| `src/personal_knowledge/application/` | **Canonical** build/lifecycle (conversation, knowledge, …) |
| `src/personal_knowledge/evaluation/` | Eval / gate / reports |
| `src/personal_knowledge/retrieval/` | Search / vectors (eval re-exports → `evaluation/vector/`) |
| `src/personal_knowledge/services/` | REST / MCP stdio / dashboard |
| `src/personal_knowledge/domains/*/` | Optional re-export shims only (application imports = 0) |
| `apps/personal_data_chatgpt/` | ChatGPT HTTP MCP + widgets + start scripts |
| `data/` | Private data (not for git content) |
| `var/` | DB / runtime / reports |
| `governance/` | Policies, preflight contracts |
| `docs/` | Architecture + runbooks + **this agent manual** |
| `.planning/` | GSD roadmap / phase plans (authoritative process state) |
| `tests/` | unit / contract / integration / governance |

Layer rule: domain ↛ application; evaluation does not silently promote.  
See `governance/policies/architecture.yaml`, `docs/architecture/domains-slimming.md`.

---

## 6. End-to-end flow diagram

```text
┌─ Upstream (RO) ─────────────────────────────────────┐
│  AgentsView sessions.db   Google raw/canonical …     │
└────────────┬───────────────────────────┬─────────────┘
             │ pk-sync conversations     │ (separate Google lifecycle)
             ▼                           ▼
   agentsview_normalized          google light DB
             │
             ▼
   agent_conversations.sqlite  ◄── dialogue SSOT
             │
             │  inspect → prepare(delta) → extract ONLY new/modified
             │  → canonical KU → candidate vector → eval → promote
             │  (NOT full inventory --start)
             ▼
   canonical_knowledge_units + active Chroma collection
             │
             ▼
   unified_search (layered hybrid)
             │
             ▼
   rag-api :8000  ←  MCP :8789  ←  tunnel :8081 → ChatGPT
```

---

## 7. Operating rules for agents

1. **Read local facts first** (`project_paths`, live files, ports) — do not invent paths.  
2. **Prefer `pk-sync`** for conversation updates; never default to `rag-pipeline`.  
3. **Minimal diffs**; no drive-by refactors of unrelated modules.  
4. **Privacy:** no secrets, tokens, private message bodies in commits, docs, or logs pasted to chat.  
5. **Confirm before:** delete, force-push, remote infra, spending API quota, mass rewrites.  
6. **Validate:** after sync or code changes, run targeted imports/health or pytest subsets.  
7. **Planning:** multi-phase work uses `.planning/`; small fixes do not need GSD.  
8. **Windows + PowerShell** is the default environment.  
9. **Imports:** new code uses `application.*` / `evaluation.*` / `core.llm` only. `domains/*` is optional re-export; **application→domains debt = 0** (`pk-ku doctor`).  
10. **Engineering contract:** before adding behavior, fixing a bug, or changing an interface, read [`architecture/engineering-and-testing-contract.md`](architecture/engineering-and-testing-contract.md). Declare the public seam, observable behavior, invariants, and focused command; then use Red → Green → focused regression.
11. **Module cohesion:** one module has one primary reason to change. Split before adding a second independent behavior, lifecycle/state machine, authority owner, or a mixed UI/transport/domain/persistence responsibility.
12. If services are down: restart via `start-services.ps1`; check all three health URLs.

---

## 8. Standard agent checklist (copy)

```text
[ ] Confirm cwd = project root; PYTHONPATH or pip install -e .
[ ] For conversation growth: pk-sync conversations [--write]
[ ] For MCP tools: 8000 + 8789 up; for ChatGPT: also 8081 healthz=live
[ ] Do not write ~/.agentsview/sessions.db
[ ] Do not run rag-pipeline for product sync
[ ] Do not commit data/var private artifacts
[ ] Declare the public seam and make the focused behavior test red before implementation
[ ] Split modules that hit a required split trigger; justify or split files above review thresholds
[ ] After code changes: smoke import + relevant tests
[ ] Report paths, commands run, before/after counts when mutating data
```

---

## 9. Key commands cheat sheet

| Intent | Command |
|--------|---------|
| Sync conversations (dry) | `pk-sync conversations` |
| Sync conversations (write) | `pk-sync conversations --write` |
| KU product CLI | **`pk-ku`** (`workflow` / `inspect` / `prepare` / `extract` / `status` / `extract-gate` / `canonical` / `publish` / `vector` / `canary` / `promote` / `watermark` / `reconcile` / `history` / `doctor`) |
| KU growth line (read) | `pk-ku history --subject S [--limit N]` |
| KU lifecycle dry-run | `pk-ku reconcile --dry-run [--max-subjects N]` |
| KU health | `pk-ku doctor [--skip-ports]` |
| KU inspect (delta) | `pk-ku inspect` |
| KU prepare (no LLM) | `pk-ku prepare --model … --provider vertex_google --endpoint https://aiplatform.googleapis.com --auth-mode gcloud` |
| KU extract status | `pk-ku status --run <run_id>` |
| KU full procedure | **[runbooks/ku-incremental.md](runbooks/ku-incremental.md)** |
| Product readiness | [`.planning/PRODUCT-READINESS.md`](../.planning/PRODUCT-READINESS.md) |
| Legacy pipeline help | `pk-sync help-legacy` |
| Start REST+MCP+tunnel | `apps\...\scripts\start-services.ps1` |
| Health | `curl.exe --noproxy "*" http://127.0.0.1:8000/health` (8789, 8081/healthz) |
| Search CLI | `rag-search …` |
| Preflight | `python -m personal_knowledge.governance.preflight --ci` |
| Tests | `python -m pytest -q tests/` |

---

## 10. Doc index

| Doc | Use |
|------|-----|
| **This file** | Agent operating manual (workflows + hard rules) |
| [runbooks/product-sync.md](runbooks/product-sync.md) | Conversation sync (`pk-sync`) |
| [runbooks/ku-incremental.md](runbooks/ku-incremental.md) | **KU delta-only procedure + forbidden full inventory** |
| [architecture/retrieval-ssot.md](architecture/retrieval-ssot.md) | Three-layer SSOT + hybrid |
| [architecture/repository-zones.md](architecture/repository-zones.md) | data/var/archive/src zoning |
| [architecture/domains-slimming.md](architecture/domains-slimming.md) | application vs domains layout + facade clear |
| [architecture/engineering-and-testing-contract.md](architecture/engineering-and-testing-contract.md) | Module cohesion, public seams, Red/Green, mocking, negative tests, and change gates |
| [../AGENTS.md](../AGENTS.md) | Workspace MCP/service short instructions |
| [../.planning/PROJECT.md](../.planning/PROJECT.md) | Product goals & decisions |
| [../.planning/ROADMAP.md](../.planning/ROADMAP.md) | Phase status (through Phase 22) |
| [../.planning/PRODUCT-READINESS.md](../.planning/PRODUCT-READINESS.md) | Daily product readiness scorecard |
| [../.planning/STATE.md](../.planning/STATE.md) | Live SSOT / active index / checkpoints |
| `.planning/phases/14-knowledge-unit-layer/` | KU-05 backfill vs KU-08 incremental plans |
| `.planning/phases/22-ku-lifecycle-growth-line/` | Lifecycle / growth line / facade inventory |

---

## 11. Change log (agent-relevant)

| Date | Change |
|------|--------|
| 2026-07-16 | Phase 22 lifecycle/growth line; promote close-out; **facade debt clear** (application→domains = 0) |
| 2026-07-16 | SCHEMA_SQL moved to `application.knowledge.migrate_add_knowledge_unit_tables` |
| 2026-07-16 | **KU incremental runbook**; ban full inventory as daily fallback; inspect≠prepare → stop |
| 2026-07-16 | Product entry `pk-sync`; `rag-pipeline` retired (exit 2) |
| 2026-07-16 | Agentsview→canonical modules restored under `application/conversation/` |
| 2026-07-15 | Phase 21 domains slimming; `core/llm` |
| 2026-07-13 | Phase 20 data/var/archive cutover |
