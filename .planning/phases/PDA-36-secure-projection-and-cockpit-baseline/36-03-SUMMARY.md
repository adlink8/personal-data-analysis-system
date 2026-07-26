---
phase: 36-secure-projection-and-cockpit-baseline
plan: 03
subsystem: ui
tags: [cockpit, zod, react, contract-testing, dto-drift, projection-v1]

# Dependency graph
requires:
  - phase: 36-secure-projection-and-cockpit-baseline
    provides: "36-01's centralized Origin/CORS policy and 36-02's `_SAFE_FAILURE_CODES`/`_KNOWN_CONFIRMATION_STATES`-locked `decision_cockpit_projection_v1` server envelope — this plan makes the React client consume exactly that contract"
provides:
  - Endpoint-bound Projection v1 Zod schemas — every exported `/ui/*` envelope schema now fixes `schema_version` to the literal `decision_cockpit_projection_v1` and `operation` to that endpoint's exact literal (e.g. `overview.get`), via a re-typed `envelope(operation, dataSchema)` factory
  - Regression proof that all nine real captured fixtures parse, that tampering `schema_version`/`operation` on any of the nine fails, and that three representative cross-endpoint payload swaps are rejected
  - Confirmed (via new tests, no code change needed) that `client.ts:apiGet` already satisfies D-36-06: relative-path-only fetch, four failure paths normalized to typed `ApiError{code,message}`, zero `console.*` calls carrying response body/poisoned content on any path
  - Fixed `OverviewPage.tsx` Now Stack derivation to use the real authority vocabulary (`proposed/accepted/rejected/deferred/revoked` confirmation states, `importance.final_score`) instead of two fields (`confirmed`, `importance.score`) that never occur in real server responses
