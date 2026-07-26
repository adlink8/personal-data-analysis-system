---
phase: 36-secure-projection-and-cockpit-baseline
status: verified
verification_mode: executed
recorded: 2026-07-26T13:06:00Z
requirements:
  CCK-01: pass
  CCK-02: pass
  CCK-03: pass
  CCK-04: pass
technical_status: pass (77/77 Python contract + 121/121 Vitest + build ok)
security_status: pass (Origin gate + safe-error catalog + physical read-only re-verified)
scope_note: >
  Verifies Phase 36 (transport/CORS security, safe Projection envelope,
  frontend DTO/vocabulary hardening, auditable baseline) only. Phase 37-40
  page functionality and Phase 40 real-browser UAT are NOT verified here and
  remain pending their own phase plans.
---

# Phase 36: Secure Projection and Cockpit Baseline — Verification Record

**Recorded:** 2026-07-26T13:06Z (Windows PowerShell, project root `D:\ADLINK\数据分析`, branch `main`)

This document replaces the earlier `planned`/`future_execution` placeholder
version of this file with real, re-executed evidence gathered while closing
plan 36-04. Every command below was actually run in this session; unexecuted
scope (browser UAT, responsive/accessibility, live service-failure drills,
Phase 37-40 functionality) is explicitly listed as **not run** in §8, not
silently folded into a passing status.

## 1. What this baseline covers (and what it does not)

Phase 36 closes the **transport, Projection-envelope and frontend-DTO** layer
underneath the pre-existing (previously untracked) Cockpit implementation:

- 36-01: centralized same-origin/CORS `_origin_policy`, pre-delegation Origin
  gate on all 12 `/agent/session/*` write routes, allowlisted safe-error
  catalog for transport-layer responses.
- 36-02: allowlisted safe-failure catalog for `ui_projection.py`'s public
  limitations/errors, `run_missing`-aware empty-state mapping, physical
  read-only DB fingerprint + write-rejection regression, `confirmation_state`
  vocabulary-lock gate in `_classify_stage`.
- 36-03: Zod `envelope()` factory binds every `/ui/*` schema to
  `decision_cockpit_projection_v1` + its exact `operation` literal, regression
  proof against all 9 live fixtures, `OverviewPage.tsx` Now Stack fixed to use
  the real `confirmation_state`/`importance.final_score` vocabulary.
- 36-04 (this plan): audits the Cockpit's tracked/ignored file boundary,
  writes a reproducible PowerShell runbook, and records this evidence file.

**Not covered by this baseline** — still pending their own phase's plan
execution, tests and verification: Phase 37 (authority-aware state/external/
evidence pages), Phase 38 (decision workspace guarded write UI), Phase 39
(feedback/proactive/runtime pages), Phase 40 (hardening + a real browser
UAT). The Cockpit's `README.md` describes those pages' functional scope as an
implementation candidate — this file does not certify them as verified, and
no Phase-40 Live UAT checklist item is claimed complete here.

## 2. Completion conditions — requirement traceability (CCK-01..04)

| Requirement | Text (abridged) | Status | Evidence |
|---|---|---|---|
| CCK-01 | Read-only versioned Projection; browser never touches SQLite/Chroma directly, no shadow SSOT, no Serving Snapshot/Active Pointer/lifecycle/External authority/Calibration promotion change | **PASS** (Phase 36 scope) | `tests/contract/test_ui_projection.py::test_all_projection_operations_are_physically_read_only` (per-table row-count fingerprint across all 8 `/ui/*` ops + a real `decision_workspace.get`, zero rows changed anywhere) — part of the 77/77 run in §3 |
| CCK-02 | Production same-origin `/app`+API; no wildcard CORS; mutation rejects cross-origin, zero write | **PASS** (already marked `[x]` in `.planning/REQUIREMENTS.md` from 36-01) | `tests/contract/test_cockpit_transport_security.py` — 18 tests incl. `test_no_wildcard_cors_in_source`, `test_cross_origin_mutation_never_delegates_and_never_leaks` (proves zero `orchestration_rest_contract` calls across all 12 `SESSION_WRITE_ROUTES` on Origin rejection) |
| CCK-03 | Safe `partial`/freshness/snapshot-binding/limitations on authority failure; no exception text/path/PII/secret/provider body/confirmation-token/HMAC in DOM/console/API error | **PASS** (Phase 36 scope) | Server: `test_authority_failure_never_leaks_exception_detail`, `test_personal_state_changes_failure_never_leaks_exception_detail`, `test_actions_recent_single_item_failure_never_leaks_exception_detail`, `test_calibration_overview_single_protocol_failure_never_leaks_exception_detail` (poisoned-fragment injection: fake path, `sk-test-...`, `Bearer ...`, provider-shaped JSON, `confirmation_token`/HMAC strings — none reach the public envelope). Frontend: `apps/personal_decision_cockpit/src/test/schemas.test.ts` `apiGet` suite (6 tests, same poisoned-fragment technique against `ApiError.message` + asserts zero `console.*` calls) |
| CCK-04 | Cockpit/Projection/contract tests/build instructions enter an auditable, versioned baseline; unverified WIP not claimed shipped in README/plans | **PASS** (this plan) | §4 (tracked/ignored audit), §6 (README overstatement fixed), this file itself |

