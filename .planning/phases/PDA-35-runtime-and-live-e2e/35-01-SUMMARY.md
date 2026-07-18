---
phase: 35-runtime-and-live-e2e
plan: 01
subsystem: runtime-supervisor
tags: [powershell, watchdog, safety, tunnel, health]
requirements-completed: [LIVE-01]
completed: 2026-07-19
---

# Phase 35 Plan 01 Summary

**The Agent stack now has a production-audited foreground supervisor that starts dependencies in order, owns only its child PIDs and fails diagnostically.**

## Results

- Canonical implementation moved to `ops/runtime`; legacy launcher is a thin PowerShell 7 wrapper.
- Check/DryRun are zero-write; Run provisions only the additive orchestration schema.
- Healthy external instances are reused; unhealthy port conflicts fail without terminating the owner.
- Secrets stay in environment/process memory; configuration logs only set/missing status.
- Tunnel profile is verified through the real CLI and full doctor runs after MCP readiness.
- Four failure/safety scenarios and a real REST+MCP launch/cleanup passed.
- Bundled production audit improved from PARTIAL (5 High plus one manual Critical) to PASS (0 Critical/High/Medium/Low).

## Commit

`6cef5be` — hardened supervisor, wrapper, tests and PASS audit.
