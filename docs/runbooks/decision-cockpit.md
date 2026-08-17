# Decision Cockpit runbook（个人决策驾驶舱运行手册）

**Status:** Phase 36 baseline closed (transport/CORS security + safe Projection
envelope + frontend DTO/vocabulary contract lock); Phase 37–40 (state/evidence,
decision workspace, feedback/proactive, hardening + Live UAT) not shipped.
**Audience:** humans and coding agents operating `apps/personal_decision_cockpit/`
and the REST backend that serves it.

## Goal

Run, test and build the Cockpit locally on Windows PowerShell, and know exactly
where the trust boundary sits: the browser only ever reads a versioned,
read-only server-owned Projection and only ever writes through the existing
`project + low` guarded session contract. This runbook does not describe a new
service, a new authority, or a Phase 40 Live UAT result — those stay in their
own phase's PLAN/SUMMARY/VERIFICATION.

## What actually owns what

- **rag-api (`http://127.0.0.1:8000`)** is the only backend process. It hosts
  the guarded `/agent/session/*` write endpoints. **Current status:** the
  Cockpit `/app` static hosting and the read-only `/ui/*` Projection dispatch
  blocks in `src/personal_knowledge/services/api_server.py` are commented out,
  so those routes currently return 404 even though the frontend build and docs
  exist. Start/stop it the same way as any other Phase 32+ REST consumer — see
  `docs/AGENTS.md` §3.3
  (`apps\personal_data_chatgpt\scripts\start-services.ps1`, or run
    `rag-api`/`python -m personal_knowledge.services.api_server` directly for a
    Cockpit-only session).
- **The Cockpit itself owns nothing.** It never opens SQLite/Chroma directly,
  never starts/stops/restarts REST, MCP (`8789`) or Tunnel (`8081`), and never
  computes lifecycle/current state, Serving Snapshot, Active Pointer or
  Calibration promotion client-side. Its system-status page only displays
  health probes it reads from the server.
- **The MCP Evidence Center widgets (`http://127.0.0.1:8789`)** are optional
  and only needed for the evidence drill-down panels; the rest of the Cockpit
  works without them (degrades to a documented `partial`).

## Build and test (Windows PowerShell, reproducible from project root)

```powershell
# from the project root, <repo-root> (or your own clone root)
Push-Location apps\personal_decision_cockpit
npm install
npm run test    # vitest run — Zod DTO/vocabulary + component + orchestration-client contracts
npm run build   # tsc --noEmit && vite build -> dist/
Pop-Location
```

`npm run build` clears and repopulates `dist/`; it is a build artifact, not a
tracked file (`apps/personal_decision_cockpit/.gitignore` ignores `dist/`,
`node_modules/`, `coverage/`, `.vite/`). rag-api serves whatever is currently
in `dist/` at `/app`; if it's missing or stale, `/app` returns the safe error
`cockpit_not_built` instead of a 500 or a stack trace — that means you need to
run `npm run build` again, not that the server is broken.

### Server-side contract tests that back this baseline

```powershell
Set-Location "<project-root>"
$env:PYTHONPATH = "$PWD\src"
python -m pytest `
  tests/contract/test_cockpit_transport_security.py `
  tests/contract/test_ui_projection.py `
  tests/contract/test_ui_projection_state_external.py `
  tests/contract/test_ui_projection_decision.py `
  tests/contract/test_ui_projection_actions_proactive.py `
  tests/contract/test_orchestration_interfaces.py -q
```

Real command output and pass/fail counts for this baseline are recorded in
`.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md`,
not repeated here — this runbook describes how to reproduce them, not what a
specific past run returned.

## Transport and mutation safety (what to expect, not just what to trust)

- Production Cockpit `/app` and `/ui/*` routes are currently disabled (404); when re-enabled, every call from
  the Cockpit is **same-origin** — no `Access-Control-Allow-Origin: *`, no ambient CORS
  trust.
