# Knowledge Unit (KU) incremental runbook

**Status:** supported operator contract (2026-07-16)  
**Audience:** humans and coding agents  
**Authority:** Phase 14 plans (KU-05 backfill vs KU-08 incremental) + module contracts in  
`application/knowledge/refresh_knowledge_units.py`

---

## 0. One-sentence rule

**Daily / after conversation sync: only extract the delta (new/modified evidence).  
Never start a full frozen inventory production run as a substitute.**

| Intent | Allowed? | Entry |
|--------|----------|--------|
| See if source changed | Yes | `refresh_knowledge_units --inspect` |
| Freeze **delta** preflight (no LLM) | Yes when it works | `refresh_knowledge_units --prepare …` |
| Extract **only new/modified** refs | Yes (design goal) | Delta inventory + `build_knowledge_units_prod --resume` / incremental commands from refresh |
| Freeze **full** inventory + `--start` whole ledger | **No for daily** | Only **planned production backfill / rebuild** (KU-05), never as “prepare failed” fallback |
| Promote to active | Yes after eval | `promote_knowledge_index` (+ prefer `--require-eval-pass`) |
| `rag-pipeline` for KU | **No** | Retired |

---

## 1. Concepts (do not mix)

| Concept | Meaning |
|---------|---------|
| **Dialogue SSOT** | `agent_conversations.sqlite` (after `pk-sync conversations`) |
| **Knowledge SSOT** | `canonical_knowledge_units` + **active** Chroma collection pointer |
| **Inspect delta** | Compare current dialogue SSOT / inventory → `new_refs` / `deleted_refs` / subjects |
| **Full inventory** | All eligible user messages frozen once for **backfill** (`build_knowledge_inventory`) |
| **Delta inventory** | Only new/modified/deleted refs for **incremental** run |
| **Watermark** | `knowledge_source_watermark` committed checksum after a successful incremental cycle |
| **Active pointer** | `var/db/knowledge_index_active.txt` — **last** step; never touch mid-extraction |

Phase 14 split:

- **KU-05 production backfill** = full inventory + durable ledger (expensive, rare).  
- **KU-08 incremental refresh** = affected subjects / new evidence only (daily after dialogue grows).

---

## 2. Prerequisites

```powershell
cd <project-root>
$env:PYTHONPATH = "<project-root>\src"

# Vertex extraction (existing scripts) — gcloud must work
# If gcloud not on PATH, set:
$env:PERSONAL_DATA_GCLOUD = "C:\Users\li\google-cloud-sdk\gcloud.bat"   # example machine path

# Verify token without printing it
& $env:PERSONAL_DATA_GCLOUD auth print-access-token | ForEach-Object { "token_len=$($_.Length)" }
```

Also:

1. Dialogue SSOT already updated if the goal is “new chats → KU” (`pk-sync conversations --write` first).  
2. Active index path known: `Get-Content var\db\knowledge_index_active.txt`.  
3. Do **not** open a second concurrent `build_knowledge_units_prod` on the same `run_id` without reading status.

---

## 3. Canonical incremental procedure (operator)

### Step A — Inspect (required, free)

```powershell
python -m personal_knowledge.application.knowledge.refresh_knowledge_units --inspect
```

Record:

| Field | Action |
|-------|--------|
| `source_changed` | Must be True to continue paid work |
| `current_checksum` | Save for logs |
| `new_refs` / `new_refs_count` | **Paid extract target size** |
| `deleted_refs_count` | Lifecycle only; **not** “re-extract all deleted” |
| `affected_subjects` | Scope note |
| `no_op` | If True → stop (nothing to do) |

**Gate A:** If `new_refs_count` is large (thousands), print estimate and **get human approval** before any LLM batch.

### Step B — Prepare delta artifact (free metadata)

```powershell
python -m personal_knowledge.application.knowledge.refresh_knowledge_units `
  --prepare `
  --model gemini-3.5-flash `
  --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" `
  --auth-mode gcloud `
  --artifact var\reports\analysis\ai_context\knowledge_incremental_delta.json
```

**Extract-queue policy is CLI-controlled** (do not hardcode in agent ad-hoc scripts). Defaults are safe daily incremental:

| Flag | Default | Meaning |
|------|---------|---------|
| `--extract-new-only` / `--no-extract-new-only` | new only | Include `modified` only with `--no-extract-new-only` |
| `--extract-since-watermark` / `--no-extract-since-watermark` | on | Floor session date at watermark day |
| `--since YYYY-MM-DD` | (none) | Explicit floor; **overrides** watermark floor |
| `--skip-succeeded` / `--no-skip-succeeded` | skip | Drop refs already `succeeded` in any run |
| `--roles user` or `user,assistant` | all eligible | Role allow-list |
| `--baseline-inventory <id>` | watermark-era auto | Force before inventory |
| `--max-extract-items N` | unlimited | Cap queue after filters (newest first) |

Examples:

```powershell
# Only user messages since 2026-07-13, cap 100
python -m personal_knowledge.application.knowledge.refresh_knowledge_units `
  --prepare --model gemini-3.5-flash --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" --auth-mode gcloud `
  --roles user --since 2026-07-13 --max-extract-items 100

# Include modified + full post-baseline new (no watermark date floor)
python -m personal_knowledge.application.knowledge.refresh_knowledge_units `
  --prepare --model gemini-3.5-flash --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" --auth-mode gcloud `
  --no-extract-new-only --no-extract-since-watermark
