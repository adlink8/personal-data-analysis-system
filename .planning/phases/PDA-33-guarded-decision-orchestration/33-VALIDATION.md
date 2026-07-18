---
phase: 33
slug: guarded-decision-orchestration
status: draft
nyquist: enabled
created: 2026-07-19
---

# Phase 33 Validation Strategy

## Test Layers

| Layer | Scope | Required proof |
|---|---|---|
| Unit | checksums, token, risk, state table | every stable abstention code and valid transition |
| Integration | SQLite concurrency and authority bridges | one append/call under replay and concurrent attempts |
| Contract | Service, REST, stdio MCP, HTTP MCP | semantic parity, truthful annotations, typed errors |
| Acceptance | disposable full flow | complete stub path plus zero-side-effect negative matrix |

## Blocking Gates

1. Prepare changes no authority and performs no provider/network call.
2. Every mutation rejects missing, expired or drifted confirmation before effects.
3. Exact replay returns the original result; conflicting replay and stale sequence abstain.
4. Provider reservation proves at-most-once behavior, including unknown-outcome recovery.
5. High-risk, out-of-domain, evidence conflict and illegal transitions leave all fingerprints unchanged.
6. Calibration output remains non-causal, non-promoting and may honestly abstain/INCONCLUSIVE.
7. All existing Phase 29–32 tests continue passing.

## Commands

- `python -m pytest tests/unit/test_orchestration_core.py -q`
- `python -m pytest tests/integration/test_orchestration_replay.py tests/integration/test_orchestration_flow.py -q`
- `python -m pytest tests/contract/test_orchestration_interfaces.py -q`
- `node --test apps/personal_data_chatgpt/test/orchestration-tools.test.mjs`
