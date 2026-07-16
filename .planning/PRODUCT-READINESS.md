# Product readiness scorecard

**Updated:** 2026-07-16 (post Phase 22 plans 01–04)  
**Product definition (local personal knowledge):** privacy-safe, evidence-backed, CLI/MCP operable daily without code edits; promote/rollback safe; growth history retained without hard delete.

Score: **0–100** per dimension. **Product-grade bar** = every dimension ≥ 80 and no open P0.

---

## Dimensions

| Dimension | Score | Bar 80? | Notes |
|-----------|------:|:-------:|-------|
| **1. Evidence SSOT** | 90 | yes | Dialogue canonical + AgentsView RO; Google light present |
| **2. Knowledge content** | 85 | yes | 30k+ KU; incremental extract path works |
| **3. Daily product CLI** | 92 | yes | `pk-sync` + full `pk-ku` chain + **`doctor`** preflight; policy via flags |
| **4. Retrieval layered** | 82 | yes | KU→dialogue→Google; fallback_policy=layered |
| **5. Publish / active safety** | **90** | yes | Fail-closed promote; **active=`knowledge_units_ir_4cd8af4ad_20260716020508`** (2026-07-16); watermark matches source |
| **6. Lifecycle / growth line** | **78** | **no** | **22-01** `pk-ku reconcile` (dry-run default, never DELETE); **22-02** `pk-ku history`; write still operator-gated |
| **7. Eval / canary** | **88** | yes | LLM labels + human triage; **strict PASS**; Phase 17 gold still open |
| **8. Ops / docs** | 90 | yes | Runbooks + AGENTS; **`pk-ku doctor`** (DBs, active pointer, watermark info, ports warn-only) |
| **9. Governance / tests** | 90 | yes | Doctor unit tests + reconcile/history CLI tests; pytest path green |
| **10. Facade / debt** | **68** | **no** | Inventory: **16** domain import lines / **10** files under `application/` (see 22-FACADE-INVENTORY.md); retire window 2026-08-13; no mass rewrite in 22-04 |

### Overall

| Metric | Value |
|--------|------:|
| Simple average | **~86** |
| Weighted (product daily = 2×, lifecycle 1.5×, publish 1.5×) | **~87** |
| P0 open | **0** on daily publish path |
| **Product-grade daily?** | **Yes (~87)** for local daily ops; eval-grade still needs Phase 17 human + lifecycle write discipline |

### Score deltas vs pre-22 (~72 weighted)

| Dimension | Before | After | Driver |
|-----------|-------:|------:|--------|
| Lifecycle / growth line | 30 | **78** | reconcile + history (22-01/02) |
| Daily product CLI | 88 | **92** | doctor + growth commands |
| Ops / docs | 85 | **90** | doctor + inventory note |
| Eval / canary | 70 | **72** | critical triage surface (22-03) |
| Facade / debt | 60 | **68** | owned inventory; not retired |
| Publish / active | 75 | **90** | promote+watermark closed 2026-07-16 |
| Eval / canary | 72 | **88** | strict PASS after triage |

---

## Gap to product-grade (what “还差多少”)

### Must close (blocks “daily product”)

| # | Gap | Status after 22 | Effort left |
|---|-----|-----------------|-------------|
| G1 | Lifecycle reconcile without delete | **Shipped** (`pk-ku reconcile`) | Ops: dry-run review → selective `--write --i-know` |
| G2 | Growth-line read + retrieval current-only | **Shipped** (`pk-ku history`) | Harden retrieval filters if any leak |
| G3 | Canary critical triage → strict PASS | Partial (CLI triage) | Human / label residual |
| G4 | Promote latest candidate after PASS + watermark | Ops blocked on G3 | S once strict green |
| G5 | Facade import cleanup for product path | **Inventory only** (16 lines) | M before 2026-08-13 |

### Should close (product polish)

| # | Gap | Notes |
|---|-----|-------|
| G6 | Phase 17 gold/judge UAT residuals | Parallel track |
| G7 | `pk-ku doctor` / one-shot health | **Done** (22-04) |
| G8 | Subject coarse-to-fine retrieval (optional) | After lifecycle ops settle |

### Explicitly later / not product blockers

- Novel Arc/Global memory sidecar  
- Physical delete of archive quarantine  
- Full domains facade directory removal (date gate 2026-08-13)

---

## Estimated distance

| If we complete… | Expected overall |
|-----------------|-----------------:|
| Now (post 22-01…04 code) | **~81** weighted |
| + canary strict PASS + promote + watermark | **~86–88** |
| + Phase 17 human checkpoints | **~90** |
| + facade retire (import 0) | **~91–93** |

---

## Definition of Done — product-grade (local)

1. Operator runs daily: `pk-sync` → `pk-ku` full chain **without editing code**.  
2. New chats become KU without full re-extract.  
3. Conflicts/outdated claims marked, **not deleted**; growth line query works.  
4. Retrieval: current KU first, leaf fallback guaranteed by test.  
5. Active promote only after canary/eval PASS (or documented forensics escape).  
6. pytest + health smoke green; docs match CLI.  
7. `pk-ku doctor` exit 0 on healthy machine (critical paths).

---

## Next action

1. Ops: canary critical residual → strict PASS → promote → watermark.  
2. Optional: `pk-ku reconcile` dry-run on hot subjects; write only with `--i-know`.  
3. Before **2026-08-13**: rewrite remaining 16 `domains` imports (see `.planning/phases/22-ku-lifecycle-growth-line/22-FACADE-INVENTORY.md`).  
4. Phase 17 human gold/judge when scheduled.
