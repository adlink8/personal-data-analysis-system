---
phase: 36-secure-projection-and-cockpit-baseline
plan: 02
subsystem: api
tags: [cockpit, ui-projection, sqlite, safe-errors, authority-vocabulary]

# Dependency graph
requires:
  - phase: 36-secure-projection-and-cockpit-baseline
    provides: "36-01's `_SAFE_ERRORS`/`_safe_error` allowlisted public-error pattern in api_server.py, reused here as the design template for ui_projection.py's own catalog"
provides:
  - Allowlisted public limitation/error catalog (`_SAFE_FAILURE_CODES`/`_safe_failure_message`/`_safe_failure_error`) in ui_projection.py — no call site interpolates `str(exc)`/exception type into a public envelope field anymore
  - `_intelligence_data_or_raise` — distinguishes IntelligenceService's `run_missing` (real "no personal-state run committed yet" empty state) from genuine read failures, fixing two pre-existing environment-dependent test failures
  - Physical read-only regression: per-authority-DB table-count fingerprint unchanged across all 8 `/ui/*` operations, plus a same-mode-as-service (`mode=ro`+`query_only=ON`) connection write-rejection proof
  - `_KNOWN_CONFIRMATION_STATES` vocabulary gate in `_classify_stage` — an out-of-vocabulary `confirmation_state` can no longer be promoted to an actionable stage via a co-occurring `action_state`