`.planning/REQUIREMENTS.md` checkbox updates for CCK-01/03/04 are deferred to
the orchestrator's phase-close tracking pass (that file is not in this plan's
`files_modified`); the underlying evidence is recorded here.

## 3. Automated gates — commands actually executed in this session

### 3.1 Frontend — Vitest

```powershell
Set-Location apps\personal_decision_cockpit
npm run test
```

**Result:** `Test Files 14 passed (14)`, `Tests 121 passed (121)`. Duration
3.58s. Zero failures. (React Router "future flag" warnings on stderr are
library deprecation notices, not test failures.)

### 3.2 Frontend — build

```powershell
Set-Location apps\personal_decision_cockpit
npm run build
```

**Result:** `tsc --noEmit` clean, `vite build` succeeded — `dist/index.html`
(0.52 kB), `dist/assets/index-*.css` (16.89 kB), `dist/assets/index-*.js`
(467.39 kB) emitted. Exit 0.

### 3.3 Server — Python contract suite

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

**Result:** exit 0. Per-file collected/passed counts (collect-only cross-check
against the dot-count in the `-q` run — both agree):

| File | Tests |
|---|---:|
| `test_cockpit_transport_security.py` | 18 |
| `test_orchestration_interfaces.py` | 3 |
| `test_ui_projection.py` | 10 |
| `test_ui_projection_actions_proactive.py` | 21 |
| `test_ui_projection_decision.py` | 17 |
| `test_ui_projection_state_external.py` | 8 |
| **Total** | **77 passed, 0 failed** |

