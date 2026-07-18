---
phase: 29
status: planned
created: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Context

## Boundary

Phase 29 creates immutable, non-authoritative Decision Analysis Candidates. An
LLM may propose analysis, but deterministic code alone decides whether a
candidate is admissible. No model output becomes Personal KU/State, External
Fact, user value confirmation, final decision, action, or command.

## Locked decisions

- Bind the exact validated `DecisionContextBinding` from Phase 28.
- Require user-confirmed goal, constraints, weights and low-risk budget before
  generation.
- Preserve a no-action baseline and explicit options, benefits, costs, risks,
  opportunity costs, reversibility, assumptions, uncertainty, missing
  information and stop conditions.
- Every factual claim uses a typed Personal or External evidence reference from
  an input allowlist; schema validity alone is insufficient.
- Privacy, freshness, conflict, region, prompt-injection and domain-risk gates
  are deterministic and fail closed to `abstain`.
- Store provider/model, prompt/schema/policy versions, sampling parameters,
  token/cost/latency telemetry and request/response checksums, never credentials
  or hidden reasoning.
- A replayable stub proves determinism; milestone acceptance additionally
  requires one explicitly authorized real LLM call.

## Reuse

- `intelligence/decision/context_binding.py` for dual-snapshot authority.
- Phase 26 decision append-only and user-confirmation patterns.
- `core/llm.py` only behind a typed provider interface.
- `core/privacy_guard.py` and memory candidate allowlisted-reference validation.

## Deferred

Real recommendation selection, user decision/action/outcome and comparative
calibration belong to Phases 30–31.
