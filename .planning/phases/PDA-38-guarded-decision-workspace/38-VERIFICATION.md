---
phase: 38-guarded-decision-workspace
status: verified
verification_mode: automated_component_contract
requirements:
  DEC-01: passed
  DEC-02: passed
  DEC-03: passed
technical_status: passed
security_status: contract_scoped_passed
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

The browser contract and component tests cover this flow, including exact preview, cancellation, explicit confirmation and replay rendering. A real browser run on a disposable fixture remains a Phase 40 human-UAT gate; it is not claimed here.

## Passing Rule

DEC-02 and DEC-03 passed the automated component/contract negative matrix. No silent write, payload substitution, cross-origin mutation, duplicate event or automatic provider retry was observed in the executed evidence. Phase 38 is technically verified; milestone acceptance still depends on the outstanding Phase 40 human-UAT items.

