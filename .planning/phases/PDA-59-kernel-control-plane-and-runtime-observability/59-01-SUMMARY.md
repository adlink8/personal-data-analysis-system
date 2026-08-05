---
phase: 59
plan: 01
subsystem: kernel-control
tags: [operation-envelope, reducer, cancel, resume, reconcile, outcome-unknown]
requires: [58-02]
provides: [pi-kernel-operation-v1, runtime-control, receipt-first-reconciliation]
affects: [59-02, 60]
tech-stack:
  added: []
  patterns: [expected-version-cas, idempotent-command-replay, metadata-only-events]
key-files:
  created:
    - apps/personal_intelligence_kernel/src/control/operation-schema.mjs
    - apps/personal_intelligence_kernel/src/control/runtime-control.mjs
    - apps/personal_intelligence_kernel/test/runtime-control.test.mjs
  modified:
    - apps/personal_intelligence_kernel/src/events/schema.mjs
requirements-completed: [OPS-02]
duration: 25 min
completed: 2026-08-05
---

# Phase 59 Plan 01: Kernel operation control and recovery model

Added a strict `pi-kernel-operation-v1` envelope for kernel task/session/skill,
domain tool, provider and Python authority transaction planes. Every operation
is bound to task/session/correlation/idempotency metadata, expected version,
side-effect class, budget counters, receipt/fingerprint references and typed
recovery actions. Inline bodies, prompts, credentials and paths are rejected.

The deterministic reducer rejects stale or illegal transitions, replays the
same command idempotently, and exposes cancel/resume/reconcile as Kernel-owned
commands. `outcome_unknown` cannot resume blindly: receipt and fingerprint
evidence must first resolve it to succeeded, resumable or manual review.
Control events use the existing metadata-only event ledger schema.

## Verification

- `node --test apps/personal_intelligence_kernel/test/runtime-control.test.mjs` — 4 passed.
- `node --test .../runtime-control.test.mjs .../capability-registry.test.mjs` — 7 passed.
- No Local Pi launcher, RPC operator or ambient capability path was added.

## Self-Check: PASSED

- Implementation commit: 7dbac16
- Blind outcome-unknown retry: 0.
- Duplicate/stale state mutations: 0 accepted.
