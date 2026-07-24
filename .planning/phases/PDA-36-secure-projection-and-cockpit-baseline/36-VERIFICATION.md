---
phase: 36-secure-projection-and-cockpit-baseline
status: planned
verification_mode: future_execution
requirements:
  CCK-01: planned
  CCK-02: planned
  CCK-03: planned
  CCK-04: planned
technical_status: not_run
security_status: not_run
---

# Phase 36: Secure Projection and Cockpit Baseline — Verification Plan

## Completion Conditions

| Requirement | Future acceptance evidence |
|---|---|
| CCK-01 | Every `/ui/*` response has the v1 envelope, endpoint-specific operation, stable authority/snapshot metadata, safe limitations and no direct authority mutation. |
| CCK-02 | Browser-originated mutations reject disallowed origins before orchestration; only the configured same-origin Cockpit route is permitted. |
| CCK-03 | Zod schemas reject cross-endpoint/version drift and the browser uses relative same-origin API paths without duplicating authority state. |
| CCK-04 | README/runbook, tracked tests and checked-in baseline describe WIP honestly; no untracked Cockpit artifact is claimed as shipped. |

## Automated Gates

1. Python contract tests for CORS/Origin rejection, Projection physical read-only behavior, safe error mapping and all nine endpoint envelopes.
2. Cockpit Zod/unit tests for exact operation names, including `system.status.get`; negative tests must reject altered schema version or endpoint payload.
3. Repository tests proving no UI route calls a provider, direct authority write, automatic promotion or external action.
4. `git diff --check`, no-WIP/placeholder baseline scan, and a documentation claim check against real test/build output.

## Required Negative Evidence

| Scenario | Expected result |
|---|---|
| Cross-origin `POST`/preflight | Rejected; all authority fingerprints unchanged. |
| Projection exception | Typed safe limitation; no `str(exc)`, path, HMAC, raw evidence or provider body. |
| Wrong operation/schema | Browser parse failure; no fallback to a different endpoint. |
| Missing/partial authority | Read-only recovery; no fabricated current data. |

## Human Check

Review the `/app` entry while a service is unavailable and confirm the user sees a bounded recovery message, not a false healthy state. This is a display check only and must not write a live authority.

## Passing Rule

All four requirements need passing automated evidence; the cross-origin mutation test and safe-error inspection are blocking security gates. Until then this document remains `planned`, and neither the Cockpit nor Phase 36 may be described as delivered.

