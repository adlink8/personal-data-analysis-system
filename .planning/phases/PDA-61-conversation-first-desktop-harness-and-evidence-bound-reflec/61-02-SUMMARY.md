# 61-02 SUMMARY — Approved Electron shell, IPC schema and preload boundary

**Plan:** 61-02 (type=execute, wave=2, autonomous=true, depends_on: 61-01)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | `src/desktop-api-schema.mjs` (537 LOC) + `test/main-preload.test.mjs` (608 LOC, 26 tests) created; RED run: 17 schema assertions pass, 9 main/preload contract assertions fail pointing at missing implementation (commit `fa59859`) |
| 2 | auto | ✅ PASS | Independent desktop package created; exact `npm install --save-dev --save-exact electron@43.3.0` (11s, 13 packages); lockfileVersion 3; lock entry version 43.3.0 + integrity exact-match APPROVED JSON; plan assertion passed (commit `cc3f5a0`) |
| 3 | auto | ✅ PASS | `main.mjs` (secure BrowserWindow + guards) + `preload.mjs` (minimal contextBridge) + schema polish; test suite **26/26 green** (commit `cfdd578`) |

## Verification

- `node --test apps/personal_intelligence_desktop/test/main-preload.test.mjs` → **26 pass / 0 fail**
- Task 2 assertion (`node -e` comparing qualification JSON vs package-lock/manifest) → PASS (approval valid, lockfileVersion 3, exact version/integrity, root devDependency)
- `git diff --check` → OK

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-UI-01 | Critical | CLOSED | named channel allowlist (15 intents), schema rejection, untrusted sender denial, no raw IPC exposure — A1/A2/A5/B5, A3/A4/A7/B7/B9, A15/B6, A17/B8 all pass |
| T-61-NAV-01 | High | CLOSED | hardened window config, strict CSP, navigation/new-window/permission denial — A13/B1, A14/B2, A16/B3/B4 pass |
| T-61-LEAK-01 | High | CLOSED | sentinel safe envelopes (ROUTE_PROVIDER_UNAVAILABLE without data, cancelled/outcome_unknown non-success), ConversationThreadView privacy ceiling — A3/A8-A12 pass |

## Deliverables

- `apps/personal_intelligence_desktop/package.json` / `package-lock.json` — electron@43.3.0 exact, devDependency only, no packager/registry/Cockpit/runtime deps
- `apps/personal_intelligence_desktop/src/main.mjs` — `createWindowConfig` (nodeIntegration:false, contextIsolation:true, sandbox:true, local preload), `CSP`, `installWindowGuards` (nav/new-window/permission denial), `installIpcHandlers` (15 named channels, sender+schema validation, `ROUTE_PROVIDER_UNAVAILABLE` until Plan 61-10 binds providers), Cache-Control no-store; Electron lazy-loaded so module is pure-Node testable
- `apps/personal_intelligence_desktop/src/preload.mjs` — `buildBridge(ipcRenderer)` exposes exactly 15 named methods, parses input before invoke, never exports ipcRenderer/generic invoke/send
- `apps/personal_intelligence_desktop/src/desktop-api-schema.mjs` — fixed intent schemas, ID namespace validation, safe-code envelopes, ConversationThreadView privacy ceiling

## Deviations / risks

- **Schema validation order** (contract-driven): `parsePayload` now validates provided keys before required-key check — more fail-closed (malformed/foreign IDs surface directly); all 17 schema assertions still pass under the new order.
- **sandbox preload ESM risk (recorded, non-blocking)**: `sandbox:true` Electron preload loads as CommonJS; ESM `preload.mjs` may not parse inside a real BrowserWindow. This plan creates no BrowserWindow (renderer wiring is Plan 61-11), and the `node --test` gate excludes that path. `preload.mjs` contains a guarded Electron runtime entry (lazy `await import("electron")` + exposeInMainWorld when `process.versions.electron` detected). **Plan 61-11 must switch to a self-contained CommonJS preload (e.g. `preload.cjs`) or empirically verify Electron 43 ESM-in-sandbox behavior**; `assertSecureWindowConfig` already permits `.cjs`.
- `npm start` not runnable yet: package.json has no `"main"` field and `renderer/index.html` not created — both are renderer-wiring scope (Plan 61-11); package.json/lock intentionally untouched here.
- No plan deviation otherwise; user-owned uncommitted changes preserved; Cockpit renderer not used as UI base.

## Self-Check: PASSED
