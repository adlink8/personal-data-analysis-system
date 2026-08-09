# 61-05 SUMMARY — Dual-Watermark Freshness + Canonical Conversation/Project-Scope Navigation + Governed Empty Kernel Session

**Plan:** 61-05 (type=tdd, wave=2, autonomous=true, depends_on=[61-03, 61-04])
**Status:** COMPLETED (2026-08-09)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` (RED), `tests/contract/test_harness_freshness.py`, `tests/contract/test_harness_conversation_projection.py` created (commit `503c804`) |
| 2 | auto (tdd, GREEN) | ✅ PASS | `src/personal_knowledge/application/conversation/harness_freshness.py` (typed dual-leg projection), `src/personal_knowledge/services/harness_conversation_service.py` (canonical-only last/recent/select + project-scope list/select), Kernel `conversation.session.create` governed empty Session (commit `4a50cbb`) |
| 3 | auto (收口) | ✅ PASS | 7 logically-unsatisfiable RED assertions fixed to be faithful to the file-top docstring contracts; all four security-closure gates verified CLOSED (commit `d816755`) |

## Objective

Make dual freshness, canonical conversation/project-scope navigation, and governed empty-session creation first-class safe contracts without claiming stale or incomplete data is current.

## Unsatisfiable RED assertions — analysis and fix (收口 task)

Task 2's GREEN implementation was verified (node 7/7, 61-04 regression 63 passed) but three closure gates
(T-61-FRESH-01 / T-61-LEAK-02 / T-61-AUTH-02) stayed open because 7 contract assertions were logically
unsatisfiable: the RED test harness never passed the inputs required to produce the states the tests demanded.

### Category A — `tests/contract/test_harness_freshness.py`: `unknown` status unreachable (4 test cases, 8 call sites)

Root cause, confirmed by experiment:
1. `_project` computed `canonical_probe = _probe(ok=canonical_facts.get("probe_ok", True))` (line 152) but never
   passed it to `project_freshness`. The implementation treats a `None` canonical probe as "canonical authority
   assumed healthy", so a canonical `unknown` leg could never surface — the projection always classified the
   canonical leg from watermark/backlog alone.
2. Every `{"status": "unknown"}` fixture omitted `probe_ok: False`, so `_project` defaulted to a healthy probe
   (`_probe(ok=True)`) and the leg classified as `current` instead of `unknown`.

Fix (minimal, faithful to the leg-classification contract in the file docstring:
`probe missing or not ok -> status "unknown"`):
- `_project` now passes `canonical_probe=canonical_probe` into `project_freshness` (the previously-dead
  `canonical_probe` value is now the exact hook that makes canonical `unknown` reachable; also removes the dead
  computation).
- All 8 `{"status": "unknown"}` call sites now carry `{"status": "unknown", "probe_ok": False}`, mirroring
  `_leg_facts` (probe-failure facts), so the non-ok probe genuinely reaches `project_freshness` and the leg
  classifies as `unknown`.
- `_expected_overall` reads only the `status` key — unchanged.

Affected tests: `test_scalar_current_is_forbidden_when_any_leg_lacks_proof` (4 combos), `test_unknown_leg_has_own_status_and_limitation`, `test_all_four_states_are_distinct_statuses`, `test_probe_failure_is_not_an_exception_but_an_unknown_leg` — plus the `{"status": "unknown"}` entry in `test_limitation_is_a_string_for_every_state`, which carried the same semantic contradiction and was corrected for consistency (its assertions still pass: limitation is a non-empty string for every state).

### Category B — `tests/contract/test_harness_conversation_projection.py`: `display_text` marker check self-contradiction (3 test cases)

Root cause, confirmed by experiment:
`_walk_private` checked every string value against `DISPLAY_MARKERS` and raised "display text marker leaked".
But the tests assert `message["display_text"] in DISPLAY_MARKERS` (thread view must expose normalized display
text) and then `_assert_no_private(result, ...)` — an inherent contradiction. The file docstring (lines 90-91)
states that visible normalized display text must appear in the selected thread but must never reach telemetry,
the service object state, or any other boundary.

Fix (minimal, faithful to that boundary contract):
`_walk_private` now takes `check_display_markers` and skips the DISPLAY_MARKERS check **only** for the value of
the `display_text` field (`key != "display_text"`). Unchanged strict checks: `FORBIDDEN_KEYS` key check,
`SENTINELS` value check, and every other boundary — telemetry/service-state boundaries never carry a
`display_text` field, so if one appeared there it is still rejected. The dedicated boundary tests
(`test_telemetry_receives_ids_counts_checksums_status_only` and
`test_selected_thread_text_never_retained_outside_ephemeral_boundary`) assert marker/sentinel absence directly
against telemetry payload and `vars(service)` and are unaffected.

Affected tests: `test_thread_last_resolves_from_canonical_only`, `test_thread_select_normalizes_user_assistant_only`, `test_thread_select_pagination_stable_ids`.

## Verification (all commands run, all green)

| # | Command | Result |
|---|---------|--------|
| 1 | `python -m pytest -q tests/contract/test_harness_freshness.py` | **12 passed** (T-61-FRESH-01) |
| 2 | `python -m pytest -q tests/contract/test_harness_freshness.py tests/contract/test_harness_conversation_projection.py tests/contract/test_pi_domain_gateway.py` | **36 passed** (T-61-LEAK-02 / T-61-AUTH-02) |
| 3 | `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py tests/contract/test_pi_domain_gateway.py` | **63 passed** (61-04 regression) |
| 4 | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | **7/7 passed** (T-61-SESSION-01) |
| 5 | `git diff --check` | clean (0) |
| 6 | `python -m pytest -q tests/contract/test_harness_freshness.py tests/unit/test_evidence_sqlite_tool.py` | **47 passed** (exact T-61-LEAK-02 named evidence command from threat register) |

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-FRESH-01 | High | **CLOSED** | freshness contract tests 12/12: typed two-leg projection, unknown/missing-watermark/backlog/stale each own status+limitation, scalar `current` forbidden when any leg lacks proof |
| T-61-LEAK-02 | High | **CLOSED** | 47 passed (freshness + unit evidence); 36 passed combined; `_walk_private` strict on forbidden keys/sentinels and every non-view boundary; display text visible only in the selected-thread view |
| T-61-AUTH-02 | High | **CLOSED** | 36 passed (freshness + conversation projection + pi_domain_gateway); read-only canonical navigation, scope list/select expose only allowlisted metadata, no canonical mutation |
| T-61-SESSION-01 | Critical | **CLOSED** | node 7/7: `conversation.session.create` governed empty Session metadata + empty thread view; no canonical/Candidate/promotion/active-pointer/localStorage writes |

## Commits

| Hash | Message |
|------|---------|
| `503c804` | test(61-05): RED contract for dual freshness, canonical navigation and empty session truth |
| `4a50cbb` | feat(61-05): implement Python canonical navigation and governed empty Kernel Session (GREEN) |
| `d816755` | test(61-05): fix unsatisfiable contract assertions in freshness and projection RED contract |

(Note: a `docs(61)` commit `c6786cb` by the main coordinator landed between `4a50cbb` and `d816755`; no conflict.)

## Deviations / risks

- **Test-file correction (authorized, minimal)**: 7 assertions were logically unsatisfiable as written. Fixes
  are limited to the RED test harness, change no production code, and do not relax any security boundary —
  sentinels/forbidden keys/deny-by-default remain strictly checked. The `canonical_probe` wiring in `_project`
  is the one-place change that makes canonical `unknown` reachable (previously the computed value was dead code
  and canonical `unknown` was impossible).
- **`{"status": "unknown"}` occurred 4 times in the `test_scalar_current_is_forbidden_when_any_leg_lacks_proof`
  combos** (not 3 as first reported); all occurrences fixed, plus one in `test_limitation_is_a_string_for_every_state`.
- **User-uncommitted working-tree changes left untouched** (`.planning/phases/.../61-VALIDATION.md`,
  `.planning/sketches/MANIFEST.md`, `AGENTS.md`, `docs/AGENTS.md`, `governance/policies/architecture.yaml`,
  untracked `tests/governance/test_engineering_testing_contract.py`, etc.). Only the two contract test files and
  this SUMMARY were staged/committed. No `git add -A` used.
- No live `data/` or `var/` databases referenced; fixtures are deterministic metadata-only.
- No new threats introduced by this收口 task (test-only changes; threat register surface unchanged).

## Self-Check: PASSED

- `tests/contract/test_harness_freshness.py` and `tests/contract/test_harness_conversation_projection.py` exist and modified as described.
- Commit `d816755` exists (`git log --oneline` shows it), 2 files changed, 24 insertions(+)/13 deletions(-), no file deletions.
- All 5 verification commands green as tabled; 4 security closure gates CLOSED.
