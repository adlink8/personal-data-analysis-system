# Product readiness scorecard

**Updated:** 2026-07-16  
**Product definition (local personal knowledge):** privacy-safe, evidence-backed, CLI/MCP operable daily without code edits; promote/rollback safe; growth history retained without hard delete.

Score: **0–100** per dimension. **Product-grade bar** = every dimension ≥ 80 and no open P0.

---

## Dimensions

| Dimension | Score | Bar 80? | Notes |
|-----------|------:|:-------:|-------|
| **1. Evidence SSOT** | 90 | yes | Dialogue canonical + AgentsView RO; Google light present |
| **2. Knowledge content** | 85 | yes | 30k+ KU; incremental extract path works |
| **3. Daily product CLI** | 88 | yes | `pk-sync` + full `pk-ku` chain; policy via flags |
| **4. Retrieval layered** | 82 | yes | KU→dialogue→Google; fallback_policy=layered |
| **5. Publish / active safety** | 75 | **no** | Fail-closed promote OK; **active lag** (canary strict FAIL); full `--start` soft-ban OK |
| **6. Lifecycle / growth line** | 30 | **no** | Schema exists; **no product reconcile**; append-mostly |
| **7. Eval / canary** | 70 | **no** | LLM labels work; strict not green; Phase 17 human gold open |
| **8. Ops / docs** | 85 | yes | Runbooks + AGENTS; gap audit done |
| **9. Governance / tests** | 88 | yes | Full pytest green post-fix; preflight residual known |
| **10. Facade / debt** | 60 | **no** | domains facade window to 2026-08-13; shim cohort remains |

### Overall

| Metric | Value |
|--------|------:|
| Simple average | **~75** |
| Weighted (product daily = 2×, lifecycle 1.5×, publish 1.5×) | **~72** |
| P0 open | **1+** (active not on latest candidate; growth/conflict unsolved) |
| **Product-grade?** | **Not yet** |

---

## Gap to product-grade (what “还差多少”)

### Must close (blocks “daily product”)

| # | Gap | Phase 22 plan | Effort (order of) |
|---|-----|---------------|-------------------|
| G1 | Lifecycle reconcile without delete (supersede / conflict) | 22-01 | M |
| G2 | Growth-line read + retrieval current-only hardened | 22-02 | S–M |
| G3 | Canary critical triage → strict PASS or explicit hold | 22-03 | S |
| G4 | Promote latest candidate after PASS + watermark | 22-03 ops | S |
| G5 | Facade import cleanup for product path | 22-04 | M |

### Should close (product polish)

| # | Gap | Notes |
|---|-----|-------|
| G6 | Phase 17 gold/judge UAT residuals | Parallel track, not only 22 |
| G7 | `pk-ku doctor` / one-shot health | 22-04 |
| G8 | Subject coarse-to-fine retrieval (optional) | After 22-01/02 |

### Explicitly later / not product blockers

- Novel Arc/Global memory sidecar  
- Physical delete of archive quarantine  
- Full domains facade directory removal (date gate 2026-08-13)

---

## Estimated distance

| If we complete… | Expected overall |
|-----------------|-----------------:|
| Now | ~72–75 |
| Phase 22 plans 01–03 only | **~82–85** (product-daily usable with growth line) |
| Phase 22 + Phase 17 human checkpoints | **~88–90** (eval-grade product) |
| + facade retire + doctor | **~90–92** |

**Rough calendar (1 focused engineer / strong agent loop):**

- 22-01: 2–4 days  
- 22-02: 1–2 days  
- 22-03: 1–2 days (ops can be same day once labels OK)  
- 22-04: 2–3 days  

**~1.5–2 weeks** to clear “product-daily bar” if Phase 17 gold is deferred.

---

## Definition of Done — product-grade (local)

1. Operator runs daily: `pk-sync` → `pk-ku` full chain **without editing code**.  
2. New chats become KU without full re-extract.  
3. Conflicts/outdated claims marked, **not deleted**; growth line query works.  
4. Retrieval: current KU first, leaf fallback guaranteed by test.  
5. Active promote only after canary/eval PASS (or documented forensics escape).  
6. pytest + health smoke green; docs match CLI.

---

## Next action

Execute **Phase 22** starting with **22-01** (`gsd-plan-phase` detail already outlined; implement via `gsd-execute-phase 22` when ready).
