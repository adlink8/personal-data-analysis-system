# Phase 36: Secure Projection and Cockpit Baseline - Context

**Gathered:** 2026-07-22  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 36 turns the existing untracked Cockpit work into an auditable, versioned and secure baseline. It fixes the transport and contract boundary before any user-facing decision write path is exposed: Projection is read-only, production Cockpit/API are same-origin, mutation rejects cross-origin requests, DTO semantics are stable, and errors remain safe.

It does not build new decision intelligence, add Wiki pages, add offline personal-data storage, expose new Proactive write routes, or execute a user decision.
</domain>

<decisions>
## Implementation Decisions

### Authority and client boundary
- **D-36-01:** The browser consumes only versioned server-owned `decision_cockpit_projection_v1` envelopes and existing guarded session APIs; it never connects to SQLite/Chroma, calculates lifecycle/current state, or writes a fact authority.
- **D-36-02:** Projection operations remain physically read-only (`mode=ro`, `query_only`) and may not call a Provider, promotion, lifecycle mutation or external action.

### Transport and mutation safety
- **D-36-03:** Production Cockpit is served from REST `/app` and calls relative same-origin routes. Wildcard CORS is removed; development origins are explicit and mutation routes reject a non-matching Origin before any confirm/session write.
- **D-36-04:** UI confirmation is not authentication. The existing server-owned preview checksum, confirmation, sequence and idempotency contract remains authoritative.

### Projection DTO and safe errors
- **D-36-05:** Projection DTO fields are defined once, validated by Zod and Python contract tests, and are backed by controlled real-response fixtures. `confirmation_state` and proactive `importance.final_score` use the authority's actual vocabulary.
- **D-36-06:** API/UI limitations expose stable safe codes and user-safe messages; they must not serialize `str(exc)`, paths, PII, secrets, provider bodies, confirmation tokens or HMAC material.

### Baseline truthfulness
- **D-36-07:** Existing Cockpit/UI Projection files are implementation candidates, not completed features, until tracked, built and verified. Documentation must not call Phase 36–40 shipped before their phase acceptance.

### the agent's Discretion

The planner may choose the exact CORS allowlist/configuration, error-code helper location and DTO fixture layout, provided D-36-01..07 and CCK-01..04 remain satisfied without widening network or write permissions.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — CCK-01..04.
- `.planning/ROADMAP.md` — Phase 36 goal and success criteria.
- `.planning/research/v1.4-decision-cockpit-ui/{SUMMARY,STACK,ARCHITECTURE,PITFALLS}.md` — milestone research.
- `.planning/PERSONAL-DECISION-COCKPIT-UI-SPEC-2026-07-19.md` — candidate product/UI contract.
- `.planning/phases/PDA-33-guarded-decision-orchestration/33-CONTEXT.md` — existing guarded mutation contract.
- `.planning/phases/PDA-35-runtime-and-live-e2e/35-VERIFICATION.md` — v1.3 runtime and live-boundary evidence.
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/personal_knowledge/services/ui_projection.py` already exposes a versioned, read-only Cockpit Projection and partial/limitations metadata.
- `src/personal_knowledge/services/api_server.py` already maps `/ui/*`, serves `/app`, applies privacy filtering and hosts guarded session routes.
- `apps/personal_decision_cockpit/src/api/` already has relative URL client, Zod schemas and orchestration helpers.
- `tests/contract/test_ui_projection*.py` and `apps/personal_decision_cockpit/src/**/*.test.*` are the baseline test suite.

### Known Gaps to Close
- `api_server.py` currently permits wildcard CORS, which cannot coexist with browser mutation exposure.
- External DTO/page fields and Overview state/priority field usage have known drift.
- Existing `ui_projection` limitations can surface exception text and need a safe public envelope.
- Cockpit/Projection/test files are not yet a verified tracked milestone baseline.
</code_context>

<deferred>
## Deferred Ideas

- Personal Wiki/Topic Pages/backlinks/LLM Wiki narrative (v1.5 only).
- New authority, external action, high-risk-domain mutation or Proactive control write route.
- Service worker/localStorage persistence of personal decision data.
</deferred>

---
*Phase: 36-secure-projection-and-cockpit-baseline*  
*Context gathered: 2026-07-22*
