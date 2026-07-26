---
phase: 36-secure-projection-and-cockpit-baseline
plan: 01
subsystem: api
tags: [cors, origin-policy, http-server, security, cockpit]

# Dependency graph
requires:
  - phase: 33-guarded-decision-orchestration
    provides: session write routes (`/agent/session/*`) and `GuardedOrchestrationInterface`/`orchestration_rest_contract` that this plan now gates by Origin
provides:
  - Centralized Origin policy (`_origin_policy`) as the single decision point for CORS response headers and cross-origin mutation rejection
  - Removal of unconditional wildcard `Access-Control-Allow-Origin: *`
  - Pre-delegation Origin gate on all 12 `/agent/session/*` write routes
  - Shared allowlisted safe-error catalog (`_SAFE_ERRORS`/`_safe_error`) for static asset, Origin rejection and internal error responses
affects: [37-authority-aware-state-and-evidence, 38-guarded-project-decision-workspace, 39-truthful-feedback-and-runtime, 40-browser-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Single Origin-policy function (`_origin_policy`) consumed by both response-header emission (`_send`) and the pre-delegation mutation gate (`do_POST`) — one decision point, not duplicated logic"
    - "Allowlisted public error catalog (`_SAFE_ERRORS`/`_safe_error`) separates safe client-facing code/message from local `traceback.print_exc()` diagnostics"
    - "Real `ThreadingHTTPServer` on an ephemeral port for HTTP-layer contract tests (Origin/CORS/preflight behavior cannot be verified by calling service functions directly)"

key-files:
  created:
    - tests/contract/test_cockpit_transport_security.py
  modified:
    - src/personal_knowledge/services/api_server.py

key-decisions:
  - "Origin policy allows three cases (no Origin / same-origin-as-Host / explicit dev allowlist via PK_COCKPIT_DEV_ORIGINS env var) and rejects everything else — applies uniformly to CORS header emission and the mutation gate"
  - "Dev-origin allowlist defaults to the Vite dev-server ports (127.0.0.1:5173, localhost:5173) and is extendable only via a server-launch-time env var, never from request content"
  - "Origin gate for /agent/session/* runs before body is read/parsed, so a rejected cross-origin request never reaches orchestration_rest_contract and cannot affect session/ledger/authority state"
  - "Safe-error catalog is a fixed literal-keyed dict; callers can only pass hardcoded code constants, never user/exception-derived strings, which structurally prevents leakage"

patterns-established:
  - "Any future Handler response path that needs a public error should add a code to _SAFE_ERRORS and call _safe_error(), not interpolate str(exc)/path into _err()"

requirements-completed: [CCK-02]

# Metrics
duration: 55min
completed: 2026-07-26
---

# Phase 36 Plan 01: Secure Projection and Cockpit Baseline — Transport Security Summary

**Removed wildcard CORS and added a centralized Origin policy in `api_server.py` that rejects cross-origin `/agent/session/*` mutations before they reach `orchestration_rest_contract`, plus a shared safe-error catalog that stops static-asset and internal-error responses from echoing paths or exception text.**

## Performance

- **Duration:** 55 min
- **Started:** 2026-07-26T10:22:00Z
- **Completed:** 2026-07-26T11:17:01Z
- **Tasks:** 3
- **Files modified:** 2 (1 created, 1 modified)

## Accomplishments
- `_origin_policy()` is now the single decision point deciding both (a) whether a response gets a scoped `Access-Control-Allow-Origin` header and (b) whether a session-write POST is allowed to proceed — no more unconditional `Access-Control-Allow-Origin: *`.
- Every one of the 12 `/agent/session/*` write routes rejects a mismatched-Origin POST with `403 origin_not_allowed` before the JSON body is parsed and before `orchestration_rest_contract` is ever called (proven with a call-count stub across all 12 routes in one test).
- `/app` static-asset-not-found, `/app` traversal fallback, Origin rejection (`do_OPTIONS` and `do_POST`), and the generic internal-error handlers in both `do_GET`/`do_POST` all now share one allowlisted `_SAFE_ERRORS`/`_safe_error()` catalog; none of them interpolate the request path or `str(exc)` into the response anymore.
- 18 new HTTP-level contract tests using a real `ThreadingHTTPServer` on an ephemeral port, covering no-Origin/same-origin/dev-Origin/unknown-Origin behavior for both GET/OPTIONS and the mutation gate, plus safe-error-content assertions with injected fake tokens/HMAC/paths.

## Task Commits

Each task was committed atomically:

1. **Task 1: 集中定义 Cockpit Origin 与 CORS 响应策略** - `4ac1400` (feat)
2. **Task 2: 在所有受控 session 写入前执行 Origin gate** - `da954a1` (feat)
3. **Task 3: 收紧静态 Cockpit 与 transport 错误的公开信息** - `4e32053` (fix)

**Plan metadata:** commit pending (this SUMMARY + STATE/ROADMAP update)

## Files Created/Modified
- `src/personal_knowledge/services/api_server.py` - Origin policy (`_origin_policy`, `_dev_allowed_origins`, `_same_origin`), `SESSION_WRITE_ROUTES` module constant, pre-delegation mutation gate in `do_POST`, Origin-aware CORS in `_send`/`do_OPTIONS`, and the `_SAFE_ERRORS`/`_safe_error` safe public error catalog
- `tests/contract/test_cockpit_transport_security.py` - New HTTP-level contract suite (real `ThreadingHTTPServer`) covering CORS/preflight Origin behavior, cross-origin mutation rejection with zero-delegation proof, and safe-error content assertions

## Decisions Made
- Origin policy treats "Origin equals the request's own Host header" as same-origin (production Cockpit case) and does not require an ACAO response header for it — matches how browsers treat genuinely same-origin fetches, and is verified by constructing the Origin from the live test server's own `host:port`.
- Dev-origin allowlist is intentionally small and explicit (`PK_COCKPIT_DEV_ORIGINS` env var, defaulting to Vite's `127.0.0.1:5173`/`localhost:5173`) rather than pattern-matching, to avoid accidentally widening the browser-mutation attack surface documented in the phase threat model (T-36-01/T-36-02).
- `_safe_error(code, status)` only accepts fixed literal `code` strings defined in `_SAFE_ERRORS`; this is a structural (not just behavioral) guarantee that request-derived content can never reach the public error body, satisfying D-36-06 without relying on developer discipline at each call site.

## Deviations from Plan

None - plan executed exactly as written. The three tasks were implemented as a single coherent edit first, then re-staged into three atomic commits matching the plan's task boundaries (Task 1: CORS/Origin policy plumbing with an ad hoc inline safe-rejection body; Task 2: mutation gate reusing the same ad hoc body; Task 3: consolidating both ad hoc bodies into the shared `_SAFE_ERRORS`/`_safe_error` catalog plus fixing the two remaining leak points). This re-staging is a mechanical git-history choice, not a functional deviation — each intermediate commit was independently tested and passes its task's `<verify>` command.

## Issues Encountered

**Pre-existing unrelated test failure (not introduced by this plan):** `tests/contract/test_ui_projection.py::test_proactive_failure_isolated_as_partial` fails on a stock `git checkout` of the pre-plan `HEAD` commit (verified via `git stash` before making any changes) — some other `overview.get` authority section returns `error` in this environment instead of the expected `ok`/`empty`, unrelated to CORS/Origin/transport. This is outside 36-01's scope (`src/personal_knowledge/services/ui_projection.py` is not a files_modified target of this plan) and is left as-is; it should be triaged separately, e.g. under Phase 36-02 (safe Projection envelope) or as its own fix.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `/agent/session/*` mutation routes are now closed to cross-origin browser requests; Cockpit page-level work (Phase 37+) can proceed without widening this boundary.
- The safe-error catalog pattern (`_SAFE_ERRORS`/`_safe_error`) is established in `api_server.py` and should be reused/extended by 36-02 when hardening `ui_projection.py`'s own limitation/error surface (D-36-06 applies there too).
- Blocker for follow-up (not blocking this plan): the pre-existing `test_proactive_failure_isolated_as_partial` failure noted above should be triaged before or during 36-02, since that plan touches `ui_projection.py`'s error/limitation handling directly.

---
*Phase: 36-secure-projection-and-cockpit-baseline*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `src/personal_knowledge/services/api_server.py` exists and contains `SESSION_WRITE_ROUTES`, `_origin_policy`, `_safe_error` — confirmed via `grep`.
- `tests/contract/test_cockpit_transport_security.py` exists on disk — confirmed via file read.
- `git log --oneline --all --grep="36-01"` returns 3 commits (`4ac1400`, `da954a1`, `4e32053`).
- All task-level `<verify>` commands re-run and pass (see below); plan-level `<verification>` command re-run: `python -m pytest tests/contract/test_cockpit_transport_security.py tests/contract/test_ui_projection.py tests/contract/test_orchestration_interfaces.py -q` → `1 failed, 27 passed` (the 1 failure is the pre-existing, out-of-scope `test_proactive_failure_isolated_as_partial` documented above; all 27 other tests, including every new test added by this plan, pass).
- Acceptance criteria re-verified per task:
  - Task 1: no literal `Access-Control-Allow-Origin", "*"` in source (`grep` clean); dev-Origin preflight gets scoped headers; unknown-Origin preflight gets no ACAO and a safe 403 body — all PASS.
  - Task 2: all 12 `SESSION_WRITE_ROUTES` reject mismatched-Origin POST with 403/`origin_not_allowed` and zero `orchestration_rest_contract` calls; same-Origin/no-Origin/dev-Origin mutation paths still reach the orchestration stub — all PASS.
  - Task 3: missing/traversed `/app` asset returns `cockpit_asset_not_found` without echoing the request path; forced internal exception returns `internal_error` without leaking injected fake token/HMAC/path text; `_SAFE_ERRORS` catalog entries are static and code-keyed — all PASS.
