---
gsd_state_version: 1.0
milestone: v1.1
milestone_name: Knowledge Unit Evaluation & Quality
status: executing
last_updated: "2026-07-15T00:02:26.704Z"
last_activity: 2026-07-15 -- Phase 21 execution started
progress:
  total_phases: 23
  completed_phases: 15
  total_plans: 50
  completed_plans: 41
  percent: 65
---

# Project State

## Milestone

**v1.1 executing:** Knowledge Unit Evaluation & Quality (Phase 17 code complete; human gold/judge/UAT residuals). Phase 18–20 complete; live data on `data/`/`var/`/`archive/`.

## Authoritative surfaces (Phase 20 cutover)

| Layer | Path / surface |
|-------|----------------|
| Dialogue SSOT | `data/canonical/agent/structured/db/agent_conversations.sqlite` |
| Knowledge SSOT | `canonical_knowledge_units` + active KU collection |
| Google light | `data/canonical/google/structured/db/google_data.sqlite` |
| Unified | `var/db/personal_system.sqlite` |
| Active KU | `knowledge_units_205bff9560b9_20260712142938` (30,774；L1+L2) @ `var/db/knowledge_index_active.txt` |
| Eval registry | `var/db/evaluation_registry.sqlite` |
| Eval reports | `var/reports/analysis/evaluations/` |
| AgentsView live | `%USERPROFILE%/.agentsview/sessions.db` (**protected-external**) |

## Done (latest)

- **Phase 20 full apply** (2026-07-13, user 全部批准):
  - agent-google-imports (5 ops), var (11 ops), archive (3 ops) — all **applied**
  - live: `data/`, `var/db`, `var/runtime`, `var/reports`, `archive/quarantine/_recycle`
  - post_apply_verify **PASS**; integrity ok; KU 30774; active pointer unchanged
  - journals: `var/phase20-journals/`; source backups `*.bak-phase20` retained
  - AgentsView still external-only

- **Phase 19 plans 01–05 complete and verified** (2026-07-13):
  - 376 physical source moves; `integration/scripts/*.py=0`
  - 467 passed, 1 skipped；Node 10/10；preflight 12/12
  - fixed-point final inventory 16,968 nodes；16,967/16,967 non-Git disposition coverage 100%
  - consolidated recovery SSOT 144 moves + 197 rewrites；rollback/reapply PASS
  - HIGH historical replay debt retained; no missing intermediate bytes fabricated

- **Phase 18 plans 01–06 complete and verified** (2026-07-13):
  - 16,163 governed nodes；coverage/metadata/lineage 100%
  - 12/12 governance preflight gates PASS；privacy violations 0
  - user-approved empty migration: 0 operations, 0 actions, active/private untouched
  - full pytest PASS（448 collected，1 skipped）；Node 10/10 PASS

- **Phase 17 plans 01–04 implemented** (2026-07-13):
  - contracts, L2 lineage 768+47=815, extraction quality
  - five-mode retrieval + bootstrap metrics + immutable registry
  - answer eval + HTML/PNG report (project-local)
  - fail-closed gate + promote `--require-eval-pass`
  - tests: `tests/test_knowledge_eval_*.py` green
- Offline full + live retrieval-only runs executed; gate **FAIL** as expected on mixed suite; **active unchanged**

## Remaining human checkpoints

1. Label real cross-turn gold (≥30) in private suite
2. Judge calibration κ/ρ ≥ 0.7 before judge-in-gate
3. Fill `17-UAT.md` sandbox promote/rollback sign-off

## Verification commands

```powershell
python -m pytest -q tests/test_knowledge_eval_*.py
python integration/scripts/evaluation/reconcile_l2_lineage.py --check
python integration/scripts/evaluation/run_knowledge_eval.py --config integration/evals/knowledge_units/eval_v1.yaml --full --render --gate --dry-run --offline
python integration/scripts/evaluation/run_knowledge_eval.py --config integration/evals/knowledge_units/eval_v1.yaml --retrieval-only --render --gate
```

## Current Position

Phase: 21 (Architectural Alignment - Domains Slimming) — EXECUTING
Plan: 1 of 4
Status: Executing Phase 21
Last activity: 2026-07-15 -- Phase 21 execution started
