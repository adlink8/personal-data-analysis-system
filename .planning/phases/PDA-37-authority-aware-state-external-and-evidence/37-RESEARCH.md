---
phase: 37
slug: authority-aware-state-external-and-evidence
status: complete
researched: 2026-07-22
research_scope: local-code-and-existing-v1.4-contracts
confidence: high
---

# Phase 37 Research

## Scope and Decision

Phase 37 is a read-side truthfulness phase. It must make the existing Cockpit explain **what is current, historical, partial, stale, conflicted, external, and evidence-backed** before Phase 38 exposes any browser confirmation workflow. It does not add a decision mutation, new authority, Wiki materialization, external-source ingestion, provider call, or client-side lifecycle rule.

The selected implementation is: extend the server-owned `decision_cockpit_projection_v1` with bounded state/external/evidence metadata, render it through shared semantic UI components, and route every evidence drill-down through a read-only Projection operation. The browser renders server conclusions; it never reconstructs authority, lifecycle, freshness, evidence eligibility, or write readiness itself.

## Existing Assets

| Asset | What is already usable | Phase 37 gap |
|---|---|---|
| `CockpitProjectionService` | Versioned envelope, `partial`, `limitations`, snapshot bindings, isolated section failures, read-only SQLite access | It exposes counts and selected metadata, but no unified current-object evidence resolver or server-computed actionability. |
| `personal_state.get` | Eight fixed domains, provenance (`fact`/`observation`/`inference`), lifecycle counts, `current_assertion_id`, `evidence_count`, state key and snapshot | Assertion cards cannot drill down into the existing `state.explain` evidence path. Client freshness is locally inferred rather than described by the authority. |
| `external_delta.get` | Separate External authority, snapshot, source/fact metadata, lifecycle/conflict and bounded Delta lists | Current UI schema expects fields not emitted by `_external_delta_section` (`fact_type`, `observed_at`, `source_id`); `updated` is intentionally always empty because no update-event source exists. |
| `DecisionFeedbackService` / workspace projection | Decision IDs, snapshot IDs, support references, checksums and append-only history are already readable | Phase 37 should make these stable references available to the common evidence drawer; Phase 38 remains responsible for write readiness and confirmation. |
| `IntelligenceService.state.explain` | Existing read-only, snapshot-bound state explanation with lifecycle path, evidence statuses, uncertainty and sealed values | It is not yet exposed as a Cockpit Projection endpoint or UI flow. |
| `DecisionIntelligenceReadService.external.explain` | Existing read-only External fact/source/snapshot detail with explicit "external never becomes personal" limitation | It is currently available only through the generic Agent route, not a Cockpit-owned evidence contract. |
| `EvidencePage` | Reuses Data Browser, Memory Graph and Relation Review widgets | It hard-codes `127.0.0.1:8789`, uses an unrestricted iframe, and explicitly admits that authority wiring is future work; an unavailable widget can appear blank. |

## Standard Stack

No new framework or production dependency is needed.

| Concern | Use | Reason |
|---|---|---|
| Read DTO authority | `src/personal_knowledge/services/ui_projection.py` + `api_server.py` `/ui/*` routes | Keeps field selection, failure isolation and authority semantics server-owned. |
| Client validation/cache | Existing Zod schemas, `apiGet`, TanStack Query | Zod rejects contract drift before rendering; query policy already has bounded retry and refresh. |
| Semantic UI state | Existing `StatePanel`, `SnapshotChip`, `FreshnessBadge`, `AuthorityBadge` plus a small shared claim/lifecycle metadata map | Reuses accessible text+icon semantics; do not duplicate page-specific status logic. |
| Evidence details | Existing `IntelligenceService.state.explain`, `DecisionIntelligenceReadService.external.explain`, `DecisionFeedbackService.recommendations.get` behind one new read-only Cockpit resolver | Preserves stable IDs/checksums and Privacy Guard behavior without a browser-to-database path. |
| Widget embedding | Existing MCP widgets only as labelled diagnostic integrations; React state plus `system.status.get` for bounded recovery | Same-origin API can report MCP availability. An iframe `load` event alone cannot prove cross-origin widget content is usable. |

## Architecture Patterns

### 1. Projection-owned truth flow

```text
Personal / External / Decision read authority
        -> CockpitProjectionService (metadata-only, bounded, query-only)
        -> decision_cockpit_projection_v1 envelope
        -> Zod validation + TanStack Query
        -> shared semantic cards / EvidenceDrawer
```

Every result keeps `schema_version`, `operation`, `snapshot_bindings`, `authorities`, `partial`, `limitations`, `freshness`, stable object identity and evidence availability. A page may arrange cards, but may not infer that two snapshots match, that evidence is eligible, or that a stale item is safe for a later mutation.

### 2. Keep three axes separate

The UI must not collapse these into one colored badge:

