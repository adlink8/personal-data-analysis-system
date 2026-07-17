---
phase: 23
slug: composite-ssot-snapshot-integrity
created: 2026-07-17
status: active
---

# Phase 23 Validation Strategy

## Fast feedback

- Registry and schema unit tests after every task.
- Snapshot/evidence targeted integration tests after each plan.
- No test may require private payloads or mutate the production active snapshot.

## Plan gates

| Plan | Required proof |
|---|---|
| 23-01 | Registry validation + schema migration tests + bootstrap dry-run |
| 23-02 | Fault-injected activation/rollback tests + legacy pointer parity |
| 23-03 | Evidence resolver and same-snapshot retrieval contract tests |
| 23-04 | Product sync/version/watermark idempotency + doctor/governance gates |

## Phase gate

1. Targeted Phase 23 tests pass.
2. Full pytest passes with only documented skips.
3. Governance preflight passes all gates.
4. Read-only live status reports one active snapshot or a clearly non-active bootstrap draft with explicit missing proofs.
5. No paid call, candidate promotion, watermark advance, AgentView write or history deletion occurs during verification.
