---
phase: 49-01
verified: 2026-08-04T00:00:00Z
status: gaps_found
score: 4/5 must-haves verified
overrides_applied: 0
gaps:
  - truth: "shutdown/dispose 对 abort、session.dispose、server.close 有 bounded timeout 且不会遗留资源"
    status: failed
    reason: "超时关闭后仍有活动 TCP 连接；Host 标记为 disposed，但未清理 server.close 未完成的连接。"
    artifacts:
      - path: "apps/personal_intelligence_kernel/src/kernel-host.mjs"
        issue: "closeServer 只等待 server.close 的回调或超时，不在超时后销毁仍存活的连接；shutdown 仍将 lifecycle 置为 disposed。"
    missing:
      - "超时后强制关闭/销毁所有活动连接，并验证 server 句柄与连接均已清理。"
deferred:
  - truth: "Pi 随产品服务受控启动和停止，成为唯一主 AI Session 与事件循环"
    addressed_in: "Phase 52"
    evidence: "49-CONTEXT.md 明确将加入 start-agent-stack.ps1 延至 Phase 52；49-01 仅建立独立 Host factory。"
---

# Phase 49-01 Verification Report

**Phase Goal:** 建立 project-owned event contract、append-only SQLite journal 和单一 Pi Kernel Host bootstrap。
**Verified:** 2026-08-04
**Status:** gaps_found
**Re-verification:** No — independent final verification of the 49-01 fix

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | D-01: Kernel is an isolated loopback host on `127.0.0.1:8790`. | ✓ VERIFIED | `kernel-host.mjs` fixes the default host/port and `assertLoopback` rejects non-loopback. Independent run reported `first_listening: true`, endpoint `127.0.0.1:8790`; port conflict returned `host_bind_failed`. |
| 2 | D-02: `pi_kernel_event_v1` owns the public event contract. | ✓ VERIFIED | `schema.mjs` defines the exact envelope keys, typed validation, forbidden inline fields, project-owned SDK normalization, and deterministic event ID. Full Node suite passed. |
| 3 | D-03: event identity and replay are deterministic. | ✓ VERIFIED | Schema tests cover stable IDs and changed bindings; journal tests cover duplicate replay, monotonic sequences, restart cursor replay, and integrity. |
| 4 | D-04: journal stores metadata references, not personal bodies. | ✓ VERIFIED | Journal schema has metadata/event JSON/checksum columns only; tests assert no body/content/prompt/completion/credential/path columns and no private-body serialization. |
| 5 | `shutdown`/`dispose` bounds abort, session disposal, and server close without resource leakage. | ✗ FAILED (BLOCKER) | Independent fake-session/open-socket check returned `{"lifecycle":"disposed","timed_out":true,"listening":false,"connections_after_shutdown":1}` after `shutdown(20)`. The method is bounded, but an active connection remains after disposal. |

**Score:** 4/5 truths verified

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `apps/personal_intelligence_kernel/src/events/schema.mjs` | Versioned deterministic event contract | ✓ VERIFIED | Substantive implementation; imported by journal and both event test paths. |
| `apps/personal_intelligence_kernel/src/events/journal.mjs` | Durable append-only SQLite journal | ✓ VERIFIED | Migration ledger, unique event/idempotency identities, checksum, replay/cursor, integrity check, append-only triggers. |
| `apps/personal_intelligence_kernel/src/kernel-host.mjs` | Contained loopback Host factory and lifecycle | ⚠️ PARTIAL | Startup, readiness, loopback bind, conflict failure and bounded waits work; timeout leaves an active connection. |
| `apps/personal_intelligence_kernel/test/event-schema.test.mjs` | Schema contract tests | ✓ VERIFIED | Included in full suite; schema behaviors pass. |
| `apps/personal_intelligence_kernel/test/event-journal.test.mjs` | Journal/Host tests | ✓ VERIFIED | 7/7 targeted tests pass, including `server.listening === true` and `provider_calls === 0`; timeout/port-conflict coverage is incomplete in the test file. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `kernel-host.mjs` | Phase 48 decision/resource policy | `readPhase48Decision`, `createContainedSession`, exact policy assertions | ✓ WIRED | Factory rejects missing/expired/non-accepted decision and policy mismatch before returning a Host. |
| `kernel-host.mjs` | `journal.mjs` | `EventJournal` construction, readiness integrity check, close on shutdown | ✓ WIRED | Host owns the journal lifecycle; journal uses the project event schema. |
| `journal.mjs` | `schema.mjs` | validate/canonicalize/checksum/idempotency imports | ✓ WIRED | Append and replay validate project-owned events and checksums. |
| `KernelHost.shutdown` | abort/session.dispose/server.close | `Promise.race` with timeout | ⚠️ PARTIAL | All three calls have timeout races, but `server.close` timeout does not destroy active connections. |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `EventJournal` | `event` / `sequence` | validated input → SQLite append → replay query | Yes | ✓ FLOWING |
| `KernelHost` | readiness/provider count | contained session/resource policy and journal integrity | Yes | ✓ FLOWING |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Full package tests | `npm test --prefix apps/personal_intelligence_kernel` | 29 passed, 0 failed | ✓ PASS |
| Journal tests | `node --test apps/personal_intelligence_kernel/test/event-journal.test.mjs` | 7 passed, 0 failed | ✓ PASS |
| Fixed loopback bind and port conflict | Independent Node check | `127.0.0.1:8790`, `server.listening=true`, conflict `host_bind_failed`, provider calls `0` | ✓ PASS |
| Bounded shutdown with hanging abort/dispose and active socket | Independent Node check | `timed_out=true`, but `connections_after_shutdown=1` | ✗ FAIL |
| Whitespace check | `git diff --check` on 49-01 target paths | Exit 0; Git emitted only LF→CRLF warnings | ✓ PASS |

## Probe Execution

No Phase 49-01-specific `probe-*.sh` was declared or discovered. Node tests and independent Node spot-checks were used.

## Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| KERNEL-01 | 49-01 | Pi 随本地产品服务受控启动和停止，成为唯一主 AI Session 与事件循环 | ? DEFERRED | 49-01 creates an isolated Host but does not alter the production supervisor; context explicitly defers that integration to Phase 52. |
| KERNEL-02 | 49-01 | 请求、Delta、任务和恢复事件统一进入版本化协议并保留绑定 identity | ✓ SATISFIED for 49-01 scope | Exact v1 envelope, deterministic identity, journal idempotency and replay all pass. |

## Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| `apps/personal_intelligence_kernel/src/kernel-host.mjs` | 114–121 | `server.close()` timeout returns without closing remaining connections | 🛑 BLOCKER | A connected socket survived after lifecycle became `disposed`. |

No unreferenced `TBD`, `FIXME`, or `XXX` marker was found in the reviewed 49-01 target implementation.

## Human Verification Required

None for this code-level acceptance. The automated lifecycle spot-check already demonstrates the blocking leak.

## Gaps Summary

The event schema, durable journal, deterministic identity/replay, loopback startup, port-conflict fail-closed behavior, accepted decision/resource gates, and zero Provider calls are verified. The phase cannot pass because `shutdown` reports `disposed` after a bounded timeout while an active TCP connection remains (`connections_after_shutdown=1`). The implementation needs an explicit forced connection cleanup path after `server.close` times out, plus a regression test covering hanging session methods and an open socket.

---

_Verified: 2026-08-04_
_Verifier: the agent (gsd-verifier)_
