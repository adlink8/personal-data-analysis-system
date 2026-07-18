---
phase: 34-agent-readable-ux
plan: 02
subsystem: chatgpt-agent-ux
tags: [chatgpt, compact, eval, recovery]
requirements-completed: [UX-01, UX-02]
completed: 2026-07-19
---

# Phase 34 Plan 02 Summary

**ChatGPT tools now preserve the shared compact contract and fixed evals prove safe tool selection and recovery behavior.**

## Accomplishments

- Node REST handling recognizes compact envelopes without unwrapping away summary/navigation fields.
- Typed errors retain category, retryability and allowlisted recovery actions.
- Read and orchestration tools share one passthrough path while legacy response compatibility remains.
- Twelve fixed Agent scenarios reach the expected action with no bypass, provider retry or auto-promotion hint.

## Commits

- `1352558` — ChatGPT compact passthrough and Agent UX evals
- `0ea5f8a` — runtime taxonomy and live transport regression correction

## Verification

- Python Phase 34/adjacent suite: 53 passed.
- Node ChatGPT compact/legacy suite: 16 passed.
