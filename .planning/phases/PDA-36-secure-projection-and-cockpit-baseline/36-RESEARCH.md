---
phase: 36
slug: secure-projection-and-cockpit-baseline
date: 2026-07-22
requirements: [CCK-01, CCK-02, CCK-03, CCK-04]
research_mode: implementation
confidence: high
---

# Phase 36 Research: Secure Projection and Cockpit Baseline

## Research Question

How can the existing, currently untracked React Cockpit and Python UI Projection become an auditable, versioned, physically read-only and browser-safe baseline before any Cockpit decision write flow is exposed?

## Scope and Non-goals

Phase 36 establishes the boundary that all later Cockpit pages rely on:

```text
Browser → same-origin REST → versioned read-only Projection → existing authorities
```

It does **not** implement new decision intelligence, a Personal Wiki, Topic Pages, browser persistence, Proactive write routes, external actions, promotion, or any new fact authority. It must not treat the existing untracked Cockpit files as shipped merely because they exist.

## Existing Capability Map

| Concern | Existing implementation | Reusable invariant | Gap Phase 36 must close |
|---|---|---|---|
| Static Cockpit hosting | `api_server.py:_resolve_cockpit_asset` and `/app` handling | `/app` is served by the same loopback REST process; traversal is rejected | Build/track this surface and make error responses safe. |
| Read aggregation | `CockpitProjectionService` in `ui_projection.py` | Uses version `decision_cockpit_projection_v1`; SQLite reads use `mode=ro` and `query_only` | Error/limitation text currently interpolates exceptions. |
| UI transport | `src/api/client.ts:apiGet` and Vite `/app/` base | UI uses relative URLs and Zod before rendering | Production server currently emits wildcard CORS. |
| Guarded writes | `orchestration.ts`, `GuardedOrchestrationInterface` | Existing `prepare → preview → confirm/execute`, checksum, sequence and idempotency flow remains server-authoritative | REST mutation routes have no Origin validation. |
| DTO parsing | `src/api/schemas.ts` and nine captured fixtures | Every `/ui/*` projection has a dedicated Zod schema and fixture test | Common envelope currently accepts arbitrary `schema_version`/`operation`; drift is not fail-closed enough. |
| State presentation | `OverviewPage.tsx`, page routes, React Query hooks | All pages obtain data through relative REST calls | Overview uses stale vocabulary (`confirmed`, `importance.score`) while the Projection emits `accepted` and `importance.final_score`. |
| Contract coverage | `tests/contract/test_ui_projection*.py` and Cockpit Vitest | Projection shapes, partial isolation, SPA asset resolution and UI fixtures are already represented | There is no P0 test that proves cross-origin mutation rejection and zero writes. |

## Standard Stack

Use the repository's existing stack. Phase 36 must not add a framework, an SSR service, a client database, or a new production Node process.

| Layer | Use | Reason |
|---|---|---|
| Cockpit app | React 18 + TypeScript + React Router + Vite | Already present at `apps/personal_decision_cockpit/`; production artifacts are served from REST `/app`. |
| Server projection | `CockpitProjectionService` | Centralizes authority, snapshot, freshness and partial semantics. |
| HTTP boundary | Standard-library `Handler` in `api_server.py` | Existing REST and static hosting owner; security policy belongs here rather than in pages. |
| Read caching | TanStack Query in memory | Gives retry/loading/stale presentation without persisting personal data. |
| DTO validation | Zod + Python contract tests + captured metadata-only fixtures | Lets every change be checked on both sides of the Python/TypeScript boundary. |
| Mutation | Existing `GuardedOrchestrationInterface` only | Keeps HMAC, sequence, confirmation, idempotency and exact replay server-owned. |

## Architecture Patterns

### 1. Versioned server-owned read envelope

All Cockpit reads should continue through a single projection envelope:

```text
decision_cockpit_projection_v1
{ operation, generated_at, snapshot_bindings, freshness,
  authorities, partial, limitations, data }
```

Pages consume a validated, endpoint-specific DTO. They do not join data from SQLite, Chroma, or several authority endpoints in JavaScript and they do not decide current/lifecycle/conflict state.