This is the same 74 (36-01/36-02 handoff baseline: transport 18 + the 4
`ui_projection*` files' 56) plus `test_orchestration_interfaces.py`'s 3, all
still green after 36-03's frontend-only changes and after this plan's
`.gitignore`/README/runbook-only edits (no Python/TS source file touched by
36-04 itself).

### 3.4 Whitespace/diff hygiene

```powershell
git diff --check
```

**Result:** exit 0, no output (no trailing-whitespace/conflict-marker
violations). Note: this ran against the *full* working tree's unstaged diff
at the time, which includes the other session's concurrent `.planning` reorg
and `api_server.py`/`build_knowledge_units_prod.py` edits (see §7) — `git
diff --check` has no path restriction applied here, so this is not scoped to
only this plan's files. Re-running it path-scoped to this plan's own changed
files would also pass trivially since none of them have whitespace issues.

### 3.5 Cockpit ignore-boundary audit

```powershell
git check-ignore -v apps/personal_decision_cockpit/node_modules apps/personal_decision_cockpit/dist
git status --short -- apps/personal_decision_cockpit
```

**Result:** `node_modules/` and `dist/` both resolve to
`apps/personal_decision_cockpit/.gitignore` rules (lines 1-2); `git status
--short -- apps/personal_decision_cockpit` shows only `M
apps/personal_decision_cockpit/README.md` (the pre-existing, not-this-plan's
dirty edit — see §6/§7). No database, PID, secret, log or unrelated-worktree
file appears under `apps/personal_decision_cockpit/`.

## 4. Tracked/ignored baseline boundary (Task 1)

`apps/personal_decision_cockpit/.gitignore` now ignores `node_modules/`,
`dist/`, `coverage/`, `.vite/`, `*.tsbuildinfo`, `*.local` — the directory
listing confirmed only `dist/`, `node_modules/`, `docs/`, `src/` exist under
`apps/personal_decision_cockpit/` in this environment (no coverage output, no
stray browser/test artifacts, no `.env*` files). `src/`, `docs/`,
`package.json`, `package-lock.json`, `tsconfig*.json`, `vite.config.ts`,
`tailwind.config.*`, `postcss.config.*`, `.gitignore` and `README.md` remain
tracked and are the audited Cockpit baseline surface.

## 5. Required negative evidence (physical safety properties re-verified)

| Scenario | Expected result | Re-verified by |
|---|---|---|
| Cross-origin `POST`/preflight to `/agent/session/*` | Rejected before delegation; all authority fingerprints unchanged | `test_cross_origin_mutation_never_delegates_and_never_leaks` — all 12 `SESSION_WRITE_ROUTES` reject a mismatched-Origin POST with `403 origin_not_allowed` and record **zero** calls into `orchestration_rest_contract` |
| Projection exception | Typed safe limitation; no `str(exc)`, path, HMAC, raw evidence or provider body | §2/CCK-03 poisoned-fragment tests (server + frontend) |
| Wrong operation/schema on a `/ui/*` payload | Browser parse failure; no fallback to a different endpoint | 36-03's `liveContract.test.ts`/`schemas.test.ts` tamper + cross-endpoint-swap tests (part of the 121/121 frontend run in §3.1) |
| Missing/partial authority | Read-only recovery; no fabricated current data | `_SAFE_FAILURE_CODES`-routed limitation tests in `test_ui_projection*.py` (part of §3.3's 77) |
| Physical DB write attempt through the read-only Projection connection | Rejected by SQLite itself | `test_all_projection_operations_are_physically_read_only` — same-mode (`mode=ro`+`query_only=ON`) connection write-rejection assertion, plus the per-table row-count fingerprint across all 4 authority DBs before/after all 8 `/ui/*` ops (zero rows changed anywhere) |
| Provider/external-action/promotion side effect from any UI-facing route in this suite | None occurs | None of the 77 tests in §3.3 construct or call a network provider, external-action client, or Calibration-promotion path; `orchestration_rest_contract`'s only invocation paths exercised here are either rejected pre-delegation (Origin gate) or run against the existing project-scoped `GuardedOrchestrationInterface` fixture stubs already covered by Phase 33's own contract |

## 6. README truthfulness fix (Task 1/2, D-36-07/T-36-11)

The prior `apps/personal_decision_cockpit/README.md` stated, verbatim:
*"Phase 40（硬化与 Live UAT）已完成：无障碍/响应式/状态模型/隐私审计修复 +
全路由冒烟测试 + 上方验收清单。"* directly above a Live-UAT checklist whose
every item was an **unchecked** `- [ ]` box — an internally contradictory,
overstated claim. This session's working-tree edit:

- Added a status banner at the top of the README stating only Phase 36 is
  closed, Phase 37-40 are pending, and the functional description below is an
  implementation candidate, not a shipped/verified feature list.
- Replaced the false "Phase 40 已完成" line with an explicit "Phase 40 尚未执行"
  statement clarifying that `npm run test`/`npm run build` passing is not
  equivalent to a Phase 40 real-browser UAT.
- Relabeled the checklist section heading to "Phase 40 — 未执行" with an
  explicit note that all unchecked boxes mean not-yet-run, not an omission.
- Added a "安全与传输边界（Phase 36 基线）" section documenting same-origin
  production serving, the `PK_COCKPIT_DEV_ORIGINS` dev-CORS allowlist, the
  Origin gate on `/agent/session/*`, the sole `project + low` guarded write
  path, and that the browser never starts/stops REST/MCP/Tunnel/Chroma or
  touches SQLite/Chroma directly.
- Marked `npm install`/`npm run dev`/`npm run build`/`npm run test` code
  fences as `powershell` and added a one-line PowerShell-reproducibility note.

**Commit status:** see §7 — this edit is applied in the working tree but was
**not committed** by this plan, because the file already carried an unrelated
uncommitted one-line change from a concurrently active session before this
plan started (shared-tree discipline: do not commit a file that was already
dirty with someone else's uncommitted change).

## 7. Environment caveats (not Phase 36 deliverable defects)

Two kinds of concurrent-session artifacts were observed and are recorded here
for auditability, not fixed by this plan (out of `files_modified` scope, and
fixing someone else's in-flight uncommitted work is explicitly out of bounds
for a shared-tree executor):

1. **`apps/personal_decision_cockpit/README.md` pre-existing dirt.** Before
   this plan started, `git diff apps/personal_decision_cockpit/README.md`
   already showed a one-line change (updating the design-contract path
   reference from the retired
   `.planning/PERSONAL-DECISION-COCKPIT-UI-SPEC-2026-07-19.md` to
   `.planning/research/v1.4-decision-cockpit-ui/UI-SPEC.md`, consistent with
   the other session's broader `.planning` reorg visible in `git status`).
   This plan's required README edits (§6) were applied on top of that
   pre-existing change in the working tree, but the file was **not staged or
   committed** by this plan per the shared-tree rule — both this plan's edits
   and the other session's edit remain uncommitted in the working tree.

2. **Uncommitted `src/personal_knowledge/services/api_server.py` changes
   outside Phase 36 scope.** A `git diff` of that file (uncommitted, from the
   other concurrently active session) shows two new routes added under a
   "999.5 单人评审台" comment banner:
   - `GET /ui/review` — serves an HTML page via
     `eval_review.build_review_page()`.
   - `POST /ui/review/labels` — calls `eval_review.save_review_labels(body)`
     and, on `ValueError`, returns the error via `_err(str(exc), 400)` — i.e.
     it **does not** use the 36-01 `_SAFE_ERRORS`/`_safe_error()` allowlisted-
     code pattern and could echo exception text in the response body.
   - Neither route is registered in `SESSION_WRITE_ROUTES` (the 36-01
     Origin-gate dict), so `POST /ui/review/labels` is a write route **not**
     covered by the pre-delegation Origin gate that this phase's threat model
     (T-36-01/T-36-02) established for `/agent/session/*`.

   This is explicitly **not a Phase 36 deliverable defect**: `/ui/review*` is
   unrelated 999.5 (eval-review tooling) work, added to this file after
   36-01/36-02 closed, by a different in-flight session, and is not part of
   this plan's or any 36-0x plan's `files_modified`. It is recorded here only
   so a future reader of this file is not misled into thinking Phase 36's
   Origin-gate/safe-error coverage is complete for *every* route in
   `api_server.py` — it is complete for the routes Phase 36 actually scoped
   (`/agent/session/*` writes and `/app` static hosting), and this new route
   is a gap for whichever phase/plan claims ownership of `/ui/review*`.

## 8. Human check / explicitly not run in this session (do not infer pass/fail)

- Any real browser session (Chrome/Edge/Firefox) against a running
  `npm run build` + rag-api `/app` while a service is unavailable, to confirm
  a bounded recovery message rather than a false healthy state — **not run**.
  No Phase 40 Live-UAT checklist item in the README is claimed complete by
  this file.
- Responsive/accessibility checks (320/768/1024/1440px, keyboard nav, reduced
  motion, 200% zoom) — **not run**.
- Live service-failure drills (stopping REST/MCP/Chroma mid-session and
  observing degradation) — **not run**; covered only at the unit/contract
  level by the tests in §3.3/§5.
- `PERSONAL_DATA_ORCHESTRATION_SECRET`/generation-runner-injected end-to-end
  session flow through a live rag-api process — **not run**; covered only by
  the existing Phase 33 `GuardedOrchestrationInterface` contract tests
  (`test_orchestration_interfaces.py`, 3 tests, included in §3.3's 77).
- Any change to, or re-verification of, Phase 37-40 page functionality,
  `.planning/REQUIREMENTS.md` checkbox state, or `.planning/ROADMAP.md`/
  `.planning/STATE.md` tracking — **not run/not modified** by this plan (see
  §9).

## 9. ROADMAP/STATE tracking (deferred, not committed)

Per the shared-tree discipline for this run, `.planning/ROADMAP.md`'s Phase 36
"Plans: 3/4 plans executed" line and the Progress table's Phase 36 row, plus
`.planning/STATE.md`'s "Current Position" block, should be advanced to reflect
36-04 (this plan) as the 4th and final Phase 36 plan, closing Phase 36. Both
files already carry a large set of unrelated uncommitted changes from another
session's `.planning` reorganization at the time this plan ran, so — per the
explicit shared-tree instruction for this session — **no edit was made to
either file by this plan**; the orchestrator should fold Phase 36's closure
into whatever tracking commit closes out the phase.

## 10. Passing rule

All four requirements (CCK-01..04) have passing automated evidence scoped to
Phase 36's transport/Projection/DTO baseline (§2-§5); the cross-origin
mutation test and safe-error/poisoned-fragment inspections are the blocking
security gates and both pass. This document now reflects `status: verified`
for Phase 36 specifically — **not** for Phase 37-40 or v1.4 as a whole, which
remain `planned`/pending their own phase plans and verification records (§1,
§8).

## 11. Commit ledger for this phase (for cross-reference)

| Plan | Commits |
|---|---|
| 36-01 (transport security) | `4ac1400`, `da954a1`, `4e32053` |
| 36-02 (safe Projection envelope) | `ae80a01`, `302360d`, `be8c931` |
| 36-03 (frontend DTO/vocabulary hardening) | `e33eb43`, `95c9470`, `e22c911` |
| 36-04 (this plan — auditable baseline) | `abe4fe9` (`.gitignore`), `9cdf7d7` (runbook), plus this file's own commit |
