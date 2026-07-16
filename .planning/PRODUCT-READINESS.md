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
| **10. Facade / debt** | **88** | yes | **application → domains real imports = 0** (2026-07-16 rewrite); domains package remains as re-export shims until optional 2026-08-13 package delete |

### Overall

| Metric | Value |
|--------|------:|
| Simple average | **~88** |
| Weighted (product daily = 2×, lifecycle 1.5×, publish 1.5×) | **~89** |
| P0 open | **0** on daily publish path |
| **Product-grade daily?** | **Yes (~89)**; Phase 17 human gold + optional domains package delete remain polish |

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
| G3 | Canary critical triage → strict PASS | **Done 2026-07-16** (human triage + strict PASS) | — |
| G4 | Promote latest candidate after PASS + watermark | **Done 2026-07-16** (active=ir_4cd8af; wm match) | — |
| G5 | Facade import cleanup for product path | **Done 2026-07-16** (application imports 0; domains package still optional shim) | Optional package delete after window |

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
| Now (post 22 + promote close-out) | **~87** weighted |
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

1. ~~Ops: canary → promote → watermark~~ **DONE 2026-07-16**.  
2. Optional: `pk-ku reconcile` dry-run on hot subjects; write only with `--i-know`.  
3. ~~Rewrite application→domains imports~~ **DONE 2026-07-16** (count 0). Optional: delete `domains/` package after external consumers zero.  
4. Phase 17 human gold/judge when scheduled.  
5. Optional: start REST/MCP (`start-services.ps1`) for live retrieval smoke on new active.
