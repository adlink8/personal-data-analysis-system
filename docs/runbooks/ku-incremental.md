# Knowledge Unit (KU) incremental runbook

**Status:** supported operator contract (2026-07-16)  
**Audience:** humans and coding agents  
**Authority:** Phase 14 plans (KU-05 backfill vs KU-08 incremental) + module contracts in  
`application/knowledge/refresh_knowledge_units.py`

---

## 0. One-sentence rule

**Daily / after conversation sync: only extract the delta (new/modified evidence).  
Never start a full frozen inventory production run as a substitute.**

**Product CLI (preferred):** `pk-ku` — policy and batching via flags; do not change application code for daily ops.

| Intent | Allowed? | Entry |
|--------|----------|--------|
| See if source changed | Yes | **`pk-ku inspect`** |
| Freeze **delta** preflight (no LLM) | Yes when it works | **`pk-ku prepare …`** (policy flags) |
| Extract **only delta queue** | Yes (design goal) | **`pk-ku extract --run <ir_…>`** |
| Run status | Yes | **`pk-ku status --run …`** |
| Extraction gate | Yes | **`pk-ku extract-gate --run … [--min-yield 0.7]`** |
| Canonical units | Yes after extract | **`pk-ku canonical --run … --write`** |
| Publish staging → current | Yes (additive only) | **`pk-ku publish --run … --write`** |
| Candidate vector index | Yes | **`pk-ku vector --write`** (never touches active) |
| Promote to active | Yes after eval labels | **`pk-ku promote --collection … --require-eval-pass …`** |
| Freeze **full** inventory + prod `--start` whole ledger | **No for daily** | Not exposed on `pk-ku`; KU-05 backfill only via explicit underlying modules |
| `rag-pipeline` for KU | **No** | Retired |

Underlying modules (`refresh_knowledge_units`, `build_knowledge_units_prod`, …) remain for forensics; **operators and agents should use `pk-ku`**.

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
pk-ku inspect
# equivalent: python -m personal_knowledge.application.ku inspect
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
pk-ku prepare `
  --model gemini-3.5-flash `
  --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" `
  --auth-mode gcloud `
  --artifact var\reports\analysis\ai_context\knowledge_incremental_delta.json
```

**Extract-queue policy is CLI-controlled** (do not hardcode in agent scripts; do not edit source for daily ops). Defaults are safe daily incremental:

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
pk-ku prepare --model gemini-3.5-flash --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" --auth-mode gcloud `
  --roles user --since 2026-07-13 --max-extract-items 100

# Include modified + no watermark date floor
pk-ku prepare --model gemini-3.5-flash --provider vertex_google `
  --endpoint "https://aiplatform.googleapis.com" --auth-mode gcloud `
  --no-extract-new-only --no-extract-since-watermark
```

Read `extract_item_count` / `fresh_run_id` from the JSON artifact before any paid extract.

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
pk-ku extract --run <fresh_run_id> --model gemini-3.5-flash `
  --max-items <batch> --workers 4 --min-request-interval 2.5
```

`pk-ku extract` only accepts incremental `ir_*` run ids by default (full-inventory run ids require `PK_KU_ALLOW_NON_INCREMENTAL_RUN=1` forensics).

Use small `--max-items` first (e.g. 20–50) to smoke Vertex, then larger batches.  
Monitor:

```powershell
pk-ku status --run <run_id>
```

**If refresh --write is used:** it may mark lifecycle and **print** pipeline commands with `requires_approval` — those commands must still target **new refs only**, not a brand-new full inventory. LLM is not auto-run by design.

### Step D — Canonical / candidate index (after extraction succeeds)

```powershell
pk-ku extract-gate --run <run_id> --min-yield 0.7
pk-ku canonical --run <run_id> --write
pk-ku publish --run <run_id> --write   # additive; does NOT demote other runs
pk-ku vector --write                  # candidate collection only
```

`pk-ku publish` is the incremental-safe path: only this `ir_*` run’s `staging` → `current`.  
Do **not** use full-backfill `StagingPublisher.promote` (it demotes other runs).

### Step E — Eval then promote

```powershell
# Canary against candidate (active unchanged)
python -m personal_knowledge.evaluation.knowledge.evaluate_knowledge_canary `
  --candidate-override <collection> --queries 30 `
  --report var\reports\analysis\ai_context\ku_canary_<id>.json

# Strict gate needs labels on the report first:
#   … --strict   (fails while gate.status=pending_labels)

pk-ku promote --list
# Only after labeled canary / eval gate PASS:
pk-ku promote --collection <candidate_collection> `
  --require-eval-pass `
  --eval-summary <path> `
  --eval-gate <path>
```

**Gate E:** No promote while canary `gate.status=pending_labels` or extract-gate critical fail without human waiver. Active pointer is the **last** write.

### 2026-07-16 incremental cycle (reference)

| Step | Result |
|------|--------|
| run | `ir_4cd8af4ad31ccdc2` (delta `di_9e002cdac7af1460`) |
| extract | 756 queued → 586 succeeded / 110 abstained / 60 terminal_failed |
| extract-gate | privacy fixed for `di_*`; yield 0.775; **failed** only on `api_completion` (52 non-schema terminal) |
| canonical | 1456 draft units → 1425 staging canonical written |
| publish | additive → +1425 current canonical (total current **32184**); active untouched |
| vector | candidate `knowledge_units_ir_4cd8af4ad_20260716020508` (32184, gate PASS) |
| canary | 30 queries, p95≈152ms, **pending_labels** → **no promote** |
| active | still `knowledge_units_205bff9560b9_20260712142938` |

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
[ ] Use pk-ku (not ad-hoc module paths / code edits) for daily KU
[ ] pk-ku inspect recorded; new_refs_count known
[ ] Human approval if paid batch is large
[ ] pk-ku prepare; if no_op but inspect shows change → STOP (do not full inventory)
[ ] pk-ku extract --run ir_* only — never invent full inventory fallback
[ ] pk-ku status shows pending decreasing on the CORRECT run
[ ] No promote until eval gate
[ ] Report before/after: active pointer, unit counts, run_id, new_refs
[ ] Policy changes → CLI flags only; do not patch prepare defaults for one-off runs
```

---

## 8. Related docs

- Agent manual: [../AGENTS.md](../AGENTS.md)  
- Conversation sync: [product-sync.md](product-sync.md)  
- Retrieval SSOT: [../architecture/retrieval-ssot.md](../architecture/retrieval-ssot.md)  
- Phase planning: `.planning/phases/14-knowledge-unit-layer/` (KU-05 vs KU-08)  