- Dev-only cross-origin access (`npm run dev` on `5173` talking to rag-api on
  `8000`) is allowed only for an explicit allowlist: the built-in
  `127.0.0.1:5173`/`localhost:5173`, plus anything you add via
  `$env:PK_COCKPIT_DEV_ORIGINS = "http://127.0.0.1:5174,http://localhost:5174"`
  **before** starting rag-api. Anything else gets `403 origin_not_allowed` with
  no CORS header echoed back.
- Every `/agent/session/*` write route (`prepare`/`confirm`/`preview`/
  `execute` and its per-stage aliases) is Origin-gated *before* the request
  body is read — a rejected cross-origin request never reaches the orchestration
  layer and cannot create a session/ledger/authority side effect.
- The only write path the Cockpit ever uses is the pre-existing low-risk
  `project + low` guarded session contract: `prepare → exact preview →
  explicit confirm → idempotent execute`. UI confirmation is UX only; the
  server's own preview checksum and idempotency key are what actually gate a
  write. A repeated confirm with the same idempotency key replays the original
  event instead of writing twice.

## Fault checks and non-destructive recovery

| Symptom | Likely cause | Non-destructive fix |
|---|---|---|
| `/app` returns `cockpit_not_built` | `dist/` missing or empty | `npm run build` in `apps/personal_decision_cockpit`, then reload — no server restart needed |
| `/app/<path>` returns `cockpit_asset_not_found` | Wrong/stale asset path (e.g. after a rebuild changed hashed filenames) | Hard-refresh the browser; if it persists, rebuild |
| A dev-origin request gets `403 origin_not_allowed` | Origin not in the allowlist | Set `PK_COCKPIT_DEV_ORIGINS` and restart rag-api (env vars are read at process start, not per-request) — do **not** work around this by widening CORS in code |
| All write actions return `confirmation_secret_unavailable` | `PERSONAL_DATA_ORCHESTRATION_SECRET` not set on the rag-api process | Set that env var (≥32 random bytes) before starting rag-api; read-only pages are unaffected |
| The `generate` step of a session returns `generation_provider_unavailable` | Stock rag-api has no generation runner injected | Expected on a stock install; `publish` and later steps are unaffected, the session simply stops at `confirmed` |
| Any endpoint returns `internal_error` | Server-side exception (details only in local stderr) | Check the rag-api process's own stderr/log, not the HTTP response — the response body deliberately never contains `str(exc)`, a path, a secret, a provider body or a confirmation token/HMAC |

None of the fixes above requires restarting REST/MCP/Tunnel from the Cockpit
itself (it has no such control), touching a database file, or bypassing the
Origin/CORS gate — if a fix here would require that, stop and treat it as a
real incident, not a routine recovery step.

## Known scope boundary (do not read past this)

- This runbook documents Phase 36's transport/Projection/DTO baseline only. It
  does **not** describe Phase 37 (authority-aware state/external/evidence),
  Phase 38 (guarded decision workspace pages), Phase 39 (feedback/proactive/
  runtime truthfulness) or Phase 40 (hardening + a real browser UAT) as
  completed — those phases have their own PLAN/SUMMARY/VERIFICATION and are
  marked complete in `.planning/ROADMAP.md` (UAT accepted 2026-07-28); note
  the live `/app`/`/ui/*` routes are currently disabled in the dispatcher.
- Personal Knowledge Wiki / Topic Pages / backlinks / LLM Wiki narrative are a
  v1.5 candidate; they are not shipped, not read, not written by anything
  described here.
- No health/finance/relationship high-risk writes and no automatic external
  action or promotion exist behind the Cockpit — the only guarded write scope
  is the pre-existing `project + low` session contract.

## Related docs

- Phase 36 evidence: `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md`
- Cockpit README: `apps/personal_decision_cockpit/README.md`
- Write-flow contract: `apps/personal_decision_cockpit/docs/write-flow.md`
- Agent operating manual (service start/stop): `docs/AGENTS.md`
