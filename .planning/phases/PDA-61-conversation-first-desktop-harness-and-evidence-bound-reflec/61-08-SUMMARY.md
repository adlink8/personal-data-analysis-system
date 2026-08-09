# 61-08 SUMMARY — Guarded Candidate review fixed route

**Plan:** 61-08 (type=tdd, wave=5, autonomous=true, depends_on: 61-03, 61-07)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | New `tests/contract/test_harness_candidate_review.py` (+15) + extended `test_pi_domain_gateway.py` (+3) + `conversation-turn.test.mjs` (+3); RED run 18/8 failed + 3 failed / 7 passed, existing tests kept green (commit `872fe2a`; first dispatch died to model infra error, clean re-dispatch succeeded) |
| 2 | auto (tdd, GREEN) | ✅ PASS | `harness_candidate_review.py` (reviewed leftover + 1 contract fix) + Gateway + Kernel route; 26/26 contract + 10/10 node (commit `11d0866`; first dispatch partially completed then died to model infra error, second dispatch reviewed leftover and finished) |

## Verification

- `python -m pytest -q tests/contract/test_harness_candidate_review.py tests/contract/test_pi_domain_gateway.py` → **26 passed**
- `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` → **10/10 pass**
- Regression: harness_reflection+proactive 30 passed (61-07), conversation-delta-reflection 9/9 (61-06)
- `git diff --check` → clean

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-REVIEW-01 | Critical | CLOSED | 26/26; all review negatives pass (version/confirmation/checksum/binding/idempotency/append-only gates) |
| T-61-REVIEW-02 | Critical | CLOSED | 10/10 node; fixed route only (GET→405, alternate paths→404, private/override fields rejected before dispatch) |
| T-61-CANON-01 | Critical | CLOSED | 15/15; fingerprints prove no promotion/rollback/watermark/active-pointer mutation |
| T-61-LEAK-04 | High | CLOSED | sentinel tests pass; receipts/ledger metadata-only |

## Deliverables

- `src/personal_knowledge/application/conversation/harness_candidate_review.py` (new) — `HarnessCandidateReviewAdapter`; actions accept/edit/ignore/undo; version semantics start at 1, +1 per successful review; four-value conflict_disposition (keep_existing/replace_existing/coexist_by_context/defer_judgment) with Chinese labels + consequence text; batch rejection; append-only feedback/receipts; safe no-store states reviewed|duplicate|confirmation_required|stale_version|conflict_disposition_required|rejected|outcome_unknown
- `src/personal_knowledge/services/pi_domain_gateway.py` — registered `candidate.review` (guarded_write); capability/binding/idempotency errors; undeclared_input for 8 forbidden field classes
- `apps/personal_intelligence_kernel/src/server.mjs` + `kernel-host.mjs` — fixed `POST /v1/candidates/review` route dispatching only to `candidate.review` with field-level validation before dispatch

## Deviations / risks

- **feedback_history semantics (Rule 2, contract-driven)**: Task 1 contract requires `feedback_history() == ()` after a successful accept; legacy adapter appended all four action types. Fixed: `feedback_history` exposes only reversible calibration gestures (ignore/undo — the entries undo can reference), while the metadata-only ledger still records all four action rows to preserve idempotency dedup.
- **`harness_conversation_service.py` not modified** (no test/contract required it; review does not flow through the 61-05 read-only canonical navigation service).
- **Bridge allowlist risk (recorded)**: production `createProjectDomainBridge` operations allowlist comes from the capability registry and does not include `candidate.review`; real desktop wiring (61-11/61-12) must add it to the bridge allowlist. `domain-bridge.mjs` is outside this plan's files_modified.
- **Gateway default adapter** has no candidates → fails closed `candidate_unknown`; successful review paths must inject a review_adapter with candidates (consistent with reflection pattern).
- No plan deviation otherwise; user-owned providerMode diff byte-preserved (fingerprint de3b29b0…).

## Self-Check: PASSED
