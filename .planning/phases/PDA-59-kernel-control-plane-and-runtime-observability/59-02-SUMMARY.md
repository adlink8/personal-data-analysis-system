---
phase: 59
plan: 02
subsystem: operation-observability
tags: [projection, cockpit, same-origin, metadata-only, recovery]
requires: [59-01]
provides: [pi-operation-projection, cockpit-operation-controls, kernel-operation-routes]
affects: [60]
tech-stack:
  added: []
  patterns: [server-owned-projection, expected-state-command, truthful-offline]
key-files:
  created:
    - src/personal_knowledge/services/pi_operation_projection.py
    - tests/contract/test_pi_operation_projection.py
    - tests/integration/test_pi_runtime_control.py
    - apps/personal_decision_cockpit/src/test/PiOperationStatus.test.tsx
  modified:
    - src/personal_knowledge/services/api_server.py
    - apps/personal_intelligence_kernel/src/kernel-host.mjs
    - apps/personal_intelligence_kernel/src/server.mjs
    - apps/personal_decision_cockpit/src/api/schemas.ts
    - apps/personal_decision_cockpit/src/api/hooks.ts
    - apps/personal_decision_cockpit/src/pages/system/SystemPage.tsx
requirements-completed: [OPS-02]
duration: 30 min
completed: 2026-08-05
---

# Phase 59 Plan 02: Operation projection, Cockpit controls and recovery integration

Added same-origin metadata-only operation list/detail projections and guarded
cancel/resume/reconcile routes. The Python API never talks to Provider, Tool or
database directly for these controls; it proxies typed Kernel operation
endpoints and reports offline/degraded states honestly.

The System page now distinguishes all six operation planes and displays state,
version, budget and safe recovery actions. Commands carry expected version and
deterministic idempotency keys. Prompts, response bodies, credentials,
personal content and local paths are excluded from the projection and UI.

The Kernel HTTP surface exposes `/v1/operations` and binds task execution to
the sole Kernel control model with metadata receipts. The route wiring is a
small coordination addition beyond the plan's listed files and does not add a
second runtime or authority.

## Verification

- `python -m pytest tests/contract/test_pi_operation_projection.py tests/integration/test_pi_runtime_control.py -q` — 5 passed.
- `npm test --prefix apps/personal_decision_cockpit -- --run PiOperationStatus` — 1 passed.
- `npm run build --prefix apps/personal_decision_cockpit` — passed.
- `python -m pytest tests/contract/test_pi_kernel_host.py tests/contract/test_pi_cockpit_transport.py -q` — 6 passed.

## Self-Check: PASSED

- Implementation commit: pending (recorded after batch commit)
- Direct UI-to-provider/authority calls: 0.
- Projection body/credential/path leakage: 0.
- Local Pi/second coordinator dependency: 0.
