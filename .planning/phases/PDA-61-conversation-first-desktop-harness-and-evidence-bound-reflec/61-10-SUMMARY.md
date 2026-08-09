# 61-10 SUMMARY — Fixed deterministic proactive control/read/dismiss/undo routes

**Plan:** 61-10 (type=tdd, wave=7, autonomous=true, depends_on: 61-07, 61-09)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | Extended `conversation-turn.test.mjs` (+5) + `tests/integration/test_harness_proactive.py` (+9); RED run: Node 5 new fail / 13 existing green, Python 9 new fail / 11 existing green (commit `2b45010`) |
| 2 | auto (tdd, GREEN) | ✅ PASS | 3 implementation files; Node 18/18, pytest 31 passed, full regression green (commit `0288c3c`) |

## Verification

- `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` → **18 pass / 0 fail**
- `python -m pytest -q tests/integration/test_harness_proactive.py tests/contract/test_pi_domain_gateway.py` → **31 passed**
- Regression: reflection+projection 60 passed (61-07/09), conversation-delta-reflection 9/9 (61-06)
- `git diff --check` → clean; kernel-host providerMode line byte-preserved

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-PROACTIVE-02 | High | CLOSED | 18/18 node + 20 pytest; unknown paths 404, method mismatch 405, override/private/schedule/permission/value/canonical inputs all 400 with zero dispatch |
| T-61-PROACTIVE-03 | Critical | CLOSED | 31 passed; fingerprint tests prove canonical/active-pointer/watermark/schedule/permissions/values unchanged after five calls; no promote/rollback claims |

## Deliverables

- `src/personal_knowledge/services/pi_domain_gateway.py` — registered `proactive.state.get` (read), `proactive.controls.update` / `proactive.dismiss` / `proactive.dismiss.undo` (guarded_write); scope = global | `project:` format (format gate + provider `unknown_scope`), category exactly 同步/简报/反思候选; quiet-hours shape+format validation; new safe codes `category_unknown`/`proactive_request_invalid`/`declared_category`/`dismissal_not_found`/`unknown_scope`
- `apps/personal_intelligence_kernel/src/server.mjs` — four fixed `POST /v1/proactive/state|controls|dismiss|undo` routes; SAFE_ERROR_CODES updated; state envelope sanitized via 61-09 `sanitizeProjectionEnvelope` (watermark/active_pointer stripped)
- `apps/personal_intelligence_kernel/src/kernel-host.mjs` — `getProactiveState` / `updateProactiveControls` / `dismissProactive` / `undoProactiveDismissal`, method→provider dispatch exactly once, dispatch-before-validation of overrides

## Deviations / risks

- `harness_conversation_service.py` not modified — Task 1 contract notes provider branch calls the 61-07 deterministic adapter directly in the gateway; no change required.
- Routes are POST (deterministic inputs carried in body: events/controls/quiet_hours/now/manual_order); no new store added — state/controls semantics wrap the 61-07 adapter via gateway.
- No plan deviation; user-owned providerMode diff byte-preserved (line moved 793→925, content identical, pure additions).

## Self-Check: PASSED
