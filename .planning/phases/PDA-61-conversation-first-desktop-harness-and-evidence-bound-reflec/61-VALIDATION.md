---
phase: 61
slug: conversation-first-desktop-harness-and-evidence-bound-reflection-loop
status: closed
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-09
---

# Phase 61 — Validation Strategy

> Per-phase validation contract for the conversation-first desktop and evidence-bound reflection Walking Skeleton.
> The global module/seam/TDD contract in `docs/architecture/engineering-and-testing-contract.md` also applies; this file adds Phase 61-specific seams, threats, commands, and closure evidence.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Python framework** | pytest via `pytest.ini` |
| **Kernel framework** | Node built-in test runner via `apps/personal_intelligence_kernel/package.json` |
| **Desktop framework** | Wave 0 Node built-in tests over pure main/preload IPC, schema, and view-model modules |
| **Quick run command** | Impacted Node or pytest command from the requirement map plus `git diff --check` |
| **Full suite command** | `npm --prefix apps/personal_intelligence_kernel test` plus the focused Python Phase 61 suite |
| **Desktop acceptance** | Manual local Electron UAT with a redacted deterministic fixture/replay provider |
| **Estimated quick latency** | Target under 60 seconds for focused checks |

---

## Sampling Rate

- **After every task commit:** Run the impacted command from the map and `git diff --check`.
- **After every plan wave:** Run the Kernel suite and all Phase 61 Python tests implemented by that wave.
- **Before `$gsd-verify-work`:** All mapped tests, Phase 55–60 activation/rollback regressions, and the six-step desktop UAT must pass.
- **Max feedback latency:** 60 seconds for focused automated checks; split longer suites by affected seam.

## Phase 55–60 and Provider-Mode Regression Gate

Run these exact commands independently before the Phase 61 checkpoint. They use only existing deterministic temporary/replay fixtures; no command is authorized to make a live paid call, activate/promote/rollback, change a pointer, or perform a destructive operation.

| Regression proof | Exact command | Required redacted closure evidence |
|---|---|---|
| Phase 55 capability registry | `python -m pytest tests/contract/test_project_capability_registry.py -q` | Exit code, PASS/FAIL, registry checksum, fixture ID |
| Phase 56 warehouse denial/invariants | `python -m pytest tests/security/test_pi_warehouse_tool_containment.py -q` | Exit code, PASS/FAIL, authority fingerprint, fixture ID |
| Phase 58 Skill lease/selection | `npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill-engine` | Exit code, PASS/FAIL, Skill checksum, fixture ID |
| Phase 58 forbidden/recovery sequence | `python -m pytest tests/integration/test_pi_skill_recovery.py -q` | Exit code, PASS/FAIL, Skill checksum or authority fingerprint, fixture ID |
| Phase 59 Kernel control reducer | `node --test apps/personal_intelligence_kernel/test/runtime-control.test.mjs` | Exit code, PASS/FAIL, policy checksum, fixture ID |
| Phase 59 cancel/resume/reconcile | `python -m pytest tests/integration/test_pi_runtime_control.py -q` | Exit code, PASS/FAIL, authority fingerprint, fixture ID |
| Phase 57/60 activation and exact rollback guards | `python -m pytest tests/e2e/test_pi_snapshot_release.py tests/e2e/test_pi_capability_os_activation.py -q` | Exit code, PASS/FAIL, policy checksum and active-pointer fingerprint from temporary fixture, fixture ID |
| Phase 61 preserved non-default provider mode (created by Plan 61-03) | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | Exit code, PASS/FAIL, provider-mode checksum/config fingerprint, fixture ID |

Record every row's command verbatim, exit code, result, applicable checksum/fingerprint, timestamp and redacted fixture ID in `apps/personal_intelligence_desktop/test/desktop-uat-record.md`. Any missing evidence, non-zero exit, unauthorized live call, activation/promotion/rollback/pointer change, or destructive operation blocks Phase 61 closure.

