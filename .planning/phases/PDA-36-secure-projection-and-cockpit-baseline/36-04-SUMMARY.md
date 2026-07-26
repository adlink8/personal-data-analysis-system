---
phase: 36-secure-projection-and-cockpit-baseline
plan: 04
subsystem: docs
tags: [cockpit, gitignore, runbook, verification, audit-baseline, shared-tree]

# Dependency graph
requires:
  - phase: 36-secure-projection-and-cockpit-baseline
    provides: "36-01 transport security, 36-02 safe Projection envelope, 36-03 frontend DTO/vocabulary hardening — this plan closes the phase by auditing the tracked/ignored baseline, writing a reproducible runbook and recording real verification evidence for all three"
provides:
  - Cockpit `.gitignore` hardened (`coverage/`, `.vite/`, `*.tsbuildinfo` added alongside existing `node_modules/`, `dist/`, `*.local`) and audited: `git status --short -- apps/personal_decision_cockpit` shows no stray database/PID/secret/log/unrelated-worktree file
  - New reproducible PowerShell runbook `docs/runbooks/decision-cockpit.md` — install/test/build commands, same-origin/CORS/mutation-gate boundary, fault-check-and-non-destructive-recovery table, explicit Phase 37-40/Wiki "not shipped" scope boundary
  - `36-VERIFICATION.md` rewritten from a `planned`/`future_execution` placeholder to real, re-executed evidence: CCK-01..04 traceability, 77/77 Python contract + 121/121 Vitest + build results, physical-read-only/Origin-gate re-verification, and an explicit environment-caveat record of another session's uncommitted `/ui/review*` routes in `api_server.py`
  - README overstatement fix (working tree only, not committed — see Deviations): removed the false "Phase 40 已完成" claim sitting above an all-unchecked Live-UAT checklist; added a Phase-36-only status banner, a same-origin/CORS/`project + low` security-boundary section, and PowerShell-explicit command fences
