# 61-09 SUMMARY — Versioned projection and governed next-turn injection

**Plan:** 61-09 (type=tdd, wave=6, autonomous=true, depends_on: 61-03, 61-07, 61-08)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | New `tests/integration/test_harness_projection.py` + extended `tests/unit/test_personal_state_projection.py` + `conversation-turn.test.mjs` (+3); RED run: Python 10 failed/12 passed, Node 3 failed/10 passed, existing tests kept green (commit `96bf108`) |
| 2 | auto (tdd, GREEN) | ✅ PASS | 6 implementation files; Python 22 passed, Node 13/13 green, full regression green (commit `a2b4a2a`). Task 2 dispatch died to model infra error after completing all edits; coordinator ran the full verification suite on the leftover work and committed it |

## Verification (run by coordinator on leftover GREEN work)

- `python -m pytest -q tests/integration/test_harness_projection.py tests/unit/test_personal_state_projection.py` → **22 passed**
- `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` → **13 pass / 0 fail**
- Regression: harness_reflection+proactive 30 passed (61-07), candidate_review+pi_domain_gateway 26 passed (61-08), conversation-delta-reflection 9/9 (61-06)
- `git diff --check` → clean; kernel-host providerMode line preserved (no `?? "replay"`)

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-PROJ-01 | High | CLOSED | projection/injection negatives pass (draft/ignored/stale/foreign excluded; provenance/freshness/conflict/version/supersession retained) |
| T-61-PROJ-02 | Critical | CLOSED | fixed GET route + provider; no endpoint override; only approved compatible context reaches prompt |
| T-61-CANON-02 | Critical | CLOSED | authority fingerprints stable; no promotion/rollback/watermark/active-pointer access |

## Deliverables

- `src/personal_knowledge/intelligence/state_projection.py` — versioned evidence-bound projection surface through existing normalization path; inference-only (fact/occurrence → provenance_rule_violation); draft/ignored lifecycle rejected; exposes version/supersession/freshness/limitations
- `src/personal_knowledge/services/pi_domain_gateway.py` — registered `personal.model_projection.get` (kind=read; allowed {scope, binding, task_id, idempotency_key}; capability via loopback header); derives only from confirmed accepted review state via review_adapter/review_db binding
- `apps/personal_intelligence_kernel/src/server.mjs` + `kernel-host.mjs` — fixed `GET /v1/personal/model-projection` route + `host.getModelProjection`, dispatch-before-validation of overrides
- `apps/personal_intelligence_kernel/src/conversation/turn-service.mjs` — pre-prompt context builder calls provider with turn scope/binding (new scope/binding/modelProjectionProvider options), injects only compatible current derived context via `options.projection_context`, receipt carries version/freshness/limitations, invalid results omitted with limitation

## Deviations / risks

- `tests/unit/test_personal_state_projection.py` existed from an earlier plan; extended rather than created (per "new" intent) — Modified not Add in commit.
- Task 2 executor completed all edits then died to model infra error (empty turn) before reporting/committing; coordinator verified the leftover work passed the full suite (including plan verification commands and security gates) and committed it. No test changes were made by the coordinator.
- No plan deviation; user-owned providerMode diff byte-preserved.

## Self-Check: PASSED