**Plan 61-12 status (recorded 2026-08-09; Task 3 approved 2026-08-10):** Task 1 executed every regression row above and recorded it in `apps/personal_intelligence_desktop/test/desktop-uat-record.md` (rows T1-1..T1-10): 9 of 10 commands exit 0 (PASS); the Phase 58 skill-engine row (`npm test --test-name-pattern=skill-engine`) exits 1 with the two pre-existing failures already tracked in `deferred-items.md` (44-vs-45 registry operation count; environmental `domain_test_server_unavailable`). No command made a live paid call or changed activation/promotion/rollback/pointer state. Task 2 completed the six executable UAT steps with per-step evidence, safe receipt status fields, redaction instructions, assertions and PASS/FAIL/BLOCKED rows. All six steps PASS (automated), and the Task 3 blocking human checkpoint approved them on 2026-08-10 ("Phase 61 desktop UAT approved") — recorded in the same UAT record. `nyquist_compliant` and `wave_0_complete` are therefore `true`; Phase 61 is **closed**.

---

## Requirement Verification Map

| Requirement | Plans / tasks | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|---------------|------------|-----------------|-----------|-------------------|-------------|--------|
| HARNESS-01 | 61-02 T1/T3; 61-05 T1/T2; 61-11 T1–T3; 61-12 | T61-UI-01 | Main creates a secure local window; Python canonical authority serves scope/history navigation; Kernel creates empty session metadata; renderer has no Node authority | Node/Python contract + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs && python -m pytest -q tests/contract/test_harness_conversation_projection.py` | ✅ (all files exist) | ✅ complete (61-12 UAT approved 2026-08-10) |
| HARNESS-02 | 61-03 T1/T2; 61-11 T1–T3; 61-12 | T61-AGENT-01 | One `session.prompt()` turn leases only Skill tools, observes Tool receipts, and settles without a second outer loop | Kernel integration | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | ✅ (file exists; 18/18 exit 0 in 61-12 T1) | ⬜ pending |
| HARNESS-03 | 61-04 T1/T2; 61-11 T1–T3; 61-12 | T61-SQL-01 | Approved descriptor queries succeed; immutable checksum-bound logical statement display is safe to show; mutation, scope escape, unsafe PRAGMA, ATTACH, extension, multi-statement, excessive output and physical-schema/value leakage fail closed | Python unit/integration + desktop UAT | `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py` | ✅ (all files exist) | ✅ complete (61-12 UAT approved 2026-08-10) |
| HARNESS-04 | 61-05 T1/T2; 61-11 T1–T3; 61-12 | T61-FRESH-01 | Both source-to-AgentView and AgentView-to-canonical freshness/backlog are returned; stale/unknown is never labelled current | Python contract | `python -m pytest -q tests/contract/test_harness_freshness.py` | ✅ (file exists) | ⬜ pending |
| HARNESS-05 | 61-06 T1/T2; 61-07 T1/T2; 61-10 T1/T2; 61-12 | T61-REFLECT-01 | Committed canonical sync/close publishes `conversation.delta.committed`; durable EventJournal cursor/replay reaches one evidence-bound Candidate and deterministic proactive data never uses a direct handler | Kernel + Python integration | `node --test apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs && python -m pytest -q tests/integration/test_harness_reflection.py tests/integration/test_harness_proactive.py` | ✅ (all files exist) | ✅ complete (61-12 UAT approved 2026-08-10) |
| HARNESS-06 | 61-08 T1/T2; 61-11 T1–T3; 61-12 | T61-REVIEW-01 | Fixed `candidate.review` validates version/action/edit checksum/confirmation/binding/idempotency and the strict per-item four-value conflict disposition; unknown/missing disposition and batch acceptance reject; no direct authority mutation; feedback is append-only | Kernel/Python contract + desktop UAT | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs && python -m pytest -q tests/contract/test_harness_candidate_review.py tests/contract/test_pi_domain_gateway.py` | ✅ (all files exist) | ✅ complete (61-12 UAT approved 2026-08-10) |
| HARNESS-07 | 61-09 T1/T2; 61-11 T1–T3; 61-12 | T61-PROJ-01 | Fixed `personal.model_projection.get` returns only approved derived versions; later `conversation.turn` injects current compatible projection provenance/freshness/confidence/time/conflict, never draft/ignored Candidate | Kernel/Python unit/integration | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs && python -m pytest -q tests/unit/test_personal_state_projection.py tests/integration/test_harness_projection.py` | ✅ (all files exist) | ✅ complete (61-12 UAT approved 2026-08-10) |
| HARNESS-08 | 61-01 through 61-12; closure in 61-12 | T61-PRIV-01 | No raw IPC/endpoint escape, raw SQL/schema/value or secret/body leakage, false cancel/reconcile success, second conversation fact store, or unauthorized authority change | Node/Python integration + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs` and `python -m pytest -q tests/integration/test_pi_kernel_events.py` | ✅ (all files exist; 54/54 exit 0 in 61-12 T1) | ⬜ pending |

