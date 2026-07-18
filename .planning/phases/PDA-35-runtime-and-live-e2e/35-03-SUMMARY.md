---
phase: 35-runtime-and-live-e2e
plan: 03
subsystem: live-agent-acceptance
tags: [tunnel, mcp, replay, fingerprints, chatgpt]
requirements-partial: [LIVE-02]
completed: 2026-07-19
---

# Phase 35 Plan 03 Summary

**The tunnel reached real readiness while a local HTTP MCP Agent completed read/explain and explicitly confirmed exact replay; tunnel-ingress proof remains open.**

## Results

- Full REST/MCP/tunnel stack reached real readiness; OAuth metadata, health and tunnel UI returned success.
- `analysis.list` and `analysis.explain` returned reviewed compact envelopes.
- A low-risk project session completed prepare, explicit confirm and same-key replay with the same event and `replayed=true`.
- Personal, External, Analysis, Pilot and Calibration SHA-256 fingerprints were unchanged.
- Orchestration delta was exactly +1 session, +1 event, +1 confirmation, +0 provider invocations; external action and promotion counts were zero.
- Fixed two transport integrity defects discovered by live acceptance: privacy-regex corruption of typed digests and Python/JavaScript `1.0`/`1` checksum drift.
- Existing logged-in ChatGPT and the current Plugins settings route were observed; UI DOM automation remained unavailable and is documented as a manual visibility check rather than fabricated evidence.

## Verification

- Production script audit: PASS, 0 findings at all severities.
- Focused Python/security suite: 67 passed.
- ChatGPT MCP Node suite: 23 passed.
- Live MCP: 44 tools and reviewed descriptor hash matched.
