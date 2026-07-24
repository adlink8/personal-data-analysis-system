---
phase: 37-authority-aware-state-external-and-evidence
status: planned
verification_mode: future_execution
requirements:
  STATE-01: planned
  STATE-02: planned
  STATE-03: planned
  EVID-01: planned
technical_status: not_run
security_status: not_run
---

# Phase 37: Authority-aware State, External and Evidence — Verification Plan

## Completion Conditions

| Requirement | Future acceptance evidence |
|---|---|
| STATE-01 | Overview and State pages distinguish fact, observation, inference, forecast, recommendation, confirmation, conflict and history. |
| STATE-02 | Personal and External authorities stay visibly separate and snapshot/checksum/freshness values come only from the server. |
| STATE-03 | Missing, stale, partial, conflict and mismatch states remain readable, explainable and read-only. |
| EVID-01 | Stable-reference evidence resolution is a same-origin GET path with authority/snapshot binding and typed recovery. |

## Automated Gates

1. Python contract tests for state/external/evidence DTOs, snapshot/checksum binding, allowlisted stable references and reject-on-mismatch behavior.
2. Component tests for claim badges, lifecycle states, empty/partial/stale/conflict rendering and long Chinese/ID layouts.
3. Evidence Drawer tests for keyboard open/close/focus restoration, GET-only network behavior and absence of raw evidence, confirmation material or provider payload.
4. Decision Workspace tests proving every session/action/outcome/prepare/confirm/execute entry remains hidden or disabled in this phase; Phase 38 is the only restoration point.
5. Widget diagnostic tests for configured origin, minimal sandbox/referrer policy, non-empty timeout recovery and visible non-SSOT labeling.

## Required Negative Evidence

| Scenario | Expected result |
|---|---|
| Stable reference bound to another snapshot | Resolver fails closed with typed read-only recovery. |
| Personal or External authority unavailable | Existing page stays readable; no browser recomputation or write CTA. |
| Widget loads but authority is stale | Widget is never treated as authority success. |
| Decision evidence is insufficient | Evidence may be viewed; no orchestration route is reachable. |

## Human Check

Open one Personal, one External and one Decision object; verify that a person can see whether each statement is a current fact, historical item or candidate and can open evidence without exposing raw private content.

## Passing Rule

All four requirements pass only if the browser remains read-only on all authority and decision paths. A reachable write control is a blocking failure, even if evidence rendering succeeds.