```

Read `extract_item_count` / `fresh_run_id` from the JSON artifact before any paid `--resume`.

Expect non-paid: `production_llm_calls=0`, `active_changed=false`.

**Gate B — conflict rule (hard):**

| inspect | prepare | Operator action |
|---------|---------|-----------------|
| `source_changed=True`, new_refs > 0 | `no_op=true` / `delta_count=0` | **STOP.** Do **not** invent another path. Report **prepare/delta defect**. |
| `source_changed=True` | non-empty `delta_inventory_id`, `fresh_run_id`, `new_count`/`delta_count` > 0 | Continue to Step C |
| `no_op` / unchanged | anything | Stop; no paid run |

Known implementation note (2026-07): when a committed watermark exists, `prepare_production_delta` may call `prepare_delta` with the **same** canonical DB as before/after, so content delta is empty even though inspect sees inventory drift. Treat that as **defect**, not as permission to full-backfill.

### Step C — Paid extraction (only delta / approved run)

**Preferred (when prepare produced a fresh run bound to delta):**

```powershell
python -m personal_knowledge.application.knowledge.build_knowledge_units_prod `
  --resume <fresh_run_id> `
  --model gemini-3.5-flash `
  --max-items <batch> `
  --workers 4 `
  --min-request-interval 2.5
```

Use small `--max-items` first (e.g. 20–50) to smoke Vertex, then larger batches.  
Monitor:

```powershell
python -m personal_knowledge.application.knowledge.build_knowledge_units_prod --status <run_id>
```

**If refresh --write is used:** it may mark lifecycle and **print** pipeline commands with `requires_approval` — those commands must still target **new refs only**, not a brand-new full inventory. LLM is not auto-run by design.

### Step D — Canonical / candidate index (after extraction succeeds)

```powershell
python -m personal_knowledge.application.knowledge.build_canonical_knowledge_units --run <run_id> --write
python -m personal_knowledge.application.knowledge.build_knowledge_unit_vector_store --write
```

(Exact flags: follow each module `--help`. Do not promote yet.)

### Step E — Eval then promote

```powershell
# Eval via existing knowledge eval entry (config under assets/evals or project eval paths)
# Then:
python -m personal_knowledge.application.knowledge.promote_knowledge_index --list
python -m personal_knowledge.application.knowledge.promote_knowledge_index `
  --promote <candidate_collection> `
  --require-eval-pass `
  --eval-summary <path> `
  --eval-gate <path>
```

**Gate E:** No promote without eval pass when gate files exist. Active pointer is the last write.

---

## 4. Forbidden fallbacks (accident log)

| Forbidden action | Why it is wrong |
|------------------|-----------------|
| After failed/empty prepare → `build_knowledge_inventory --write` + `prod --start` | Freezes **entire** eligible set (~20k+) and re-queues old evidence |
| Resume a mistaken full-inventory run “until pending=0” | Continues paying for non-delta work |
| Promote mid-run | Can point active at incomplete candidate |
| Use `rag-pipeline` to “refresh knowledge” | Retired; wrong SSOT layer |
| Ignore inspect vs prepare conflict | Hides prepare bugs; burns quota |

**Incident 2026-07-16:** Agent ran full inventory after prepare `no_op` despite inspect showing ~4k new_refs. Process was stopped; active pointer left unchanged. Do not resume that full run as daily work.

---

## 5. Command matrix (paid / active / full)

| Command | LLM paid? | Touches active? | Full eligible set? | Daily OK? |
|---------|-----------|-----------------|--------------------|-----------|
| `refresh --inspect` | No | No | No (reports delta) | Yes |
| `refresh --prepare` | No | No | No (delta artifact) | Yes |
| `refresh --write` | No auto-LLM | No | No (lifecycle + command list) | Careful |
| `build_knowledge_inventory --write` | No | No | **Yes freeze** | **Only planned backfill** |
| `build_knowledge_units_prod --start` on full inventory | **Yes** | No | **Yes extract** | **No daily** |
| `prod --resume` on **delta** run | **Yes** | No | No | Yes after approval |
| `build_knowledge_unit_vector_store --write` | Embed cost | No (candidate) | Rebuild candidate | After extract |
| `promote_knowledge_index --promote` | No | **Yes** | N/A | After eval |

---

## 6. Environment notes (existing scripts)

| Need | How |
|------|-----|
| Vertex token | `gcloud auth print-access-token` via `PERSONAL_DATA_GCLOUD` if not on PATH |
| Project/model defaults | `PERSONAL_DATA_GCP_PROJECT`, `PERSONAL_DATA_VERTEX_LOCATION`, `PERSONAL_DATA_VERTEX_MODEL` |
| Machine example (do not hardcode in new scripts) | `C:\Users\li\google-cloud-sdk\gcloud.bat` was verified present; PATH may omit it |

Do **not** rewrite extraction to another LLM provider as a “quick fix” without an explicit product decision.

---

## 7. Agent checklist (copy)

```text
[ ] Dialogue SSOT already current if goal is new chats (pk-sync first)
[ ] refresh --inspect recorded; new_refs_count known
[ ] Human approval if paid batch is large
[ ] prepare run; if no_op but inspect shows change → STOP (do not full inventory)
[ ] Extraction only on delta/fresh_run_id — never invent full inventory fallback
[ ] status shows pending decreasing on the CORRECT run
[ ] No promote until eval gate
[ ] Report before/after: active pointer, unit counts, run_id, new_refs
```

---

## 8. Related docs

- Agent manual: [../AGENTS.md](../AGENTS.md)  
- Conversation sync: [product-sync.md](product-sync.md)  
- Retrieval SSOT: [../architecture/retrieval-ssot.md](../architecture/retrieval-ssot.md)  
- Phase planning: `.planning/phases/14-knowledge-unit-layer/` (KU-05 vs KU-08)  