affects: [37-authority-aware-state-and-evidence, 38-guarded-project-decision-workspace, 39-truthful-feedback-and-runtime, 40-browser-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Zod envelope factory takes the endpoint operation as a required generic parameter (`envelope('overview.get', DataSchema)`) and uses `z.literal(...)` for both `schema_version` and `operation` — any future new `/ui/*` endpoint schema must supply its own literal, structurally preventing a copy-pasted schema from silently accepting another endpoint's payload"
    - "Contract tests assert both directions: fixture parses (positive) and tampered/foreign-endpoint payload is rejected (negative) — applied uniformly across all nine live fixtures in liveContract.test.ts"
    - "Client-side display-only vocabulary must mirror the exact literal set the server treats as authoritative (`_KNOWN_CONFIRMATION_STATES`/`_classify_stage`'s closed-state set, `importance.final_score` + the same ranking threshold used server-side) rather than re-deriving new heuristics"

key-files:
  created: []
  modified:
    - apps/personal_decision_cockpit/src/api/schemas.ts
    - apps/personal_decision_cockpit/src/test/schemas.test.ts
    - apps/personal_decision_cockpit/src/test/liveContract.test.ts
    - apps/personal_decision_cockpit/src/test/appSmoke.test.tsx
    - apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx

key-decisions:
  - "client.ts required zero functional changes for Task 2 — a fresh read confirmed it already used relative-only fetch paths and a small allowlisted ApiError code set (network_error/http_<status>/invalid_json/schema_mismatch) with safely templated messages and no console logging anywhere on the failure paths. Effort was redirected to adding the regression tests the plan's acceptance criteria actually require (schemas.test.ts apiGet suite + appSmoke.test.tsx schema_mismatch display case), so the guarantee is now evidenced, not just believed."
  - "OverviewPage Now Stack keeps `accepted` decision items visible (not just `proposed`) — only `rejected/deferred/revoked` (the server's own closed-state set from `_classify_stage` rule 1) are excluded. Excluding `accepted` would have been wrong: it is a currently-valid, non-closed state, not a resolved one."
  - "The proactive `isHighImportance` threshold (0.55) is set to match the server's own `DEFAULT_RANKING_POLICY.threshold` used by `proactive_summary.get`'s now/deferrable split, rather than inventing an independent client-side value (previous buggy code used a made-up 0.7 against the wrong field). This keeps the two independent 'is this important' judgments (Overview's ad hoc Top-3 slice vs. Proactive Summary's authoritative grouping) numerically consistent without the client calling into or duplicating the ranking authority itself — display-only, no write, no new authority."
  - "Missing/non-numeric `importance.final_score` is conservatively treated as NOT high-importance for Now Stack purposes, mirroring the server's own 'unscored → deferrable' default in `_proactive_inbox_section`, rather than defaulting to inclusion."

patterns-established:
  - "Any new `/ui/*` Zod envelope schema added in Phase 37+ must be built via `envelope('<operation.literal>', DataSchema)` — omitting the operation argument is a compile error, so DTO drift toward an over-permissive `z.string()` operation field can't silently reappear."

requirements-completed: [CCK-01, CCK-03]

# Metrics
duration: ~35min
completed: 2026-07-26
---

# Phase 36 Plan 03: Secure Projection and Cockpit Baseline — Cockpit DTO/Vocabulary Hardening Summary

**Tightened all nine `/ui/*` Zod envelope schemas to reject any response whose `schema_version`/`operation` doesn't exactly match that endpoint, proved `client.ts`'s existing relative-path/safe-error behavior with new regression tests, and fixed `OverviewPage.tsx`'s Now Stack to use the real `accepted/rejected/deferred/revoked` confirmation vocabulary and `importance.final_score` field instead of two fields that never occur in real backend responses.**

## Performance

- **Duration:** ~35 min
- **Started:** 2026-07-26T20:00:00+08:00 (approx.)
- **Completed:** 2026-07-26T20:36:00+08:00
- **Tasks:** 3
- **Files modified:** 5 (1 source schema file, 1 source page file, 3 test files)

## Accomplishments

- `schemas.ts`'s shared `envelope()` factory now requires each of the nine exported endpoint schemas (`overview.get`, `system.status.get`, `personal_state.get`, `external_delta.get`, `decision_queue.get`, `decision_workspace.get`, `actions_recent.get`, `proactive_summary.get`, `calibration_overview.get`) to pass its own operation literal; `schema_version` and `operation` are both `z.literal(...)`, closing T-36-07 (a response with the wrong version or the wrong/foreign operation can no longer be parsed as valid Cockpit data).
- `liveContract.test.ts` gained full coverage across the nine real captured fixtures: each one still parses (30→32 existing assertions preserved), each one fails to parse after `schema_version` or `operation` is tampered (18 new tests), and three representative cross-endpoint swaps (decision-queue vs. personal_state, proactive-summary vs. actions_recent, overview vs. system.status) are proven rejected.
- `schemas.test.ts` gained matching negative tests for the four endpoints it directly constructs fixtures for (overview/system-status/personal-state/external-delta): wrong version, wrong operation, and foreign-endpoint-payload rejection, plus a new `apiGet` test suite (6 tests) that mocks `fetch` and proves: requests stay relative-path-only, all four failure paths (network/http-non-2xx/invalid-json/schema-mismatch) normalize to typed `ApiError`, injected poisoned fragments (fake filesystem path, `confirmation_token=`, `HMAC-SHA256=`, a `sk-test-...`-shaped secret) never appear in `ApiError.message`, and `console.log/error/warn` are never called on any failure path.
- `appSmoke.test.tsx` gained a `schema_mismatch` display regression (DOM shows only the safe message, console untouched) plus three focused `OverviewPage` Now Stack tests scoped with `within()` to the "现在最重要" card (to avoid false negatives from the same data also legitimately appearing in `ProactiveCard`/`DecisionQueueCard`): `proposed`/`accepted` items show with correct real-vocabulary detail text and `rejected` is excluded; `deferred`/`revoked`-only decision sets correctly fall through to the empty state; and `importance.final_score` threshold gating correctly ignores a high legacy `score` field with no `final_score`.
- `OverviewPage.tsx`'s Now Stack derivation was fixed: `CLOSED_CONFIRMATION_STATES = {rejected, deferred, revoked}` replaces the old `=== 'confirmed'` check (a value that never appears in real `confirmation_state` data, so the previous filter was a no-op), and `isHighImportance` now reads only `importance.final_score` against a 0.55 threshold matching the server's own `DEFAULT_RANKING_POLICY.threshold`, instead of the old `importance.score`/`importance.level` fields that don't exist in real Projection responses.

## Task Commits

Each task was committed atomically:

1. **Task 1: 把每个 Projection schema 绑定到 v1 和预期 operation** - `e33eb43` (feat)
2. **Task 2: 保持相对同源客户端与安全错误映射的回归覆盖** - `95c9470` (feat)
3. **Task 3: 修正 Overview 的 confirmation 与 proactive score 展示** - `e22c911` (fix)

**Plan metadata:** this SUMMARY commit (docs); STATE.md/ROADMAP.md progress tracking deferred (see below).

## Files Created/Modified

- `apps/personal_decision_cockpit/src/api/schemas.ts` — `envelope()` factory now takes an `operation` literal; all nine exported envelope schemas updated to pass their endpoint's exact operation string
- `apps/personal_decision_cockpit/src/api/client.ts` — reviewed, unmodified (already compliant with D-36-06; see Decisions Made)
- `apps/personal_decision_cockpit/src/test/schemas.test.ts` — version/operation tamper + cross-endpoint-rejection tests for four schemas; new `apiGet` behavior test suite (relative URL, four typed-error paths, poisoned-content non-leak, console silence, success path)
- `apps/personal_decision_cockpit/src/test/liveContract.test.ts` — tamper regression across all nine live fixtures; three cross-endpoint payload-rejection tests; two D-36-05 contract-level assertions that the real `overview.json` fixture actually carries the vocabulary `OverviewPage.tsx` now depends on
- `apps/personal_decision_cockpit/src/test/appSmoke.test.tsx` — `schema_mismatch` safe-display regression; three `OverviewPage` Now Stack vocabulary regressions scoped via `within()`
- `apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx` — `CLOSED_CONFIRMATION_STATES` set + `isHighImportance` rewritten to use `importance.final_score`

## Decisions Made

See `key-decisions` in frontmatter. Summarized: `client.ts` needed no code change (already safe; only test coverage was added); Overview's Now Stack keeps `accepted` visible and only excludes the server's own closed-state set; the client-local importance threshold (0.55) intentionally mirrors the server's `DEFAULT_RANKING_POLICY.threshold` rather than inventing a new number; missing/non-numeric `final_score` defaults to "not important" to match the server's own conservative default.

## Deviations from Plan

**1. [Scope-appropriate interpretation] Task 2's `<files>` list included `client.ts` but it required zero functional changes**

- **Found during:** Task 2, after re-reading `client.ts` against the plan's acceptance criteria
- **Issue:** The plan's Task 2 action describes hardening `apiGet`'s error mapping and removing any body/console-leak paths. A fresh read of the current `client.ts` (last touched before this plan) showed it already: (a) uses only relative fetch paths, (b) maps all four failure modes to a small allowlisted `ApiError{code,message}` shape with safely templated messages, and (c) contains zero `console.*` calls anywhere. There was nothing unsafe to fix.
- **Fix:** No source change to `client.ts`. Effort was redirected to writing the regression tests the plan's acceptance criteria actually demand (which did not previously exist): a 6-test `apiGet` suite in `schemas.test.ts` using poisoned-fragment injection to prove the safety property, plus an `appSmoke.test.tsx` DOM/console regression for the `schema_mismatch` display path.
- **Files modified:** `apps/personal_decision_cockpit/src/test/schemas.test.ts`, `apps/personal_decision_cockpit/src/test/appSmoke.test.tsx` (no change to `client.ts` itself).
- **Verification:** New tests pass (`schemas.test.ts` 27/27, `appSmoke.test.tsx` 16/16); full frontend suite 121/121; `npm run build` succeeds.
- **Committed in:** `95c9470` (Task 2 commit)

**2. [Necessary test-scoping fix during implementation] `within()` scoping required in appSmoke Now Stack tests**

- **Found during:** Task 3, first run of the new `OverviewPage` Now Stack tests
- **Issue:** A naive `screen.getByText(...)`/`screen.queryByText(...)` against the whole rendered Overview page failed with "multiple elements found" because the same decision/proactive item legitimately also renders inside `DecisionQueueCard`/`ProactiveCard` further down the same page — those sections intentionally re-display the same data for a different purpose (full queue vs. curated "now" slice) and are unrelated to this plan's scope.
- **Fix:** Scoped all three new assertions to the "现在最重要" `<section>` via `within(nowStackSection())`, where `nowStackSection()` locates the section by its `<h2>` heading.
- **Files modified:** `apps/personal_decision_cockpit/src/test/appSmoke.test.tsx`
- **Verification:** All three Now Stack tests pass deterministically; re-ran full suite (121/121) to confirm no interaction with other appSmoke route tests.
- **Committed in:** `e22c911` (Task 3 commit)

---

**Total deviations:** 2 (1 scope-appropriate no-op on an already-compliant file, 1 test-mechanics fix discovered while writing the plan's own acceptance-criteria tests). Neither touched any file outside this plan's `files_modified` list; no scope creep into unrelated subsystems.

## Issues Encountered

- **Shared working tree confirmed genuinely active during execution:** a `git status --short` taken after all three task commits showed `src/personal_knowledge/services/api_server.py` as freshly modified (22 lines added) plus two new untracked files (`assets/evals/knowledge_units/eval_policy_v3-draft.yaml`, `src/personal_knowledge/services/eval_review.py`) that were **not** present in the initial pre-task `git status` snapshot handed to this executor. This confirms another session was actively committing/working in this shared tree concurrently. None of these files were touched, read, staged, or referenced by this plan's work; every `git add`/`git commit` in this plan used explicit file paths (never `git add -A`/`git add .`), and a `git status --short` was checked before each of the three commits to confirm only the intended files were staged.
- No other issues — all three tasks' `<verify>` commands and the plan-level `<verification>` command passed on first or second attempt (one test-scoping fix, documented above as a deviation).

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The Cockpit's TypeScript DTO layer now structurally rejects wrong-version/wrong-operation responses and is regression-proven against all nine real endpoint fixtures — Phase 37+ pages building new endpoint consumers should extend `envelope()` the same way (pass the operation literal) rather than reintroducing a permissive `z.string()`.
- `OverviewPage.tsx` is the first page in this Cockpit to correctly consume the real `confirmation_state`/`importance.final_score` vocabulary end-to-end; Phase 37's `PersonalStatePage`/`ExternalContextPage` work and Phase 38's `DecisionCenterPage`/`DecisionWorkspacePage` work (already largely built per the existing untracked WIP) should be checked against this plan's `liveContract.test.ts` D-36-05 pattern (asserting the real fixture actually carries the fields a page depends on) rather than assumed correct.
- `client.ts` and `orchestration.ts` remain the sole HTTP boundary; no new persistence, no new mutation surface, no new browser-side authority was added by this plan.
- **STATE.md/ROADMAP.md progress commit deferred:** per the shared-tree discipline instructions for this run, `.planning/ROADMAP.md`'s Phase 36 "Plans: 2/4 plans executed" line was edited to "Plans: 3/4 plans executed" and `.planning/STATE.md`'s "Current Position" block was edited to "Plan: 4 of 4 / Status: 36-01/36-02/36-03 complete; 36-04 next" — both **in the working tree only**, not committed, because both files already carry a large set of unrelated uncommitted changes from another session's `.planning` reorganization (moving root spec docs into `.planning/audits/`/`research/`, rewriting the progress frontmatter to whole-project scale). The orchestrator should fold these two targeted line-edits into whatever tracking commit closes out Phase 36's plan sequence, or reapply them if that other session's changes are committed/reset first.
- Plan 36-04 (per `36-CONTEXT.md`'s Plan D: "auditable baseline plus focused verification") is next; this plan's frontend contract-hardening work and 36-01/36-02's server-side hardening are both ready inputs for that baseline documentation pass.

---
*Phase: 36-secure-projection-and-cockpit-baseline*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `apps/personal_decision_cockpit/src/api/schemas.ts` contains `z.literal(operation)` inside `envelope()` and all nine call sites pass an operation string literal — confirmed via read-back during editing.
- `apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx` contains `CLOSED_CONFIRMATION_STATES` and reads `importance['final_score']` (not `['score']`/`['level']`/`['importance']`) — confirmed via read-back during editing.
- `git log --oneline e33eb43~1..e22c911` returns exactly 3 commits (`e33eb43`, `95c9470`, `e22c911`), each touching only files within this plan's `files_modified` scope (verified via `git status --short` immediately before each commit).
- Plan-level `<verification>` command re-run: `npm run test -- --run src/test/schemas.test.ts src/test/liveContract.test.ts src/test/appSmoke.test.tsx` → 75/75 passed; `npm run build` → succeeded (tsc --noEmit clean, vite build produced `dist/`).
- Full frontend suite re-run: `npm run test -- --run` → 121/121 passed across 14 test files (up from the pre-plan baseline of 109/109 — all 12 new tests are additions from this plan).
- Cross-check: server-side Python contract baseline handed off from 36-02 (`test_ui_projection*.py` × 4 + `test_cockpit_transport_security.py`) re-run with `$env:PYTHONPATH` set → exit code 0 (74/74 passed), confirming this plan's frontend-only changes did not require and did not touch any Python file.
- `git status --short` after the final commit confirms `src/personal_knowledge/services/api_server.py` and the two new untracked files from the concurrently active other session remain exactly as found (untouched, unstaged by this plan).