| Axis | Examples | Owner |
|---|---|---|
| Claim / object kind | Fact, Observation, Inference, Forecast, Recommendation, Confirmation, External | Producing authority; absent kinds are not fabricated. |
| Lifecycle / record status | current, stale, conflict, resolved, expired, historical | Producing authority. `Historical` is a display grouping, not a replacement lifecycle value. |
| Readability / freshness | complete, partial, unavailable, unknown, stale-at, expired-at | Projection from authority metadata and policy. It is not equivalent to record lifecycle. |

`FreshnessBadge` currently derives `<24h/<7d` from browser time. For action-sensitive presentation, Phase 37 should receive or deterministically project an explicit freshness level/reason from the server. The client may format timestamps, but must not decide that data is current enough for Phase 38.

### 3. One bounded evidence resolver, not direct browser adapters

Add a read-only Projection operation such as `evidence.resolve.get` (the exact route name is planner discretion) that accepts a typed reference:

```json
{
  "subject_type": "personal_state | external_fact | decision",
  "stable_id": "...",
  "snapshot_id": "...",
  "checksum": "...",
  "state_key": { "assertion_kind": "...", "subject": "...", "domain": "...", "scope": "...", "predicate": "..." }
}
```

The server validates the reference against the current object and dispatches only to an allowlisted read service:

```text
personal_state -> IntelligenceService.state.explain
external_fact  -> DecisionIntelligenceReadService.external.explain(resource_type="fact")
decision       -> DecisionFeedbackService.recommendations.get + existing support[]
```

Return metadata, evidence references/statuses, authority/snapshot/checksum, uncertainty, abstention/limitations and safe next steps. Do not return sealed assertion values, raw conversation bodies, arbitrary filesystem paths or an unrestricted “fetch this URL” capability. A reference that no longer matches its snapshot/checksum returns a typed mismatch/expired result, not a best-effort newest record.

### 4. Section-level degraded UX

Use the existing envelope semantics consistently:

| Backend condition | UI behavior |
|---|---|
| Query pending | Skeleton only; do not show a previous response as current. |
| Whole same-origin API unreachable | `error/offline` panel with retry and a statement that no current authority result is available. |
| One authority error | Show the surviving sections, a `partial` strip naming the unavailable authority and its safe limitation. |
| Authority is valid but empty | Empty-state explanation and next safe step; never call it a service error. |
| Object is stale, conflicted, mismatched or lacks eligible evidence | Preserve its metadata, show reason and recovery direction; mark it non-actionable for the future Phase 38 flow. |
| MCP widget unavailable | Keep a non-empty diagnostic/recovery card, state that widget content is unavailable/unverified, offer a new-window diagnostic link; never leave an empty iframe as a success state. |

The external Delta `updated=[]` limitation must remain visible as a data limitation, not be represented as “there were no updates.”

### 5. MCP Widget containment

The current widget port differs from Cockpit origin, so it is cross-origin. Treat it as an optional diagnostic surface, not evidence authority. Use an explicit allowed widget origin, restrictive `iframe` `sandbox` and `referrerPolicy`, and a matching `frame-src` CSP where the REST static host supports it. Start from the least privilege set; do not grant `allow-same-origin`, top navigation, popups, downloads or forms unless a tested widget requirement proves it necessary. A port probe or iframe `load` event is not proof that the widget rendered authoritative data.

## DTO and Data-flow Settlement

Before page work, settle the server/client field names from the actual projection rather than retaining permissive “maybe this field exists” rendering.

| Object | Stable fields the Phase needs | Current mismatch to close |
|---|---|---|
| Personal assertion | state key, `current_assertion_id`, snapshot ID, record status, provenance class, confidence, `evidence_count`, evidence/actionability status | Current page has key and count but no drill-down link or authoritative readiness. |
| External fact | `fact_id`, subject/predicate or a defined display label, region, valid window, source identity, quality/confidence, lifecycle/conflict, snapshot and freshness | Projection emits `subject`/`predicate` and no `observed_at`/`source_id`; page tries to read `fact_type`/`observed_at`/`source_id`. Choose one canonical DTO and update Zod, fixtures and rendering together. |
| Decision support | recommendation ID, personal/external snapshot binding where present, support record IDs/checksums, evidence status, limitations | Existing workspace already has most of it; expose it through the common drawer without inventing a new decision authority. |

Use fixtures captured from the current read-only contract for both complete and partial cases. Do not broaden the client schema solely with `.passthrough()` to conceal a producer/consumer mismatch that affects truth labels or evidence navigation.

## Don't Hand-Roll

- Do not implement a browser SQLite/Chroma reader, lifecycle resolver, snapshot comparer, evidence eligibility rule, or decision permission check.
- Do not build a second graph or topic-Wiki store; Phase 37 only projects existing authorities.
- Do not add an iframe-based “evidence API” or scrape widget DOM across origins.
- Do not treat a count of evidence as proof of eligible evidence; resolve the stable reference server-side.
- Do not use an arbitrary client age threshold as an authorization gate.
- Do not introduce a generic proxy that can fetch arbitrary external URLs or raw evidence bodies.
- Do not use styling color as the only representation of Fact/Inference/Conflict/External/partial state.

