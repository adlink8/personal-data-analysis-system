---
phase: 61
slug: conversation-first-desktop-harness-and-evidence-bound-reflection-loop
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-08-09
---

# Phase 61 — Validation Strategy

> Per-phase validation contract for the conversation-first desktop and evidence-bound reflection Walking Skeleton.

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

---

## Requirement Verification Map

| Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| HARNESS-01 | T61-UI-01 | Main creates a secure local window; renderer has no Node authority; last-conversation/empty state loads | Node unit + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs` | ❌ W0 | ⬜ pending |
| HARNESS-02 | T61-AGENT-01 | One `session.prompt()` turn leases only Skill tools, observes Tool receipts, and settles without a second outer loop | Kernel integration | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | ❌ W0 | ⬜ pending |
| HARNESS-03 | T61-SQL-01 | Approved descriptor queries succeed; mutation, scope escape, unsafe PRAGMA, ATTACH, extension, multi-statement, and excessive output fail closed with invariant fingerprints | Python unit/integration | `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py` | ❌ W0 | ⬜ pending |
| HARNESS-04 | T61-FRESH-01 | Both source-to-AgentView and AgentView-to-canonical freshness/backlog are returned; stale/unknown is never labelled current | Python contract | `python -m pytest -q tests/contract/test_harness_freshness.py` | ❌ W0 | ⬜ pending |
| HARNESS-05 | T61-REFLECT-01 | Same canonical delta and rule version deduplicate; Candidate retains evidence, conflict, time, confidence, and receipt | Python integration | `python -m pytest -q tests/integration/test_harness_reflection.py` | ❌ W0 | ⬜ pending |
| HARNESS-06 | T61-REVIEW-01 | Accept/edit/ignore validate version and confirmation; no direct authority mutation; feedback is append-only | Python contract + desktop UAT | `python -m pytest -q tests/contract/test_harness_candidate_review.py` | ❌ W0 | ⬜ pending |
| HARNESS-07 | T61-PROJ-01 | Accepted content becomes a versioned derived projection with provenance, freshness, confidence, time and conflict; generated draft never becomes fact | Python unit/integration | `python -m pytest -q tests/unit/test_personal_state_projection.py tests/integration/test_harness_projection.py` | ⚠ partial/W0 | ⬜ pending |
| HARNESS-08 | T61-PRIV-01 | No raw IPC/endpoint escape, secret/body leakage, false cancel/reconcile success, or unauthorized authority change | Node/Python integration + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs` and `python -m pytest -q tests/integration/test_pi_kernel_events.py` | ⚠ partial/W0 | ⬜ pending |

*Plan/task IDs will be bound to these requirement rows after PLAN.md generation.*

---

## Required Negative and Invariant Tests

- Assert a real conversation route calls `AgentSession.prompt()` and observes Tool-call/result plus final settled/idle state; a provider-only or fixed `SkillEngine.run()` path must fail the acceptance test.
- Refuse every Tool proposal outside the active Skill lease before bridge dispatch and again at the Python gateway; the default Conversation profile exposes no mutation, promotion, activation, or rollback Tool.
- Fingerprint every authority database and active pointer before and after SQLite read, rejection, timeout, cancel, ignored Candidate, and failed confirmation. Only the intended append-only Candidate/feedback/projection stores may change after confirmed acceptance.
- Use sentinel secrets and raw-body fixtures to scan main/preload/renderer responses, logs, receipts, Task/Session/Event storage, and screenshots for body, prompt, completion, credential, token, and secret leakage.
- Assert Electron `nodeIntegration: false`, `contextIsolation: true`, `sandbox: true`, restrictive CSP, denied navigation/new-window, sender validation, and no raw `ipcRenderer` export.
- Preserve the user's existing non-default provider-mode behavior in `apps/personal_intelligence_kernel/src/kernel-host.mjs` with a regression test before changing the conversation path.

---

## Wave 0 Requirements

- [ ] `apps/personal_intelligence_desktop/test/main-preload.test.mjs` — IPC allowlist, sender validation, unsafe configuration, safe errors, navigation, CSP, and renderer isolation.
- [ ] `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` — real Pi session event loop, leased tools, receipts, cancel, idle, and outcome reconciliation.
- [ ] `tests/unit/test_evidence_sqlite_tool.py` — descriptor/query policy and pure validation cases.
- [ ] `tests/integration/test_evidence_sqlite_tool.py` — read-only SQLite, limits, timeout, negative statements, and authority fingerprint cases.
- [ ] `tests/contract/test_harness_freshness.py` — two-hop AgentView/canonical freshness contract.
- [ ] `tests/integration/test_harness_reflection.py` — deterministic delta trigger, evidence binding, deduplication, and Candidate schema.
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
2. Submit the fixed historical/project prompt; observe one read-only Skill, collapsed Tool row, evidence-bound answer, and expandable receipt with no raw trace/body.
3. Open the SQLite evidence card; verify database identity, checksum, both freshness legs, limits/truncation, and safe empty/rejected copy; prove fingerprint stability.
4. Emit the same canonical conversation-delta fixture twice; verify exactly one inline Candidate with evidence, conflict, time, confidence, and receipt.
5. Exercise edit then explicit accept, and ignore then undo; verify accepted content appears only as a versioned derived projection in the next turn.
6. Exercise cancel and `outcome_unknown` reconciliation; verify neither is presented as success and no unauthorized write is claimed.

---

## Validation Sign-Off

- [ ] Every PLAN task has a focused automated command or explicit Wave 0 dependency.
- [ ] No three consecutive tasks lack automated verification.
- [ ] All Wave 0 paths exist before dependent implementation tasks run.
- [ ] No watch-mode flags are used.
- [ ] Focused feedback latency remains under 60 seconds.
- [ ] High/Critical threats are closed or the phase remains blocked.
- [ ] Full Phase 61 suite and desktop UAT are green.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` are set when evidence exists.

**Approval:** pending