affects: [37-authority-aware-state-and-evidence, 38-guarded-project-decision-workspace, 39-truthful-feedback-and-runtime, 40-browser-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "VERIFICATION.md as a living evidence record, not a plan-time placeholder: this plan replaced 36-VERIFICATION.md's pre-existing `status: planned`/`verification_mode: future_execution` frontmatter with `status: verified`/`verification_mode: executed` plus a `scope_note` that scopes 'verified' strictly to Phase 36, not v1.4 as a whole — future phases' own VERIFICATION.md should follow the same explicit-scope pattern rather than letting 'verified' read as milestone-wide"
    - "Shared-tree README handling: when a files_modified target is already dirty with another session's unrelated change, still apply the plan's required edits to the working-tree file (so the content is correct going forward) but commit nothing for that file — document the deferral with enough detail (exact pre-existing diff, exact new edits) that a future commit can cleanly separate the two"

key-files:
  created:
    - docs/runbooks/decision-cockpit.md
  modified:
    - apps/personal_decision_cockpit/.gitignore
    - .planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md
    - apps/personal_decision_cockpit/README.md (working tree only, not committed)
    - .planning/ROADMAP.md (working tree only, not committed)
    - .planning/STATE.md (working tree only, not committed)

key-decisions:
  - "README.md was already dirty with an unrelated one-line change (design-contract path reference update, part of the other session's `.planning` reorg) when this plan started. Per the shared-tree special-case instruction, this plan's required README edits were applied on top of it in the working tree but the file was never staged/committed by this plan — the deferral, the exact pre-existing diff and the exact new edits are all recorded in `36-VERIFICATION.md` §6-§7 so a future commit (by whichever session/orchestrator resolves the reorg) can separate the two changes cleanly."
  - "`.planning/ROADMAP.md` and `.planning/STATE.md` progress lines (Phase 36 → 4/4 plans executed / Closed) were edited in the working tree only, not committed, per the explicit shared-tree instruction that these two files carry unrelated dirt from another session's reorg; the orchestrator folds Phase 36's closure into whatever tracking commit closes out the phase."
  - "The other session's uncommitted `api_server.py` additions (`GET /ui/review`, `POST /ui/review/labels` under a '999.5 单人评审台' banner) were investigated (via `git diff`) and found to (a) not be covered by the 36-01 `SESSION_WRITE_ROUTES` Origin gate and (b) use `_err(str(exc), 400)` instead of 36-01's `_safe_error()` allowlisted-code pattern. This was recorded as an explicit environment caveat in `36-VERIFICATION.md` §7 — not fixed, not reverted, not treated as a Phase 36 defect — because it is unrelated 999.5 work outside this plan's and every 36-0x plan's `files_modified` scope, added by a different in-flight session."
  - "`.planning/REQUIREMENTS.md` CCK-01/03/04 checkboxes were deliberately left unedited (that file is not in this plan's `files_modified`); `36-VERIFICATION.md` records the underlying PASS evidence and explicitly notes the checkbox update is deferred to the orchestrator's phase-close tracking pass."

patterns-established:
  - "Any future phase's closure plan should treat its own VERIFICATION.md the same way: re-run every command listed in the plan's task `<verify>` blocks in the actual closure session (not trust an earlier plan's cached numbers), and explicitly list what was NOT run rather than omitting it — an absent section reads as 'not considered', a present 'not run' section reads as 'considered and honestly bounded'."

requirements-completed: [CCK-01, CCK-03, CCK-04]

# Metrics
duration: ~65min
completed: 2026-07-26
---

# Phase 36 Plan 04: Secure Projection and Cockpit Baseline — Auditable Baseline Closure Summary

**Closed Phase 36 by auditing the Cockpit's tracked/ignored file boundary, writing a reproducible Windows-PowerShell runbook (`docs/runbooks/decision-cockpit.md`), replacing `36-VERIFICATION.md`'s planning-time placeholder with real re-executed evidence (77/77 Python contract tests, 121/121 Vitest, successful build, physical-read-only and Origin-gate re-verification), and fixing the Cockpit README's overstated "Phase 40 已完成" claim — while working around another session's concurrent, unrelated `.planning` reorg and uncommitted `api_server.py`/README.md edits without touching or committing any of them.**

## Performance

- **Duration:** ~65 min
- **Started:** 2026-07-26T12:45:00Z (approx.)
- **Completed:** 2026-07-26T13:15:00Z (approx.)
- **Tasks:** 3
- **Files created/modified (committed):** 3 (1 created, 2 modified)
- **Files modified (working tree only, not committed):** 3 (`README.md`, `.planning/ROADMAP.md`, `.planning/STATE.md`)

## Accomplishments

- Audited `apps/personal_decision_cockpit/`'s tracked/ignored boundary: confirmed via `git check-ignore -v` and `git status --short -- apps/personal_decision_cockpit` that `node_modules/`/`dist/` are correctly ignored and no database, PID, secret, log or unrelated-worktree file has leaked into the Cockpit directory; hardened `.gitignore` with `coverage/`, `.vite/`, `*.tsbuildinfo` as defense-in-depth against future generated artifacts.
- Wrote `docs/runbooks/decision-cockpit.md`: a from-scratch, Windows-PowerShell-reproducible runbook covering install/test/build commands, which process owns what (`rag-api` on `8000` is the only backend; the Cockpit itself starts/stops nothing and never touches SQLite/Chroma directly), the same-origin/CORS/`PK_COCKPIT_DEV_ORIGINS` boundary, the sole `project + low` guarded write path, a fault-check table (`cockpit_not_built`, `origin_not_allowed`, `confirmation_secret_unavailable`, `generation_provider_unavailable`, `internal_error`) with non-destructive recovery steps, and an explicit "not shipped" boundary for Phase 37-40 and the v1.5 Wiki candidate.
- Re-executed every command named in this plan's task-3 `<verify>` block in this session and recorded the real results in `36-VERIFICATION.md`: frontend `npm run test` → 121/121 across 14 files; `npm run build` → clean `tsc --noEmit` + successful `vite build`; the six named Python contract files → 77/77 passed (18 transport + 3 orchestration + 10/8/17/21 across the four `ui_projection*` files); `git diff --check` → clean.
- Rewrote `36-VERIFICATION.md` end to end: it previously held a plan-time `status: planned`/`verification_mode: future_execution` placeholder written before any of 36-01/02/03 executed. It now has `status: verified` scoped explicitly to Phase 36 (via a `scope_note` in frontmatter and repeated in-body caveats) with per-requirement (CCK-01..04) evidence citations down to specific test function names, a required-negative-evidence table, and two fully documented environment caveats.
- Investigated and documented (without fixing) the other session's uncommitted `api_server.py` additions: `GET /ui/review` and `POST /ui/review/labels` (999.5 eval-review tooling) are not covered by the 36-01 `SESSION_WRITE_ROUTES` Origin gate, and the latter's error path uses `_err(str(exc), 400)` rather than 36-01's `_safe_error()` allowlisted catalog — recorded as an explicit, clearly-labeled environment caveat in `36-VERIFICATION.md` §7, not a Phase 36 defect.
- Fixed the Cockpit README's core truthfulness bug (D-36-07/T-36-11): it previously stated *"Phase 40（硬化与 Live UAT）已完成"* directly above a Live-UAT checklist where every item was an unchecked `- [ ]` box. Replaced with an explicit "Phase 40 尚未执行" statement, a Phase-36-only status banner at the top of the file, a new "安全与传输边界（Phase 36 基线）" section, and PowerShell-explicit command fences — applied in the working tree but not committed (see Deviations).

## Task Commits

Each task was committed atomically, scoped to only its own file(s) (verified with `git status --short` immediately before every commit — never `git add -A`/`git add .`):

1. **Task 1: 界定可跟踪 Cockpit 基线与忽略边界** - `abe4fe9` (chore) — `.gitignore` only; README edit applied in working tree, not committed (pre-existing dirt)
2. **Task 2: 编写可复现且不越权的 Cockpit 运行说明** - `9cdf7d7` (docs) — new `docs/runbooks/decision-cockpit.md` only; README edit applied in working tree, not committed
3. **Task 3: 执行受限基线验证并记录事实证据** - `70b2098` (docs) — `36-VERIFICATION.md` only

**Plan metadata:** this SUMMARY commit (docs), to follow.

## Files Created/Modified

- `apps/personal_decision_cockpit/.gitignore` — added `coverage/`, `.vite/`, `*.tsbuildinfo` alongside the existing `node_modules/`, `dist/`, `*.local`
- `docs/runbooks/decision-cockpit.md` — new file: PowerShell install/test/build, service-ownership boundary, transport/mutation-safety summary, fault-check/recovery table, explicit not-shipped scope
- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md` — rewritten from a plan-time placeholder to real, commands-actually-run evidence
- `apps/personal_decision_cockpit/README.md` — status banner, "Phase 40 已完成" → "Phase 40 尚未执行" fix, checklist-section relabel, new security-boundary section, PowerShell command fences — **working tree only, not committed** (see Deviations)
- `.planning/ROADMAP.md` — Phase 36 "Plans: 3/4" → "4/4 … Closed" and the Progress-table row updated — **working tree only, not committed** (shared-tree rule)
- `.planning/STATE.md` — Current Position advanced to Phase 36 CLOSED / Phase 37 next — **working tree only, not committed** (shared-tree rule)

## Decisions Made

See `key-decisions` in frontmatter. Summarized: README's pre-existing dirt (an unrelated design-contract-path fix from the other session's `.planning` reorg) meant this plan's required README edits were applied but never committed — the exact split is documented in `36-VERIFICATION.md` so it can be cleanly separated later; ROADMAP/STATE progress edits follow the same working-tree-only rule per the explicit coordinator instruction; the other session's uncommitted `/ui/review*` routes in `api_server.py` were investigated and documented as an environment caveat rather than touched; `.planning/REQUIREMENTS.md` checkbox updates for CCK-01/03/04 were deliberately left to the orchestrator since that file isn't in this plan's scope.

## Deviations from Plan

**1. [Shared-tree special case, exactly as pre-briefed] `apps/personal_decision_cockpit/README.md` edits made but not committed**

- **Found during:** Task 1, first `git diff apps/personal_decision_cockpit/README.md` check (run before any edit, per the coordinator's explicit shared-tree instruction)
- **Issue:** The plan's Task 1/2/3 all list `README.md` in `<files>`, but the file was already dirty with a one-line, not-this-plan change (`.planning/PERSONAL-DECISION-COCKPIT-UI-SPEC-2026-07-19.md` → `.planning/research/v1.4-decision-cockpit-ui/UI-SPEC.md` reference update) before this plan started, consistent with the other session's visible `.planning` reorg in `git status`.
- **Fix:** Made all of this plan's required README edits (status banner, "Phase 40 已完成" fix, checklist relabel, security-boundary section, PowerShell fences) directly in the working-tree file, on top of the pre-existing change — so the content is correct for anyone reading the file now — but never ran `git add`/`git commit` on it. The full pre-existing diff and the full list of this plan's own edits are both recorded in `36-VERIFICATION.md` §6-§7 for traceability.
- **Files affected:** `apps/personal_decision_cockpit/README.md` (edited, not committed).
- **Verification:** `grep -noE` for the plan's required verify regex (`npm run test|npm run build|/app|same-origin|project \+ low|not shipped|Phase 40|Wiki`) against the working-tree file confirms all patterns are present.
- **Committed in:** not committed by this plan (working tree only).

**2. [Explicit coordinator instruction] `.planning/ROADMAP.md`/`.planning/STATE.md` progress edits made but not committed**

- **Found during:** end of Task 3, closing out the phase's tracking state
- **Issue:** Both files carry a large amount of unrelated uncommitted content from another session's `.planning` reorganization (visible in the pre-task `git status --short`), and the coordinator's `CRITICAL_shared_tree_discipline` section explicitly instructs deferring these two files' progress edits to the orchestrator.
- **Fix:** Edited `.planning/ROADMAP.md`'s Phase 36 "Plans:" line/Progress-table row and `.planning/STATE.md`'s "Current Position" block to reflect Phase 36 closed / Phase 37 next, in the working tree only.
- **Files affected:** `.planning/ROADMAP.md`, `.planning/STATE.md` (edited, not committed).
- **Verification:** `git diff .planning/ROADMAP.md .planning/STATE.md` shows exactly this plan's intended two/three-line changes layered on top of the other session's pre-existing diff.
- **Committed in:** not committed by this plan (working tree only); orchestrator to fold in at phase close.

---

**Total deviations:** 2, both explicitly pre-briefed shared-tree special cases (not scope creep, not unplanned discoveries) — neither touched any file outside this plan's `files_modified` list or the two coordinator-flagged tracking files.

## Issues Encountered

- **Confirmed the coordinator's `prior_wave_context` caveat firsthand:** `git diff src/personal_knowledge/services/api_server.py` (uncommitted, from the other concurrently active session) does contain a `POST /ui/review/labels` write route not covered by the 36-01 `SESSION_WRITE_ROUTES` Origin gate, plus an `_err(str(exc))` usage — exactly as flagged. Documented in `36-VERIFICATION.md` §7 as an environment caveat; not touched, not fixed, not reverted (out of this plan's `files_modified` scope and not this executor's work to fix).
- No other issues — all three tasks' `<verify>` commands and the plan-level `<verification>` command passed on execution; `git status --short` was checked before every commit to confirm only this plan's intended file(s) were staged.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Phase 36 (CCK-01..04) is closed: transport security (36-01), safe Projection envelope (36-02), frontend DTO/vocabulary hardening (36-03), and this auditable baseline (36-04) are all committed with real evidence in `36-VERIFICATION.md`.
- `docs/runbooks/decision-cockpit.md` is now the canonical reproducible-ops entry point for anyone (human or agent) running the Cockpit locally; it should be extended (not replaced) by Phase 37-40 as their own page-level functionality is verified.
- **Outstanding, not this plan's job to close:** (a) `apps/personal_decision_cockpit/README.md`'s working-tree edits need a future commit once the other session's `.planning` reorg either lands or is reset — see `36-VERIFICATION.md` §6-§7 for the exact split; (b) `.planning/ROADMAP.md`/`.planning/STATE.md` progress edits are working-tree-only and need the orchestrator's phase-close tracking commit; (c) the uncommitted `/ui/review*` routes in `api_server.py` (999.5 scope) should get their own Origin-gate/safe-error coverage decision from whichever plan claims that scope — it is explicitly not retrofitted here; (d) `.planning/REQUIREMENTS.md` CCK-01/03/04 checkboxes should be ticked by the orchestrator using the evidence in `36-VERIFICATION.md` §2.
- Phase 37 (authority-aware-state-external-and-evidence) can proceed on top of this baseline; nothing in this plan widened network/write permissions or touched Phase 37-40's own page code.

---
*Phase: 36-secure-projection-and-cockpit-baseline*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `apps/personal_decision_cockpit/.gitignore` contains `coverage/`, `.vite/`, `*.tsbuildinfo` in addition to the pre-existing `node_modules/`, `dist/`, `*.local` — confirmed via read-back during editing.
- `docs/runbooks/decision-cockpit.md` exists on disk and its required-pattern grep (`npm run test|npm run build|/app|same-origin|project \+ low|not shipped|Phase 40|Wiki`) returns matches for every term — confirmed via `grep -noE` re-run.
- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md` frontmatter shows `status: verified`, `verification_mode: executed`, and all four `CCK-0x: pass` — confirmed via read-back.
- `git log --oneline abe4fe9^..70b2098` returns exactly 3 commits (`abe4fe9`, `9cdf7d7`, `70b2098`), each touching only the single file named in its corresponding task (verified via `git status --short` immediately before each commit and `git show --stat` per commit).
- Plan-level `<verification>` commands re-run in this session: `Get-Content 36-VERIFICATION.md` (real content, not the old placeholder), `git check-ignore -v apps/personal_decision_cockpit/node_modules apps/personal_decision_cockpit/dist` (both resolve to the Cockpit's own `.gitignore`), `git diff --check` (exit 0, no output) — all as recorded in `36-VERIFICATION.md` §3.
- `git status --short` after the final commit confirms `src/personal_knowledge/services/api_server.py`, the other session's `.planning/*` reorg files, and `apps/personal_decision_cockpit/README.md` remain exactly as found (this plan's README edits are present in the working tree per the documented deviation, but the file was never staged/committed by this plan).