**Implementation implication:** retain `CockpitProjectionService` as the only `/ui/*` aggregation point. Strengthen the Python envelope and Zod common schema together; use literal schema version and endpoint operation checks, not generic strings.

### 2. Same-origin transport is a server responsibility

The production UI is served at `/app/` by the loopback REST process. UI calls remain relative (`/ui/*`, `/agent/session/*`). CORS and Origin checks must be implemented once in `api_server.py`, before any session operation reaches `orchestration_rest_contract`.

```text
POST /agent/session/*
  → validate browser Origin against production same-origin or explicit dev allowlist
  → reject before parsing/delegating on mismatch
  → guarded orchestration validates preview/confirmation/sequence/idempotency
```

The exact explicit development allowlist and handling of a missing `Origin` header are planner-level choices, but both must be documented and tested for compatibility with existing non-browser local clients. A supplied non-matching Origin must always be rejected with zero delegation and zero writes.

### 3. Safe public errors, detailed local diagnostics

`partial` is part of the public contract, not an excuse to expose `str(exc)`. The public Projection envelope needs stable safe limitation/error codes and user-safe messages. Detailed exception types, paths and diagnostics stay in controlled local logs only.

The same policy applies to static `/app` errors and mutation errors: client-visible responses and browser console output may not contain PII, filesystem paths, raw provider payloads, confirmation tokens or HMAC material.

### 4. Truthful baseline, not premature feature completion

The existing Cockpit app, Projection implementation and tests are WIP candidates. Phase acceptance must first make the file set auditable and demonstrate build plus relevant contracts. Documentation should say `planned` or `in verification` until Phase 36 verification exists; it must not mark Phases 36–40 delivered based on the presence of untracked files.

## Recommended Implementation Order

### Plan A — Establish the HTTP safety boundary

1. Centralize a loopback same-origin / explicit development-origin policy in `api_server.py`.
2. Remove `Access-Control-Allow-Origin: *`; make `OPTIONS` return CORS headers only for permitted development origins.
3. Guard every `/agent/session/*` POST before `orchestration_rest_contract` is called.
4. Return a stable safe rejection contract and prove rejected requests cause no orchestration invocation or database mutation.

This is first because the current UI already contains mutation client code; no Cockpit baseline is safe while arbitrary origins can reach it.

### Plan B — Make Projection v1 safe and exact

1. Introduce a narrow public limitation/error representation owned by `ui_projection.py`.
2. Replace exception interpolation in `_collect`, `_personal_state_detail`, calibration isolation and equivalent paths with safe codes/messages.
3. Keep internal exception details out of the returned envelope while preserving `authorities`, `partial`, snapshot bindings and freshness.
4. Define the one canonical envelope vocabulary, including actual confirmation states and `importance.final_score`.

### Plan C — Close Python ↔ TypeScript contract drift

1. Make TypeScript schemas demand `decision_cockpit_projection_v1` and the expected operation for each endpoint.
2. Keep one controlled metadata-only response fixture per `/ui/*` endpoint; update fixtures only from a reviewed live response or isolated contract fixture.
3. Correct the Overview derivation to use the authority vocabulary (`accepted`, etc.) and `importance.final_score` rather than obsolete fields.
4. Ensure the client remains relative-path only and does not log response payloads.

### Plan D — Record an auditable baseline

1. Add the Cockpit, Projection and their contract tests to the Phase's tracked change set without sweeping unrelated worktree changes into the baseline.
2. Add a concise build/run verification note that distinguishes source code, generated `dist/`, tests and Phase acceptance evidence.
3. Run the focused Python and Vitest/build checks selected by the planner; record exact results in later plan/verification artifacts rather than backdating a completion claim.

## Concrete Code Integration Points

