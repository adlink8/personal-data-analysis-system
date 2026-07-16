---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Knowledge Unit Evaluation & Quality → product hardening
status: planning
last_updated: "2026-07-16T11:48:00+08:00"
last_activity: 2026-07-16 -- Phase 22 planned (lifecycle/growth line)
progress:
  total_phases: 24
  completed_phases: 21
  total_plans: 54
  completed_plans: 49
  percent: 72
---

# Project State

## Milestone

**v1.1 executing → product hardening:** Phase 17 human checkpoints still open; Phases 18–21 complete; **Phase 22 planned** (KU lifecycle / growth line / product readiness).

## Authoritative surfaces

| Layer | Path / surface |
|-------|----------------|
| Dialogue SSOT | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Knowledge SSOT | `canonical_knowledge_units` + **active** Chroma collection |
| Active KU (live) | `knowledge_units_205bff9560b9_20260712142938` @ `var/db/knowledge_index_active.txt` |
| Candidate (pending) | `knowledge_units_ir_4cd8af4ad_20260716020508` (canary 30/30 labeled, strict FAIL 1×wrong) |
| Product CLI | `pk-sync`, `pk-ku` (incl. canary `--label-with-llm`, watermark, promote fail-closed) |

## Done (latest, 2026-07-16 product ops)

- pk-sync / pk-ku product packaging; incremental extract; publish additive; vector candidate
- LLM canary labeling; promote default require-eval; full inventory `--start` soft-ban
- Safe cleanup: bak-phase20 quarantined; full pytest green after governance test fix
- GSD codebase map refresh; gap audit + auto-test reports

## Current Position

**Phase: 22 (ku-lifecycle-growth-line) — PLANNED**  
Plans: 22-01..04 outlined under `.planning/phases/22-ku-lifecycle-growth-line/`  
Readiness: `.planning/PRODUCT-READINESS.md` (~72 weighted; product-grade **not yet**)  
Next: implement 22-01 reconcile dry-run CLI, or discuss-phase refinements if scope changes

## Remaining human / product checkpoints

1. Phase 22: lifecycle reconcile + growth line (no delete)
2. Canary critical (1× wrong) triage → strict PASS → promote → watermark
3. Phase 17: gold/judge/UAT residuals (parallel)
4. 2026-08-13: domains facade removal window

## Verification snapshot

```powershell
python -m pytest -q tests --tb=line   # green as of 2026-07-16 post-fix
pk-ku workflow
pk-ku watermark   # read-only
```