## Common Pitfalls

1. **`stale` ambiguity:** record lifecycle and source freshness are different. Always show their labels/reasons separately.
2. **Partial presented as success:** `ok=true` plus `partial=true` is an intentionally degraded success. The UI must surface `limitations` and failed `authorities`, not only use HTTP status.
3. **External/personal contamination:** External fact cards must retain External authority/source/region/validity and the permanent non-promotion statement. Never copy them into Personal State page data.
4. **Evidence race:** a card rendered from snapshot A cannot silently drill into latest snapshot B. Stable reference, snapshot and checksum must be verified together.
5. **False widget confidence:** cross-origin iframe `onLoad` cannot confirm an operational MCP tool; display diagnostic status and recovery before/after timeout.
6. **Privacy leakage through diagnostics:** limitations, error panels, `title`, DOM dataset, console logs and widget URLs must not expose raw evidence, PII, HMAC, filesystem paths, provider responses or secret material.
7. **Silent contract drift:** current External page masks incompatible producer fields as “未提供”. For safety-critical fields, fail the affected section as partial and make the DTO discrepancy testable.
8. **Premature write affordance:** Phase 37 may display blocked/non-actionable state, but it must not expose `prepare`, `confirm`, `execute`, or a “safe to commit” client calculation.

## Code Examples

### Evidence reference rendered by a card

```ts
// Display-only reference. The server, not the browser, validates the binding.
const evidenceRef = {
  subject_type: 'personal_state',
  stable_id: assertion.current_assertion_id,
  snapshot_id: envelope.snapshot_bindings.personal,
  state_key: assertion.key,
};
```

### Required envelope handling

```ts
if (envelope.partial) {
  // render limitations + failed authorities; do not replace valid sections
}
if (object.readiness?.actionable === false) {
  // show reasons and evidence link only; Phase 38 later owns mutation controls
}
```

### External display mapping rule

```text
The producer chooses one DTO: subject + predicate OR display_label/fact_type.
The UI consumes that exact DTO and prints “未提供” only for optional fields.
It never guesses a semantic type from an arbitrary predicate string.
```

## File and Test Strategy

| Area | Primary files | Required verification |
|---|---|---|
| Projection and API | `src/personal_knowledge/services/ui_projection.py`, `src/personal_knowledge/services/api_server.py`, `tests/contract/test_ui_projection_state_external.py` | Resolver success/mismatch/authority error, metadata-only output, exact snapshot/checksum binding, external DTO parity, partial isolation and no mutation. |
| Client contract | `apps/personal_decision_cockpit/src/api/schemas.ts`, `api/hooks.ts`, fixtures, schema tests | Canonical External fields, evidence resolver envelope, explicit freshness/readiness discriminants, malformed/safe-error rejection. |
| State/overview UI | `pages/overview/OverviewPage.tsx`, `pages/state/PersonalStatePage.tsx`, shared authority/feedback components and tests | Eight domains; all applicable kind/lifecycle labels; conflict/historical/partial/empty/offline; evidence drawer launch carries stable reference only. |
| External UI | `pages/external/ExternalContextPage.tsx` and tests | Source/region/validity/lifecycle/conflict/freshness; permanent External separation; `updated` limitation; filters remain local read-only. |
| Evidence UI/widgets | `pages/evidence/EvidencePage.tsx` plus new drawer/widget status component and tests | Personal/External/Decision drill-down, mismatch/abstain recovery, Memory Graph diagnostic label, unavailable MCP non-empty fallback, restrictive iframe attributes. |

Minimum tests must include: current Personal evidence resolution, External fact resolution, Decision support drill-down; snapshot/checksum mismatch; no evidence/abstained; individual state/change/external authority failure; empty versus partial; stale lifecycle versus stale freshness; schema producer/client parity; widget unavailable fallback; and proof that all Phase 37 browser requests are GET/read-only.

## Risks and Prohibitions for the Planner

- Phase 36 is a prerequisite: keep its same-origin/CORS/safe-error contract intact; do not re-open generic CORS or add cross-origin mutation convenience paths.
- Phase 37 must not create a Personal Wiki page, topic cache, back-link index or LLM narrative. Those are v1.5 work.
- Do not solve missing External update events by inferring changes in the client; retain the explicit limitation until the authority exposes a versioned update record.
- Do not claim that the existing 78 component tests or a successful iframe render proves authoritative evidence E2E. Add targeted contract/UI evidence tests now; browser UAT remains Phase 40.

## Planning Recommendation

Plan this phase as three dependency-ordered slices:

1. **Settle read DTOs and resolver contract:** server projection, API route, Zod schemas, captured fixtures and Python contract tests.
2. **Render authority-aware State and External:** shared semantic labels/freshness/readiness, page integration and deterministic partial/empty/conflict behavior.
3. **Close the evidence surface:** common drawer plus contained diagnostic widgets, mismatch/abstain recovery, focused UI tests.

This order prevents the UI from cementing the current External field drift or treating Widget embeds as a substitute for snapshot-bound evidence.

