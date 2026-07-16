---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Knowledge Unit Evaluation & Quality → product hardening
status: executing
last_updated: "2026-07-16T18:30:00+08:00"
last_activity: 2026-07-16 -- Phase 22 plans 01-04 implemented (reconcile/history/canary triage/doctor)
progress:
  total_phases: 24
  completed_phases: 21
  total_plans: 54
  completed_plans: 53
  percent: 78
---

# Project State

## Milestone

**v1.1 executing → product hardening:** Phase 17 human checkpoints still open; Phases 18–21 complete; **Phase 22 plans 01–04 implemented** (lifecycle growth line + doctor). Remaining: ops promote after canary strict PASS; facade retire by 2026-08-13.

## Authoritative surfaces

| Layer | Path / surface |
|-------|----------------|
| Dialogue SSOT | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Knowledge SSOT | `canonical_knowledge_units` + **active** Chroma collection |
| Active KU (live) | pointer @ `var/db/knowledge_index_active.txt` (doctor checks) |
| Candidate (pending) | promote only after canary strict PASS + eval |
| Product CLI | `pk-sync`, `pk-ku` (inspect…promote, watermark, **reconcile**, **history**, **doctor**) |

## Phase 22 plan status

| Plan | Title | Status |
|------|-------|--------|
| **22-01** | Lifecycle reconcile dry-run + CLI (zero DELETE) | **done** — `pk-ku reconcile` |
| **22-02** | Growth-line history read | **done** — `pk-ku history` |
| **22-03** | Canary critical triage / label path | **done** (CLI); ops strict PASS still open |
| **22-04** | Facade inventory + doctor + readiness gates | **done** — `pk-ku doctor`, `22-FACADE-INVENTORY.md` |

## Done (latest, 2026-07-16 product ops)

- pk-sync / pk-ku product packaging; incremental extract; publish additive; vector candidate
- LLM canary labeling; promote default require-eval; full inventory `--start` soft-ban
- **22-01/02:** lifecycle reconcile + growth-line history (never DELETE)
- **22-04:** `pk-ku doctor` read-only health; facade inventory (16 import lines / 10 files)
- Safe cleanup: bak-phase20 quarantined; readiness scorecard updated (~81 weighted)

## Current Position

**Phase: 22 (ku-lifecycle-growth-line) — PLANS 01–04 CODE COMPLETE**  
Readiness: `.planning/PRODUCT-READINESS.md` (**~81** weighted; product-grade **not yet** — active lag + lifecycle bar 80 + facade)  
Next ops: canary strict PASS → promote → watermark; optional reconcile write with `--i-know`

## Remaining human / product checkpoints

1. **Phase 17 code complete; human checkpoints** still open (gold/judge/UAT sign-off — parallel to Phase 22)
2. Canary critical residual → strict PASS → promote → watermark  
3. 2026-08-13: domains facade removal (inventory owned; mass rewrite deferred)  
4. Selective `reconcile --write --i-know` after dry-run review

## Verification snapshot

```powershell
$env:PYTHONPATH="D:\ADLINK\数据分析\src"
python -m personal_knowledge.application.ku doctor
python -m personal_knowledge.application.ku workflow
python -m personal_knowledge.application.ku watermark   # read-only
python -m pytest -q tests/unit/test_doctor_ku.py tests/unit/test_pk_ku_cli.py -k "doctor or history or reconcile" --tb=short
```
