---
phase: 31
status: planned
created: 2026-07-18
requirements: [PDI-08]
---

# Phase 31 Context

## Boundary

Phase 31 evaluates the Phase 30 low-risk `project` pilot. It compares an
evidence-bound personalized candidate with a generic candidate under one
pre-registered protocol. It may propose a new candidate policy, prompt or
threshold version, but it never rewrites historical runs or self-promotes a
version into authority.

## Locked decisions

- Freeze cohort membership, question, External Snapshot, observation window,
  exclusions, metrics and thresholds before the first production candidate.
- Personalized and generic arms receive the same question, external facts,
  provider/model, schema, sampling and budget; only the generic arm is denied
  Personal Snapshot/history.
- Keep arm identity blinded during rubric scoring where technically possible,
  and preserve exact request/response and evaluator checksums.
- Report acceptance, execution, completion, time/cost deviation, quality,
  satisfaction, side effects, regret and abstention separately; do not collapse
  them into one opaque score.
- Small samples, missing windows, protocol deviations or ambiguous/confounded
  outcomes produce `INCONCLUSIVE`, never an inferred win or causal claim.
- Calibration creates an immutable proposal against a named parent version.
  Promotion requires separate evaluation, rollback proof and explicit user
  acceptance; historical candidates, outcomes and measurements never change.
- Product UAT must cover explanation, correction, reject/defer, revoke/restore,
  privacy, zero external execution and exact audit reconstruction.

## Canonical references

- `.planning/REQUIREMENTS.md` — PDI-08 and milestone exclusions.
- `.planning/ROADMAP.md` — Phase 31 goal and acceptance criteria.
- `.planning/phases/29-structured-llm-decision-analysis/29-CONTEXT.md` — model,
  evidence and candidate-authority boundaries.
- `.planning/phases/30-low-risk-project-decision-pilot/30-CONTEXT.md` — real
  pilot chain and observation-window contract.
- `src/personal_knowledge/intelligence/decision/effectiveness.py` — existing
  non-causal outcome and calibration semantics.

## Deferred

Multi-domain rollout, health/finance/relationship decisions, automated policy
promotion and claims of population-level or causal benefit remain out of scope.
