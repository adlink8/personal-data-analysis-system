# 61-03 SUMMARY — Real Pi lease-scoped conversation turn

**Plan:** 61-03 (type=tdd, wave=1, autonomous=true)
**Status:** COMPLETED (2026-08-10)

## Tasks

| Task | Type | Result | Evidence |
|------|------|--------|----------|
| 1 | auto (tdd, RED) | ✅ PASS | `test/conversation-turn.test.mjs` created (555 LOC, 6 tests, ~85 assertions, 6 sentinel leak checkpoints); RED run: 6 tests, 1 pass / 5 fail matching acceptance criteria (commit `651a02d`) |
| 2 | auto (tdd, GREEN) | ✅ PASS | Implementation (2 new + 3 modified files); focused test 6/6 green; full Kernel suite 59/62 pass, 3 pre-existing failures (commit `9d6baac`) |

## Verification

- `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` → **6 pass / 0 fail** (GREEN), provider-mode fingerprint `de3b29b0178cfec6e07d5d6b4a3ad4ab1bed61906bcaca59f2135e5809db5ca7`
- `npm --prefix apps/personal_intelligence_kernel test` → 62 tests, 59 pass, 3 fail (all pre-existing, reproduced at HEAD `651a02d` in temp worktree)
- `git diff --check` → 0

## Security closure (Threat Model)

| Threat | Severity | Status | Evidence |
|--------|----------|--------|----------|
| T-61-AGENT-01 | Critical | CLOSED | unknown/cross-profile lookup, checksum_drift, not_read_only, at_most_one_* all fail closed; ordinary Conversation never sees Reflection/Operator mutation authority |
| T-61-LOOP-01 | High | CLOSED | prompt(source:"rpc")→waitForIdle→dispose asserted; conversation path never calls providerAdapter.generate()/SkillEngine.run() as second outer loop |
| T-61-RECOVER-01 | High | CLOSED | cancelled/outcome_unknown are non-success envelopes; reconcile via existing reconcileTask |
| T-61-TRACE-01 | High | CLOSED | sentinel leak tests pass; no body/prompt/completion/credential/secret in Task/Session/Event/Candidate projections |

## Deliverables

- `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` (new)
- `apps/personal_intelligence_kernel/src/conversation/turn-service.mjs` (new) — `runConversationTurn`
- `apps/personal_intelligence_kernel/src/runtime/conversation-session.mjs` (new) — `conversationSessionFactory`
- `apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs` — Conversation/Reflection/Operator profiles (`PROFILE_DEFINITIONS`, `resolveProfile`, `profileToolNames`, `isProfileOperation`, `deriveConversationLease`), deny-by-default
- `apps/personal_intelligence_kernel/src/kernel-host.mjs` — narrow dispatch for `/v1/conversations/turn|cancel|resume|reconcile`
- `apps/personal_intelligence_kernel/src/server.mjs` — 4 fixed routes, typed input, safe no-store envelopes

## User-owned diff preservation

- `kernel-host.mjs` providerMode diff (`mode: options.providerMode ?? process.env.PI_KERNEL_PROVIDER_MODE` with `?? "replay"` removed) recorded before edit and verified byte-for-byte identical after edit; regression test #6 enforces it stays undefined unless explicitly supplied.

## Deviations / risks

- 3 pre-existing Kernel suite failures (not introduced by this plan): capability-registry expects 44 ops but has 45 (due to 61-04 `evidence.sqlite_query` registration — deferred to phase close-out); event-journal host_bind_failed (port 8790 occupied by external PID 99180 — environment); skill-warehouse-e2e (needs Python domain test server unavailable — environment).
- Default `conversationSessionFactory` uses provider-free runtime + synthetic model (consistent with containment posture); real inference requires explicit factory injection or later wiring. Live/paid smoke remains outside acceptance and requires separate human approval.
- No plan deviation; Task 1 contract naming implemented exactly as tested.

## Self-Check: PASSED
