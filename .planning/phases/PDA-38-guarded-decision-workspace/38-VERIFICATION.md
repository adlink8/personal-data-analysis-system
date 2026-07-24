---
phase: 38-guarded-decision-workspace
status: planned
verification_mode: future_execution
requirements:
  DEC-01: planned
  DEC-02: planned
  DEC-03: planned
technical_status: not_run
security_status: not_run
---

# Phase 38: Guarded Decision Workspace — Verification Plan

## Completion Conditions

| Requirement | Future acceptance evidence |
|---|---|
| DEC-01 | Workspace shows complete alternatives, baseline, assumptions, counterevidence, stop conditions and limitations; recommendation remains a candidate. |
| DEC-02 | Only eligible `project + low` sessions follow prepare → exact preview → explicit confirm → receipt/replay with zero side effects on cancellation. |
| DEC-03 | Typed recovery handles stale, integrity, conflict, sequence, actor mismatch and provider-outcome-unknown without automatic retry or data disclosure. |

## Automated Gates

1. Decision Workspace component tests for all comparison fields, candidate labeling and truth-gate denial of every ineligible combination.
2. Orchestration client/Confirm Drawer/Session Page tests proving exact payload forwarding, explicit operation-specific confirmation, volatile actor behavior, double-click protection and focus handling.
3. Python contract/integration/E2E fixture tests for cross-origin rejection, preview tamper/expiry, illegal transition, same-key replay, changed-payload conflict and provider outcome unknown.
4. Security assertions: no browser provider calls, no local persistence of actor identity, no preview/HMAC/confirmation/raw-evidence leakage in DOM/URL/console/test artifacts.

## Required Negative Evidence

| Scenario | Expected result |
|---|---|
| partial/stale/conflict/insufficient evidence | Read-only explanation; no prepare CTA. |
| Cancel/Esc/close confirmation | Zero POST and no event. |
| Exact repeated confirm | Same event/checksum/sequence with `replayed=true`; no second write. |
| Refreshed actor or provider unknown | Resume/explain only; no automatic retry or substituted idempotency key. |

## Human Check

On a disposable fixture, inspect a preview before confirming: it must state the precise event, what will not happen, sequence/checksum and risk. Repeat the identical confirmation and verify that the receipt explicitly says it is a replay.

## Passing Rule

DEC-02 and DEC-03 cannot pass without the negative matrix. Any silent write, payload substitution, cross-origin mutation, duplicate event or automatic provider retry blocks the phase.

