---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Knowledge Unit Evaluation & Quality → product hardening
status: executing
last_updated: "2026-07-17T13:35:53.690Z"
progress:
  total_phases: 29
  completed_phases: 17
  total_plans: 58
  completed_plans: 51
  percent: 59
---

# Project State

## Milestone

**v1.1 product hardening:** Phase 17 human checkpoints still open; Phases 18–21 complete; **Phase 22 plans 01–04 implemented**; **2026-07-16 ops close-out: canary strict PASS → promote active=ir_4cd8af → watermark advanced**.

## Authoritative surfaces

| Layer | Path / surface |
|-------|----------------|
| Dialogue SSOT | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Knowledge SSOT | `canonical_knowledge_units` + **active** Chroma collection |
| Active KU (live) | **`knowledge_units_ir_4cd8af4ad_20260716020508`** (promoted 2026-07-16; previous 205bff for rollback) |
| Watermark | matches current source checksum |
| Product CLI | `pk-sync`, `pk-ku` (inspect…promote, watermark, **reconcile**, **history**, **doctor**) |

## Phase 22 plan status

| Plan | Title | Status |
|------|-------|--------|
| **22-01** | Lifecycle reconcile dry-run + CLI (zero DELETE) | **done** — `pk-ku reconcile` |
| **22-02** | Growth-line history read | **done** — `pk-ku history` |
| **22-03** | Canary critical triage / label path | **done** (CLI + ops: strict PASS + promote) |
| **22-04** | Facade inventory + doctor + readiness gates | **done** — `pk-ku doctor`, `22-FACADE-INVENTORY.md` |

## Done (latest, 2026-07-16 product ops)

- pk-sync / pk-ku product packaging; incremental extract; publish additive; vector candidate
- LLM canary labeling; promote default require-eval; full inventory `--start` soft-ban
- **22-01/02:** lifecycle reconcile + growth-line history (never DELETE)
- **22-04:** `pk-ku doctor` read-only health; facade inventory (16 import lines / 10 files)
- Safe cleanup: bak-phase20 quarantined; readiness scorecard updated (~81 weighted)

## Current Position

Phase: 23 (Composite SSOT Snapshot Integrity) — EXECUTING
Plan: 3 of 4
**Phase: 22 (ku-lifecycle-growth-line) — PLANS 01–04 CODE COMPLETE + OPS CLOSED**  
Readiness: `.planning/PRODUCT-READINESS.md` (**~86** weighted; operationally usable, quality sign-off open)
Active: `knowledge_units_ir_4cd8af4ad_20260716020508`; watermark matches source.  
Next optional: `reconcile --write --i-know` after dry-run; Phase 17 human gold; facade retire 2026-08-13.

## Cross-cutting architecture/data governance audit

- **Authoritative issue inventory:** [`ARCHITECTURE-LAYERING-DATA-GOVERNANCE-AUDIT-2026-07-17.md`](./ARCHITECTURE-LAYERING-DATA-GOVERNANCE-AUDIT-2026-07-17.md)
- **Expected target gap:** [`TARGET-GAP-ANALYSIS-2026-07-17.md`](./TARGET-GAP-ANALYSIS-2026-07-17.md) — separately evaluates foundation integrity, v1.1 evaluation closure, stable knowledge-product readiness, and the long-term personal-intelligence loop.
- Scope: D/S/R/A layer separation, SQLite/Chroma composite SSOT, inventory/watermark/lifecycle integrity, evaluation evidence, repository and runtime drift.
- Initial verdict: **gaps_found**. The audit found disabled SQLite FK enforcement, 18,859 FK violations, Delta Inventory FK mismatch, and unsafe incremental inspection/execution boundaries.
- **2026-07-17 remediation:** unified Full/Delta Inventory registry migrated with verified backup; FK violations are 0; knowledge write connections enforce FK; doctor and publish/promote gates fail closed; inspect defaults to committed watermark; execution lists are no longer preview-truncated; governance preflight is 12/12 PASS.
- No reconcile write, additional promotion, watermark advance, pointer change, data delete, or compat/archive retirement was performed during remediation.

## Remaining human / product checkpoints

1. **Phase 17 code complete; human checkpoints** still open (gold/judge/UAT sign-off — parallel)
2. ~~Canary → promote → watermark~~ **DONE 2026-07-16** (active=ir_4cd8af; wm advanced)
3. 2026-08-13: domains facade removal (inventory owned; mass rewrite deferred)
4. Selective `reconcile --write --i-know` after dry-run review (optional)

Phase 17 evaluation evidence: `17-EVAL-REVIEW.md` scores coverage **74/100 NEEDS WORK**. Final scorer-v2/policy-v2 run `6d7233db5da0414c` has 178 rows but only 22 real scoreable gold cases and 0 real cross-turn gold; 150 synthetic shells are excluded from retrieval metrics. L1+L2 R@5 is 59.09%; exact L2-only (764/764) R@5 is 18.18%; secret provenance hits are 0. Candidate-scoped safety checks correctly FAIL on L2-only/Hybrid privacy and all candidate modes' no-answer FP, plus coverage/cross-turn/human-grounded requirements. The 58-case private dev calibration proved score-only abstention unsafe, so no threshold was deployed. Active is unchanged.

## Verification snapshot

```powershell
$env:PYTHONPATH="D:\ADLINK\数据分析\src"
python -m personal_knowledge.application.ku doctor
python -m personal_knowledge.application.ku workflow
python -m personal_knowledge.application.ku watermark   # read-only
python -m pytest -q
python -m personal_knowledge.governance.preflight
```

## Accumulated Context

### Roadmap Evolution

- Phase 23 added: Target A composite SSOT snapshot integrity
- Phase 24 added: Target B/C evaluation closure and lifecycle adoption
- Phase 25 added: Target D personal state and change intelligence
- Phase 26 added: Target D decision/action feedback loop
- Phase 27 added: Target D proactive multi-domain acceptance
