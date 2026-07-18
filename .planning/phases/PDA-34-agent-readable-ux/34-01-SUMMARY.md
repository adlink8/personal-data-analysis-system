---
phase: 34-agent-readable-ux
plan: 01
subsystem: agent-contract
tags: [compact, evidence, errors, recovery, privacy]
provides:
  - Shared 16 KiB Agent envelope
  - Stable evidence links and next actions
  - Central typed error/recovery catalog
requirements-completed: [UX-01, UX-02]
completed: 2026-07-19
---

# Phase 34 Plan 01 Summary

**REST and stdio Agent adapters now return one compact, budgeted success/error contract with stable evidence drill-down and safe recovery actions.**

## Accomplishments

- Added `agent_compact_envelope_v1` with a hard 16 KiB default budget.
- Added stable ID/checksum evidence links and allowlisted next actions.
- Added nine error categories including non-retryable unknown provider outcome.
- Omitted provider bodies, confirmation capabilities and private rich content before projection.
- Preserved underlying service contracts and existing tool names.

## Commits

- `8279e49` — compact Agent contract and transport integration
- `81611ab` — budget, privacy, evidence and error taxonomy tests

## Verification

19 compact/transport/adjacent contract tests passed.