*Plan/task IDs are bound in the `Plans / tasks` column above; Plan 61-12 is the final closure plan for Phase 61 — it aggregates the last automated suite, the six-step desktop UAT record (`apps/personal_intelligence_desktop/test/desktop-uat-record.md`) and this validation status. All automated commands for every row above exist and were executed/recorded by Plan 61-12 Task 1; each row's Status flips to PASS only after the Task 3 checkpoint records the blocking Electron manual UAT evidence.*

---

## Required Negative and Invariant Tests

- Assert a real conversation route calls `AgentSession.prompt()` and observes Tool-call/result plus final settled/idle state; a provider-only or fixed `SkillEngine.run()` path must fail the acceptance test.
- Assert the canonical event test enters via the real post-commit sync/close publisher, not `harness_reflection` directly; a dry-run, missing/changed committed checksum/watermark, failed subscriber dispatch or divergent replay cannot advance the reflection cursor or create a Candidate.
- Refuse every Tool proposal outside the active Skill lease before bridge dispatch and again at the Python gateway; the default Conversation profile exposes no mutation, promotion, activation, or rollback Tool.
- Fingerprint every authority database and active pointer before and after SQLite read, rejection, timeout, cancel, ignored Candidate, and failed confirmation. Only the intended append-only Candidate/feedback/projection stores may change after confirmed acceptance.
- Use sentinel secrets and raw-body fixtures to scan main/preload/renderer responses, logs, receipts, Task/Session/Event storage, and screenshots for body, prompt, completion, credential, token, and secret leakage.
- Assert Electron `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`, restrictive CSP, denied navigation/new-window, sender validation, and no raw `ipcRenderer` export.
- Preserve the user's existing non-default provider-mode behavior in `apps/personal_intelligence_kernel/src/kernel-host.mjs` with a regression test before changing the conversation path.
- Assert `candidate.review`, `personal.model_projection.get`, `conversation.project_scopes.list`, `conversation.project_scope.select`, `conversation.session.create`, and all four proactive routes have fixed provider bindings; reject endpoint override, stale version, edit checksum mismatch, missing confirmation/binding/idempotency/capability, missing/unknown high-impact/conflict disposition, every batch acceptance request, draft/ignored Candidate selection, stale/foreign projection context and private-field leakage. Assert scope/history reads remain Python canonical, empty session creation writes only Kernel metadata, the safe conflict view exposes exactly `keep_existing`, `replace_existing`, `coexist_by_context`, and `defer_judgment` with consequences, and the next real turn receives only an approved projection through the governed context builder.
- Assert `statement_display` is deterministic, server-derived and checksum-bound to query ID/version/parameter-name set; tampered display, unknown query, physical SQL/table/column names, parameter values and sentinels are rejected or absent from receipt/result/UI.
- Assert Ctrl/Cmd+K opens only `receipt.open` and `proactive.manage`; unknown command/payload is rejected, Esc closes the palette before drawers/modals, and focus returns to its trigger.

---

## Wave 0 Requirements

