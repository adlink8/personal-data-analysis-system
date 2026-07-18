---
phase: 30
status: planned
created: 2026-07-18
requirements: [PDI-07]
---

# Phase 30 Context

## Boundary

Phase 30 converts one admitted Phase 29 analysis candidate into a real,
user-owned, low-risk `project` decision case and follows it through decision,
manual action and observed outcome. The system records and explains the chain;
it never performs an external action or treats model output as the decision.

## Locked decisions

- Use one real project decision with an explicit no-action baseline, confirmed
  goal, weights, constraints and risk budget.
- Freeze the exact Personal and External Snapshot IDs/hashes and the admitted
  analysis request/response/candidate checksums before recommendation creation.
- Only deterministic code may translate an admitted analysis option into a
  recommendation candidate. The user alone accepts, rejects or defers it.
- Action records are user-reported/manual observations, never commands,
  messages, purchases, deployments or connector calls.
- Predeclare metric, baseline, target, unit, observation window and collection
  source before action. Missing or incomplete windows remain `inconclusive`.
- Record time/cost estimates and actuals, completion, quality, satisfaction,
  side effects, regret and confounders separately.
- Include at least one real control path (`abstain`, `reject` or `defer`) and
  prove correction, revoke/restore, snapshot rollback and forward-restore.
- All transitions are append-only, checksum chained, idempotent and reversible
  by compensating events. Personal, External and Analysis authorities remain
  unchanged by pilot writes.

## Canonical references

- `.planning/REQUIREMENTS.md` — PDI-07 and out-of-scope boundaries.
- `.planning/ROADMAP.md` — Phase 30 goal and success criteria.
- `.planning/phases/29-structured-llm-decision-analysis/29-CONTEXT.md` — admitted
  candidate and deterministic-gate contract.
- `src/personal_knowledge/intelligence/decision/state_machine.py` — existing
  user decision/action/outcome event semantics.
- `src/personal_knowledge/intelligence/decision/effectiveness.py` — non-causal
  observation-window assessment.

## Deferred

Generic-versus-personalized comparison, policy calibration, multi-domain
rollout and any automated external action belong outside this phase.
