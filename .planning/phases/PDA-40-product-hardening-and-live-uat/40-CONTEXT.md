# Phase 40: Product Hardening and Live UAT - Context

**Gathered:** 2026-07-22  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 40 proves the complete Cockpit in a real browser and records release/recovery evidence. It verifies responsive behavior, accessibility, privacy, truthful service degradation and the existing low-risk exact replay flow. It does not expand feature scope or treat a green component suite as sufficient product evidence.
</domain>

<decisions>
## Implementation Decisions

### Acceptance scope
- **D-40-01:** Browser UAT covers 320/768/1024/1440 widths, keyboard navigation, visible focus, Esc drawer closing, reduced motion, 200% zoom, long Chinese text and long identifiers.
- **D-40-02:** Charts require an equivalent text/table reading path; color never is the sole carrier of Fact/External/Candidate/Risk/Partial meaning.

### Fault and privacy evidence
- **D-40-03:** UAT separately proves REST offline, MCP Widget unavailable, Chroma unavailable and individual authority partial states. Each must show accurate empty/partial/stale/offline/recovery UI rather than blank or stale success.
- **D-40-04:** The browser must not retain raw messages, provider bodies, PII, credentials, HMAC or confirmation material in localStorage, default DOM, console, snapshots or user-visible errors.

### Verification and recovery
- **D-40-05:** Required evidence includes `npm run build`, front-end tests, UI Projection contracts, guarded orchestration/replay/privacy tests and at least one real same-origin prepare/confirm/exact-replay UAT.
- **D-40-06:** A failed release/UAT leaves authority data untouched. Recovery is a front-end artifact/config rollback or typed service recovery; no database reset, lifecycle rewrite or silent cache fallback is allowed.
- **D-40-07:** Any new browser E2E dependency/tool requires its own dependency review; it cannot be smuggled in as a prerequisite for claiming acceptance.

### the agent's Discretion

The planner may choose the exact browser automation/manual evidence approach and UAT report template, provided D-40-01..07 and UX-01..02/QA-01..02 are verifiable before marking the phase complete.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — UX-01..02, QA-01..02.
- `.planning/ROADMAP.md` — Phase 40 goal and criteria.
- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-CONTEXT.md` — transport/privacy baseline.
- `.planning/phases/PDA-38-guarded-decision-workspace/38-CONTEXT.md` — exact confirm/replay acceptance.
- `.planning/research/v1.4-decision-cockpit-ui/PITFALLS.md` — browser, degraded and privacy failure modes.
</canonical_refs>

<code_context>
## Existing Code Insights

- Cockpit package currently has Vitest/Testing Library and build scripts but no established Cockpit-specific browser E2E suite.
- Existing UI query hooks use bounded in-memory query caching; it is not an offline persistence guarantee.
- REST `/app`, MCP widget embedding, runtime state and Projection partial data are existing integration boundaries requiring real-browser validation.
</code_context>

<deferred>
## Deferred Ideas

- Persistent/offline personal-data caching.
- Mobile native app, public deployment, multi-user login or SSR.
- New business capabilities or Wiki features.
</deferred>

---
*Phase: 40-product-hardening-and-live-uat*  
*Context gathered: 2026-07-22*
