---
phase: 35-runtime-and-live-e2e
plan: 02
subsystem: descriptor-contract
tags: [mcp, snapshot, protocol, live-smoke]
requirements-completed: [LIVE-03]
completed: 2026-07-19
---

# Phase 35 Plan 02 Summary

**The 44-tool ChatGPT MCP surface is now pinned by a reviewed canonical snapshot and matches a real localhost `/mcp` server.**

## Results

- Snapshot covers full input/output schemas, annotations and security schemes.
- Canonical descriptor SHA-256: `42920a097e3073791634cf8af006e9eb35b07bbcdba53541c21b04c553b42706`.
- Check/update CLI fails closed on drift.
- Live MCP initialize negotiated protocol `2025-06-18`; 44 tools and hash matched exactly.
- Live `decision_analysis_list` and `decision_analysis_explain` returned compact envelopes of 2010 and 3562 bytes.
- Runtime gained safe owned Stop/Status lifecycle and retained production audit PASS.

## Commits

- `b590636` — owned stop/status lifecycle
- `b904172` — descriptor CLI, test and live smoke probe
- `5479470` — reviewed descriptor snapshot