| File / symbol | Phase 36 change boundary |
|---|---|
| `src/personal_knowledge/services/api_server.py:_send` (around line 285) | Replace unconditional wildcard CORS with an allowlisted response policy. Do not add CORS behavior in individual routes. |
| `api_server.py:do_OPTIONS` (around line 313) | Apply the same allowlist policy and safe response contract; do not grant methods/headers to arbitrary origins. |
| `api_server.py:do_POST` (around line 719) | Validate Origin before the `session_write_routes` mapping invokes guarded orchestration; mismatch returns typed safe error and performs no write. |
| `api_server.py:_err` and `/app` handling | Avoid reflecting arbitrary request path or exception text into public Cockpit responses beyond a safe code/message. |
| `src/personal_knowledge/services/ui_projection.py:CockpitProjectionService._error/_collect` (around lines 334/372) | Replace raw detail and exception text with stable public codes. Preserve authoritative partial/degraded semantics. |
| `ui_projection.py:_envelope` (around line 348) | Own the canonical v1 shape and safe limitations metadata; keep physical read-only behavior unchanged. |
| `apps/personal_decision_cockpit/src/api/schemas.ts` | Factor the common envelope so each exported schema pins version and expected operation; retain endpoint-specific data schemas. |
| `apps/personal_decision_cockpit/src/api/client.ts:apiGet` | Keep relative fetch and no-payload logging; map safe server errors into user-safe `ApiError`. |
| `apps/personal_decision_cockpit/src/api/orchestration.ts` | Reuse the current client only after server Origin policy exists; do not reimplement confirmation/HMAC/idempotency in TypeScript. |
| `apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx` | Correct local derived Now Stack against the actual Projection state vocabulary and final score field. This is display-only, not a new ranking authority. |
| `tests/contract/test_ui_projection*.py` | Extend for safe limitations and route policy; retain direct-service/REST parity assertions. |
| `apps/personal_decision_cockpit/src/test/liveContract.test.ts` | Keep all nine `/ui/*` fixtures parseable after schema tightening; add focused regressions for real state vocabulary. |

## Don't Hand-Roll

| Do not build | Why | Reuse instead |
|---|---|---|
| A browser fact store, lifecycle evaluator or local replica | Would form a shadow SSOT and diverge from snapshot/evidence rules | Server-owned `CockpitProjectionService` and existing authorities. |
| A new confirmation token, checksum or replay mechanism in React | Would duplicate the highest-risk part of v1.3 and weaken server authority | `GuardedOrchestrationInterface` plus the existing preview/confirm API. |
| A second mutation API for Cockpit pages | Could bypass low-risk domain/risk budget and append-only audit rules | Existing `/agent/session/*` surface only. |
| LocalStorage, IndexedDB or a Service Worker cache for personal decision payloads | Introduces privacy, stale-data and revocation liabilities | In-memory TanStack Query plus explicit offline/degraded state. |
| A custom global business-rule layer (Redux/store) | Moves authority decisions into the browser | Local component state and validated server DTOs. |
| A new UI framework, SSR server or production Node process | Enlarges the running surface without serving a v1.4 requirement | Vite build served from Python `/app`. |

## Testing Strategy

### Python unit and contract tests

- Assert every public `/ui/*` response retains the required version, operation, snapshot/freshness metadata and safe `partial` semantics.
- Inject failures containing a fake path, secret-looking value and provider-like body; assert public `limitations`/`error` do not return those strings while the affected authority becomes `error` and `partial=true`.
- Use a temporary `ThreadingHTTPServer` and a stubbed `GuardedOrchestrationInterface` to test allowed same-origin, explicit dev origin, non-matching Origin and `OPTIONS` behavior.
- For every rejected cross-origin POST, assert `orchestration_rest_contract` is never called and database/ledger fingerprints remain unchanged.
- Retain SPA asset traversal and missing-build tests; add safe static-error assertions.

### Frontend unit and contract tests

- Verify every endpoint schema rejects the wrong `schema_version` or `operation`, while preserving controlled forward-compatible unknown fields where required.
- Parse all nine metadata-only fixtures through their endpoint schemas.
- Test the Overview with `accepted`/`proposed`/`rejected` confirmation states and `importance.final_score`; prove it does not silently classify every real item as important or pending due to obsolete fields.
- Assert all fetch URLs remain relative and the error path never logs body/payload data.

### Baseline verification (not a substitute for Phase 40 UAT)

