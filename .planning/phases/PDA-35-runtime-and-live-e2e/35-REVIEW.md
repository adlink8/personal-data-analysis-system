---
phase: 35
status: passed
reviewed: 2026-07-19
findings_open: 0
---

# Phase 35 Code Review

## Resolved findings

| Priority | Finding | Resolution |
|---|---|---|
| P1 | First-readiness timeout could leave the just-started tunnel outside the cleanup list. | Register ownership before start; regression test enforces ordering. |
| P1 | Redirected child stdout/stderr were not drained and could deadlock a verbose tunnel process. | Children inherit the supervisor's controlled output handles. |
| P1 | Privacy PII regexes could mutate typed hashes/IDs and invalidate signed previews. | Typed integrity keys bypass free-text scanning in Python and Node; normal text remains protected. |
| P1 | JavaScript JSON serialized Python `1.0` as `1`, invalidating preview checksums. | Preview payload and session identity use transport-stable numeric normalization. |

## Result

No open correctness, safety or compatibility findings. The runtime audit and live replay both pass.

