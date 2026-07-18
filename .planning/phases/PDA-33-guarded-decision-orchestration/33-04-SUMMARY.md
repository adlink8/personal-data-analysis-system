---
phase: 33-guarded-decision-orchestration
plan: 04
subsystem: orchestration-transports
tags: [service, rest, mcp, chatgpt, acceptance]
requires:
  - phase: 33-03
    provides: guarded authority bridges
provides:
  - Shared schema-versioned orchestration interface
  - Additive REST, stdio MCP and ChatGPT MCP session tools
  - Server-side confirmation capability handling
  - Cross-surface positive, replay and rejection acceptance
affects: [34-operator-ux, 35-live-acceptance]
tech-stack:
  added: []
  patterns: [thin-transport-adapter, server-side-capability, strict-tool-schema]
key-files:
  created:
    - src/personal_knowledge/services/orchestration_service.py
    - tests/contract/test_orchestration_interfaces.py
    - tests/e2e/test_orchestration_acceptance.py
    - apps/personal_data_chatgpt/test/orchestration-tools.test.mjs
  modified:
    - src/personal_knowledge/services/api_server.py
    - src/personal_knowledge/services/mcp_server.py
    - apps/personal_data_chatgpt/server.mjs
key-decisions:
  - "Public tools accept explicit confirmed=true while the service mints and consumes the bound HMAC capability internally."
  - "Mutation tools are non-destructive, idempotent and closed-world, but correctly not marked read-only."
requirements-completed: [ORCH-01, ORCH-02, ORCH-03, ORCH-04]
duration: 35min
completed: 2026-07-19
---

# Phase 33 Plan 04: Agent Transport and Acceptance Summary

**Real Agent transports can now prepare, explicitly confirm, execute, resume and explain guarded sessions without exposing confirmation capabilities or duplicating provider effects.**

## Accomplishments

- Added one shared interface used by REST and stdio MCP.
- Added 13 focused ChatGPT HTTP MCP tools with strict schemas and truthful annotations.
- Kept HMAC capabilities server-side while preserving explicit per-write confirmation.
- Added all-surface generation/replay acceptance with provider call counting and authority fingerprints.
- Redacted legacy confirmation-token arguments from stdio diagnostic logs.

## Task Commits

1. **Shared REST and stdio contracts** — `3ae12dd`
2. **ChatGPT session tools** — `ae736e8`
3. **All-surface acceptance tests** — `0d0c145`
4. **Server-side capability security fix** — `680b2fb`

## Deviations from Plan

The public contract uses `confirmed=true` and mints the short-lived capability inside the service. Returning a bearer token through ChatGPT would be correctly sealed by the existing privacy guard and would make the next step unusable.

## Issues Encountered

Security review caught the unusable exposed-token design and sensitive stdio argument logging before phase closure; both are fixed and covered by regression tests.

## Self-Check: PASSED

- Python orchestration and adjacent contract suites: 27 passed.
- ChatGPT MCP and legacy contract suites: 13 passed.
- Exact generation replay retains `provider_calls=1`; rejection fingerprints remain unchanged.

---
*Phase: 33-guarded-decision-orchestration*
*Completed: 2026-07-19*