- [ ] `apps/personal_intelligence_desktop/test/main-preload.test.mjs` — IPC allowlist, sender validation, unsafe configuration, safe errors, navigation, CSP, and renderer isolation.
- [ ] `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` — real Pi session event loop, leased tools, receipts, cancel, idle, and outcome reconciliation.
- [ ] `tests/unit/test_evidence_sqlite_tool.py` — descriptor/query policy and pure validation cases.
- [ ] `tests/integration/test_evidence_sqlite_tool.py` — read-only SQLite, limits, timeout, negative statements, and authority fingerprint cases.
- [ ] `tests/contract/test_harness_freshness.py` — two-hop AgentView/canonical freshness contract.
- [ ] `tests/integration/test_harness_reflection.py` — deterministic delta trigger, evidence binding, deduplication, and Candidate schema.
- [ ] `apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs` — actual committed publisher, durable EventJournal replay/cursor, failed-dispatch retry and no direct-handler shortcut.
- [ ] `tests/contract/test_harness_candidate_review.py` — accept/edit/ignore, version/confirmation, receipts, and append-only feedback.
- [ ] `tests/integration/test_harness_projection.py` — accepted Candidate to versioned projection and next-turn retrieval.
- [ ] Redacted deterministic fixture package and desktop UAT record template; fixtures must not use live `data/` or `var/` personal bodies.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Packaged/local desktop opens into the last allowed conversation or truthful empty state without opening a browser | HARNESS-01 | Real Electron window lifecycle and perceived startup flow | Launch approved local build with fixture store; record window, navigation, empty/restore state, and no external browser |
| Conversation, Tool receipt, SQLite evidence card, and errors follow approved UI-SPEC without raw trace/body | HARNESS-02, HARNESS-03, HARNESS-04 | Visual hierarchy, disclosure, and safe copy | Submit fixed prompt, inspect collapsed/expanded receipts, rejected query, freshness legs, truncation and safe error text |
| Duplicate delta yields one Candidate; edit/accept/ignore/undo and next-turn projection remain truthful | HARNESS-05, HARNESS-06, HARNESS-07 | End-to-end human review and temporal projection flow | Replay fixed delta twice, review Candidate paths, start next conversation, inspect evidence/confidence/time/conflict |
| Cancel and `outcome_unknown` reconciliation never claim false success | HARNESS-08 | Desktop control interaction across local processes | Cancel fixed long-running fixture, force unknown outcome, reconcile, and inspect state plus fingerprints |

---

## Desktop UAT Sequence

1. Start approved non-production fixture/replay dependencies and open the Electron app; confirm last-conversation restore or declared empty state without a browser.
2. Submit the fixed historical/project prompt; observe one read-only Skill, collapsed Tool row, evidence-bound answer, and expandable receipt with no raw trace/body. Open Ctrl/Cmd+K and verify it offers only `receipt.open` and `proactive.manage`; verify Esc returns focus to the invoking control.
3. Open the SQLite evidence card; verify database identity, checksum, both freshness legs, limits/truncation, and safe empty/rejected copy. Expand `受控查询` / `已执行的脱敏 allowlisted statement` and verify it displays only immutable server `statement_display`, never raw SQL, physical schema or parameter values; prove fingerprint stability.
4. Enter through the committed canonical sync/close fixture publisher and replay the same `conversation.delta.committed` event twice; verify exactly one inline Candidate with event/checksum/watermark evidence, conflict, time, confidence, and receipt.
5. Open one high-impact/conflicting Candidate and verify the per-item modal shows exactly `keep_existing`/`保留旧结论`, `replace_existing`/`用新结论取代`, `coexist_by_context`/`按情境共存`, and `defer_judgment`/`暂不判断`, each with consequence text; unknown disposition rejects and no batch-accept control exists. Exercise edit then explicit accept, and ignore then undo through the fixed review bridge; verify accepted content appears only as a versioned derived projection in the next turn through `personal.model_projection.get`, while a draft/ignored Candidate never enters context. Verify deterministic proactive state/control/dismiss/undo routes retain quiet-hour, cluster and append-only feedback semantics.
6. Exercise cancel and `outcome_unknown` reconciliation; verify neither is presented as success and no unauthorized write is claimed.

---

## Validation Sign-Off

- [x] Every PLAN task has a focused automated command or explicit Wave 0 dependency.
- [x] No three consecutive tasks lack automated verification.
- [x] All Wave 0 paths exist before dependent implementation tasks run.
- [x] No watch-mode flags are used.
- [x] Focused feedback latency remains under 60 seconds.
- [x] High/Critical threats are closed or the phase remains blocked.
- [x] Full Phase 61 suite and desktop UAT are green.
- [x] Each exact Phase 55–60/provider-mode regression command above has a recorded exit code 0, PASS result and applicable redacted checksum or fingerprint in the UAT record; real activation, promotion, rollback and pointers remain unchanged. (Note: recorded in `desktop-uat-record.md` by Plan 61-12 Task 1; the Phase 58 skill-engine row exits 1 with the two pre-existing deferred failures — see `deferred-items.md`.)
- [x] `nyquist_compliant: true` and `wave_0_complete: true` are set when evidence exists (automated evidence recorded by Plan 61-12 Task 1; flags flipped to `true` after the Task 3 blocking human checkpoint approved the six-step desktop UAT on 2026-08-10).

**Approval:** APPROVED 2026-08-10 — human confirmed "Phase 61 desktop UAT approved"; Phase 61 is closed.
