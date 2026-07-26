---
phase: 37-authority-aware-state-external-and-evidence
status: passed
verification_mode: executed
verified: 2026-07-27
verifier: independent gsd-verifier subagent (read-only, reran all gates)
requirements:
  STATE-01: passed
  STATE-02: passed
  STATE-03: passed
  EVID-01: passed
technical_status: passed
security_status: passed
---

# Phase 37: Authority-aware State, External and Evidence — Verification Plan

## Executed Verification Record (2026-07-27)

Independent read-only verification (gsd-verifier) reran all gates after plans 37-01/02/03; executor
summaries were not trusted as evidence.

| Gate | Result |
|---|---|
| Python contract tests (ui_projection ×4 + evidence + transport security, PYTHONPATH=src) | **102 passed, 0 failed** — includes the full-DB fingerprint test `test_all_projection_operations_are_physically_read_only` with no exclusion (the earlier flake was attributed to a concurrent `pk-ku extract`; that process finished and the test passes cleanly) |
| Frontend Vitest (`npm run test -- --run`) | **203/203 passed** (19 files) |
| Frontend build (`tsc --noEmit` + `vite build`) | Succeeded |
| Requirement verdicts | STATE-01 / STATE-02 / STATE-03 / EVID-01 all **PASS** (evidence: ClaimLifecycleBadges closed-set grouping; canonical External DTO with server-only freshness and explicit-partial required fields; assertionReadinessNote blocking conflict/stale/no-evidence claims from confirmation use; evidence_resolve six-state vocabulary, GET-only route, WidgetDiagnosticCard sandbox + no-referrer + non-empty recovery + non-SSOT labeling) |
| Git audit | 12 commits (af7cc05..14a22c4) all plan-scoped; zero contamination from the concurrent session's working-tree changes; 3 SUMMARYs committed and consistent with code |

Commits: 37-01 `af7cc05`/`ccf18c2`/`ccd47ff`/`4126875`; 37-02 `dd9716e`/`8105b6c`/`7f02d57`/`61e7538`;
37-03 `8040c66`/`fee86ad`/`79828b9`/`14a22c4`.

Residual notes: ROADMAP/STATE progress lines were deferred during execution due to the shared
working tree and folded in at phase close; the legacy MCP widget remains a diagnostic/historical
view only. Phase 38 should layer readiness/truth gates onto the existing DecisionWorkspacePage
guarded entries and reuse — not modify — this phase's read-only evidence paths.

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