affects: [37-authority-aware-state-and-evidence, 38-guarded-project-decision-workspace, 39-truthful-feedback-and-runtime, 40-browser-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Allowlisted public failure catalog owned by the module that raises it (`_SAFE_FAILURE_CODES` in ui_projection.py), mirroring 36-01's `_SAFE_ERRORS` in api_server.py — every public-facing failure string traces to a fixed literal code, never to `str(exc)`"
    - "Authority-reported typed error codes (e.g. `run_missing`) are data, not incidents — `_intelligence_data_or_raise` treats a known 'no committed run yet' code as a legitimate empty result rather than an exception to isolate as `error`"
    - "Vocabulary-gated stage classification: state-machine-adjacent fields (action_state) are only trusted to drive stage promotion when the co-occurring field they causally depend on (confirmation_state) is itself in the published vocabulary"

key-files:
  created: []
  modified:
    - src/personal_knowledge/services/ui_projection.py
    - tests/contract/test_ui_projection.py
    - tests/contract/test_ui_projection_state_external.py
    - tests/contract/test_ui_projection_decision.py
    - tests/contract/test_ui_projection_actions_proactive.py

key-decisions:
  - "run_missing is scoped narrowly: only IntelligenceService's own typed 'no committed personal_state run for the active snapshot' code is treated as empty. Other codes (snapshot_missing, snapshot_not_validated, checksum-mismatch codes, etc.) still raise and isolate as authority=error, since those indicate real integrity/config problems, not absence of data."
  - "The per-item inline `error` field (actions_recent single-item, calibration single-protocol) was changed from a `f\"{type}: {exc}\"` string to a `{code, message}` dict for consistency with the module's own allowlisted catalog shape; no test asserted its previous string shape, so this is a safe non-breaking narrowing."
  - "_classify_stage's action-state-driven branches (awaiting_outcome/closed-by-terminal-action/in_progress) are now gated behind `confirmation_state in _KNOWN_CONFIRMATION_STATES`; `has_outcome` remains an independent, stronger signal evaluated before the gate, so a real recorded outcome still wins even over a corrupted confirmation label."
  - "Physical read-only proof implemented as a before/after per-table row-count fingerprint (not raw file bytes/mtime, which would be sensitive to WAL/journal housekeeping) across all 8 /ui/* operations plus one real decision_workspace.get call, rather than mocking/spying every read-service call site."

patterns-established:
  - "Any new ui_projection.py failure branch should add a code to `_SAFE_FAILURE_CODES` and call `_safe_failure_message`/`_safe_failure_error`, not interpolate `str(exc)`/`type(exc).__name__` directly — mirrors the `_SAFE_ERRORS`/`_safe_error` convention established in api_server.py by 36-01."

requirements-completed: [CCK-01, CCK-03]

# Metrics
duration: 70min
completed: 2026-07-26
---

# Phase 36 Plan 02: Secure Projection and Cockpit Baseline — Safe Projection Envelope Summary

**Replaced every `str(exc)` interpolation in `ui_projection.py`'s public limitations/errors with an allowlisted safe-code catalog, fixed two pre-existing test failures by correctly mapping IntelligenceService's `run_missing` to an empty (not error) authority state, added physical-read-only fingerprint/write-rejection regressions, and closed a real vocabulary-lock gap where an unknown `confirmation_state` could be promoted to an actionable decision-queue stage via a co-occurring `action_state`.**

## Performance

- **Duration:** ~70 min
- **Started:** 2026-07-26T11:22:00Z
- **Completed:** 2026-07-26T12:32:00Z
- **Tasks:** 3
- **Files modified:** 5 (1 source, 4 test files)

## Accomplishments

- `ui_projection.py` now owns a fixed `_SAFE_FAILURE_CODES` catalog (`authority_read_failed`, `history_count_unavailable`, `item_assembly_failed`, `protocol_explain_failed`) with `_safe_failure_message`/`_safe_failure_error` helpers; `_collect`'s generic single-authority exception isolation, the `state.history` count fallback, `actions_recent.get`'s per-recommendation full-chain assembly failure, and `calibration_overview.get`'s per-protocol `explain` failure all route through it — none of them build their public limitation/error text from `str(exc)` or `type(exc).__name__` anymore.
- Diagnosed and fixed the two pre-existing failures handed off from 36-01 (`test_proactive_failure_isolated_as_partial`, `test_personal_state_changes_failure_isolated`): both failed for the same underlying reason — `IntelligenceService.invoke("state.current"/"changes.recent")` returns `ok=False, error.code="run_missing"` in this environment (no personal_state run has been committed against the currently active knowledge snapshot), and `ui_projection.py` was turning that legitimate "no data yet" signal into a raised `ValueError` that `_collect` then reported as authority `"error"`. Added `_intelligence_data_or_raise`, which recognizes `run_missing` as a genuine empty state and returns a zero-value section instead of raising; all other IntelligenceService error codes still raise and isolate as `error` exactly as before.
- Added 5 poisoned-exception regression tests (containing fake `C:\secret\x`, `sk-test-...`, `Bearer ...`, a provider-shaped JSON body, and `confirmation_token`/`HMAC` strings) across the `overview.get`, `personal_state.get`, `actions_recent.get`, and `calibration_overview.get` failure paths, asserting none of the injected fragments (nor the raw exception type name) appear anywhere in the serialized public envelope.
- Added a per-authority-DB table-row-count fingerprint test that invokes all 8 `/ui/*` operations (including a real `decision_workspace.get` when a recommendation exists) and proves zero rows changed anywhere, plus a same-mode (`mode=ro`+`query_only=ON`) connection test proving a write statement is rejected by SQLite itself — direct evidence for D-36-01/D-36-02's physical-read-only boundary, which previously had no dedicated regression.
- Closed a real (if practically hard-to-trigger) vocabulary gap in `_classify_stage`: previously, an item with an out-of-vocabulary `confirmation_state` (e.g. a corrupted/unexpected value) but a co-occurring `action_state` of `planned`/`started`/`completed`/`abandoned`/`not_taken` would still be routed to an actionable stage (`in_progress`/`awaiting_outcome`/`closed`) via the action-state branches, bypassing the confirmation-state check entirely. Added `_KNOWN_CONFIRMATION_STATES` as an explicit gate: those branches now only fire when `confirmation_state` is one of the five published values; anything else falls through to the conservative `needs_attention` catch-all (unless an independent recorded `outcome` already marks it `completed`). Verified both at the pure-function level and end-to-end through `decision_queue.get`/`proactive_summary.get` with synthetic monkeypatched authority responses.

## Task Commits

Each task was committed atomically:

1. **Task 1: 定义安全的 Projection public limitation/error 目录** - `ae80a01` (feat) — safe-failure catalog, `run_missing`→empty fix, poisoned-exception regressions
2. **Task 2: 保持 Projection v1 的物理只读与 authority 边界** - `302360d` (feat) — DB fingerprint + write-rejection regressions, reviewed all 8 operations for read-only-surface-only usage
3. **Task 3: 锁定状态与主动评分的 authority vocabulary** - `be8c931` (feat) — `_classify_stage` vocabulary gate fix + end-to-end vocabulary-lock regressions for decision_queue/proactive_summary

**Plan metadata:** this SUMMARY commit (docs) + STATE/ROADMAP progress update, to follow.

## Files Created/Modified

- `src/personal_knowledge/services/ui_projection.py` — safe-failure catalog + helpers, `_intelligence_data_or_raise`, `run_missing`-aware empty returns in `_personal_section`/`_personal_state_detail`/`_recent_changes_detail`, safe per-item `error` fields in `actions_recent`/`calibration_overview`, `_KNOWN_CONFIRMATION_STATES` gate in `_classify_stage`
- `tests/contract/test_ui_projection.py` — poisoned-exception leak regression (overview.get/proactive), DB fingerprint + write-rejection physical-read-only regressions
- `tests/contract/test_ui_projection_state_external.py` — poisoned-exception leak regression (personal_state.get/changes.recent)
- `tests/contract/test_ui_projection_decision.py` — pure-function + end-to-end unknown-confirmation-state vocabulary-lock regressions
- `tests/contract/test_ui_projection_actions_proactive.py` — poisoned-exception leak regressions (actions_recent single item, calibration single protocol), end-to-end `importance.final_score` vocabulary-lock regression

## Decisions Made

See `key-decisions` in frontmatter. Summarized: `run_missing` empty-mapping is scoped to exactly that one typed code (not a blanket "any IntelligenceService error is empty" change); the inline per-item `error` field shape was narrowed from a free-form exception string to a `{code, message}` dict since no test depended on its previous shape; `_classify_stage`'s action-driven branches are now vocabulary-gated while `has_outcome` remains an independent override; the read-only proof uses a logical per-table row-count fingerprint rather than raw file bytes to avoid false positives from SQLite journal/WAL housekeeping.

## Deviations from Plan

**1. [Rule: pre-existing failure in plan's own files_modified scope] Fixed two failing tests not explicitly named as a task**

- **Found during:** Baseline verification run before Task 1 (and confirmed again per the coordinator's prior_wave_context handoff)
- **Issue:** `test_proactive_failure_isolated_as_partial` (test_ui_projection.py) and `test_personal_state_changes_failure_isolated` (test_ui_projection_state_external.py) both failed on a clean checkout — not because of anything this plan changed, but because `IntelligenceService.invoke` naturally returns `run_missing` in this environment (no personal_state run committed against the current active snapshot) and `ui_projection.py` mapped that to authority `"error"` instead of `"empty"`.
- **Fix:** Added `_intelligence_data_or_raise` (Task 1) so `run_missing` specifically degrades to a zero-value empty section; all other IntelligenceService error codes are unaffected and still raise/isolate as `error`.
- **Files modified:** `src/personal_knowledge/services/ui_projection.py` (no test file changes were needed to fix these two specific tests — they simply started passing).
- **Verification:** Both tests pass; full four-file + transport-security suite (74 tests) passes with 0 failures.
- **Committed in:** `ae80a01` (Task 1 commit)

**2. [Scope-appropriate hardening beyond literal task wording] Closed a real vocabulary-promotion gap in `_classify_stage`, not just verified existing behavior**

- **Found during:** Task 3, while writing the "prove unknown confirmation is never promoted" acceptance-criteria test
- **Issue:** The plan's Task 3 acceptance criteria ("未知 confirmation 不会被提升为可执行") was already satisfied by existing tests *at the pure-function level for the specific inputs those tests used*, but constructing a new case (unknown `confirmation_state` + actionable `action_state`) exposed that the action-state branches in `_classify_stage` ran before any check on `confirmation_state`'s vocabulary membership, so such an item — while not reachable through the real state machine (action can't start before acceptance) — would silently be classified as `in_progress`/`awaiting_outcome`/`closed` if it ever occurred (e.g. from data drift or an authority bug).
- **Fix:** Added `_KNOWN_CONFIRMATION_STATES` gate before the action-driven branches; `has_outcome` remains evaluated first as an independent signal.
- **Files modified:** `src/personal_knowledge/services/ui_projection.py`, `tests/contract/test_ui_projection_decision.py`, `tests/contract/test_ui_projection_actions_proactive.py`
- **Verification:** All pre-existing `_classify_stage`/`decision_queue`/`proactive_summary` tests still pass unchanged; new pure-function and end-to-end tests cover the previously-unguarded combination.
- **Committed in:** `be8c931` (Task 3 commit)

---

**Total deviations:** 2 (1 pre-existing-failure fix required by the coordinator's explicit handoff instruction, 1 defense-in-depth fix discovered while writing the plan's own acceptance-criteria test). Both are strictly within `ui_projection.py`'s files_modified scope and directly serve D-36-05/D-36-06; no scope creep into unrelated subsystems.

## Issues Encountered

- **Git index contamination (self-corrected):** the working tree had a large number of unrelated `.planning/*` doc renames/edits already staged in the index before this plan started (left over from other GSD workflow activity in this shared working tree, unrelated to Phase 36). The first Task 1 commit accidentally swept those in via a bare `git commit -m` after `git add`ing only the intended files (the pre-existing staged content was still in the index). Caught immediately via `git show --stat HEAD`; fixed with `git reset --soft HEAD~1` (index untouched) → `git reset HEAD -- .` (fully unstage) → re-`git add` only the 4 intended files → verified with `git diff --cached --stat` → recommitted. All three actual task commits (`ae80a01`, `302360d`, `be8c931`) contain only files within this plan's `files_modified` scope; the unrelated `.planning/*` changes and the untracked `tools/migrations/abandon_orphan_runs.py` were left exactly as found, untouched.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `ui_projection.py`'s public failure surface is now fully allowlisted (D-36-06 closed for this file); any future new failure branch should extend `_SAFE_FAILURE_CODES` rather than reintroducing `str(exc)`.
- Physical read-only boundary (D-36-01/D-36-02) now has direct regression coverage (fingerprint + write-rejection), not just incidental behavior.
- `confirmation_state`/`importance.final_score` vocabulary handling (D-36-05) is locked both at the unit and end-to-end level; Phase 37+ pages building on `decision_queue.get`/`proactive_summary.get` can rely on this without re-deriving vocabulary logic client-side.
- No known blockers for Phase 37 (authority-aware state/external/evidence). The four ui_projection contract files plus `test_cockpit_transport_security.py` all pass (74/74) as the combined regression baseline handed forward.

---
*Phase: 36-secure-projection-and-cockpit-baseline*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `src/personal_knowledge/services/ui_projection.py` contains `_SAFE_FAILURE_CODES`, `_intelligence_data_or_raise`, `_KNOWN_CONFIRMATION_STATES` — confirmed via read-back during editing.
- `git log --oneline e3994d8..HEAD` returns exactly 3 commits: `ae80a01`, `302360d`, `be8c931`, each touching only files within this plan's `files_modified` scope (verified via `git show --stat` per commit).
- Plan-level `<verification>` command re-run: `python -m pytest tests/contract/test_ui_projection.py tests/contract/test_ui_projection_state_external.py tests/contract/test_ui_projection_decision.py tests/contract/test_ui_projection_actions_proactive.py -q` → 56 passed, 0 failed.
- Extended regression (four files + `test_cockpit_transport_security.py`, the 36-01 handoff regression): 74 passed, 0 failed.
- `test_proactive_failure_isolated_as_partial` and `test_personal_state_changes_failure_isolated` (the two pre-existing failures named in the coordinator's handoff) both pass.
- `git status` confirms no unintended files were committed; the pre-existing unrelated `.planning/*` staged/modified content and `tools/migrations/abandon_orphan_runs.py` remain exactly as found (untouched, uncommitted).
