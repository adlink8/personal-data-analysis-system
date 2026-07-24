---
phase: 39-feedback-proactive-and-runtime-truthfulness
status: planned
verification_mode: future_execution
requirements:
  FDB-01: planned
  FDB-02: planned
  RUN-01: planned
technical_status: not_run
security_status: not_run
---

# Phase 39: Feedback, Proactive and Runtime Truthfulness — Verification Plan

## Completion Conditions

| Requirement | Future acceptance evidence |
|---|---|
| FDB-01 | The complete append-only Recommendation → Decision → Action → Outcome → Effectiveness → Calibration history is browsable through server-owned stable cursors, with non-causal/sample limitations. |
| FDB-02 | Proactive/Calibration UI preserves final score, support, suppression/restore history and limitations, but creates no new REST control or automatic action. |
| RUN-01 | REST, MCP, Tunnel, Chroma, authority freshness and supervisor last-observed state are separately represented with honest degraded recovery. |

## Automated Gates

1. Authority/projection tests for stable newest-first order plus timestamp/ID tie-breaker, opaque cursor, cross-page no-repeat/no-omission/no-reorder, cursor mismatch fail-closed and zero writes.
2. Component tests for missing stages, `causal_claim=false`, unknown/small samples, PASS/FAIL/INCONCLUSIVE, partial records, long limitations and cursor-failure recovery.
3. Proactive and Calibration tests for `importance.final_score`, user-control history, no automatic promotion/external action and no UI-derived truth state.
4. Runtime matrix tests stubbing REST/MCP/Tunnel/Chroma/authority failures independently; `agent-stack.json` must be shown only as last observed.
5. Read-only proof: all Phase 39 projection reads leave every authority fingerprint unchanged and expose no raw exception/private material.

## Required Negative Evidence

| Scenario | Expected result |
|---|---|
| Invalid/expired/wrong-snapshot cursor | Typed read-only recovery; already-read history stays visible. |
| Positive outcome on one sample | Explicitly non-causal and insufficient for promotion. |
| Proactive data absent or control suppressed | Clear scope/cooldown/suppression state; no new control API call. |
| Chroma/MCP/Tunnel offline | Scoped degraded card; no claim that supervisor last record proves current health. |

## Human Check

Browse more than one feedback page in a disposable fixture and inspect the beginning/end of the timeline. Confirm no duplicate records and that current runtime observations do not claim a stopped service is healthy.

## Passing Rule

Any cursor gap/reorder, causal overclaim, implicit control write or conflation of last-observed with current health blocks the phase.