Use the existing targeted commands after implementation:

```powershell
Set-Location <repo-root>\apps\personal_decision_cockpit
npm run test
npm run build

Set-Location <repo-root>
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/contract/test_ui_projection.py tests/contract/test_ui_projection_state_external.py tests/contract/test_ui_projection_decision.py tests/contract/test_ui_projection_actions_proactive.py tests/contract/test_orchestration_interfaces.py -q
```

Phase 36 should record only the checks it actually ran. Responsive accessibility and real browser end-to-end acceptance remain Phase 40 responsibilities.

## P0 Risks and Mitigations

| Risk | Evidence in current baseline | Required mitigation | Acceptance evidence |
|---|---|---|---|
| Cross-origin local mutation | `_send` always emits `Access-Control-Allow-Origin: *`; `do_POST` delegates session mutations without Origin validation | Central policy, explicit allowlist, pre-delegation rejection | Non-matching Origin returns safe typed error; invocation/write count remains zero. |
| Sensitive error leakage | `_collect` and several detail helpers include `str(exc)` in limitations | Public safe-code/message mapper; private detailed diagnostics only | Poisoned exception strings never reach JSON, DOM or console. |
| DTO drift disguised as success | Zod common envelope accepts arbitrary version/operation; Overview uses stale fields | Pin envelope/operation and test live fixtures plus real vocabulary | Wrong version/operation fails parsing; fixture and page tests pass with actual fields. |
| WIP mistaken for release | Cockpit, Projection and projection tests are currently untracked; `api_server.py` is modified | Audit only the intended file set and show build/test traceability | Git/change review plus verified focused checks; docs retain planned status until acceptance. |
| Compatibility regression for existing local clients | REST serves MCP/CLI/other local consumers as well as Cockpit | Document origin policy for browser vs non-browser use and test permitted paths | Existing contract callers retain expected behavior; browser cross-origin path is blocked. |

## Prohibited Outcomes

- Do not expose wildcard CORS for Cockpit mutation routes.
- Do not treat UI confirmation, a random browser actor hash or loopback alone as authentication.
- Do not reflect exception strings, filesystem paths, raw authority records, provider bodies, confirmation tokens or HMAC material to browser-visible JSON, DOM or console.
- Do not add client-side writes to Personal, External, Knowledge, Lifecycle, Serving Snapshot, Active Pointer or Calibration authorities.
- Do not add automatic retries with a changed payload, automatic promotion or external actions.
- Do not add a Personal Wiki, Wiki materialization, backlinks, LLM Wiki narrative or Wiki-to-RAG feedback in this phase.
- Do not mark the Cockpit or later phases shipped until tracked code and the appropriate verification evidence exist.

## Planning Recommendation

Plan this phase as four narrow plans in dependency order: (1) shared same-origin/CORS/mutation guard, (2) safe Projection envelope, (3) strict browser DTO and current-vocabulary correction, (4) auditable baseline plus focused verification. Keep Phase 36 limited to the transport/contract boundary; page-level authority, evidence and decision workflow behavior belongs to Phases 37–40.

## Sources

### Primary repository evidence

- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-CONTEXT.md`
- `.planning/REQUIREMENTS.md` — CCK-01 through CCK-04
- `.planning/ROADMAP.md` — Phase 36 success criteria
- `.planning/research/v1.4-decision-cockpit-ui/{SUMMARY,STACK,ARCHITECTURE,PITFALLS}.md`
- `src/personal_knowledge/services/api_server.py`
- `src/personal_knowledge/services/ui_projection.py`
- `apps/personal_decision_cockpit/src/api/{client,schemas,orchestration}.ts`
- `apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx`
- `tests/contract/test_ui_projection*.py`
- `apps/personal_decision_cockpit/src/test/{liveContract,schemas,orchestration,appSmoke}.test.*`

## Confidence

**HIGH.** The Phase boundary, existing service boundaries, current CORS behavior, DTO drift and test locations are directly evidenced in the repository. The precise development-origin configuration and missing-Origin compatibility rule remain an implementation choice that the Phase 36 planner must make explicit and test.

