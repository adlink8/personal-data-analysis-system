# Phase 61 Desktop UAT — Redacted Evidence Record

> Privacy-safe verification record for the Phase 61 conversation-first desktop
> harness and evidence-bound reflection loop (HARNESS-08 closure, Plan 61-12).
>
> **Privacy rule:** this record contains NO prompt, completion, body, credential,
> token, raw SQL, physical schema, parameter value, or selected-thread display
> text. Every row below records only redacted metadata: command (verbatim),
> exit code, PASS/FAIL/BLOCKED status, checksum/authority/provider-mode
> fingerprints, ISO timestamp, and a redacted fixture ID.
>
> **Status:** Task 1 (Plan 61-12) automated evidence recorded. The six numbered
> UAT steps (1. last/recent/select + scope list/select + empty session, 2. real
> Pi lifecycle, 3. controlled-query display, 4. committed delta/replay,
> 5. review/projection/proactive, 6. cancel/resume/outcome_unknown) are
> completed as automated rows below; the blocking Electron walking-skeleton
> manual pass is recorded by Task 3 against this same record.

---

## Record metadata

| Field | Value |
|-------|-------|
| Phase | 61-conversation-first-desktop-harness-and-evidence-bound-reflection-loop |
| Plan | 61-12 (closure / HARNESS-08) |
| Fixture ID (redacted) | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Deterministic zero-paid provider | Kernel `providerMode=replay` (no live `data/`, `var/`, no paid model) |
| Temporary authority fixture | `active_pointer.txt` (`mode=legacy`, primary unactivated) + canonical/watermark/permission/value fixture files |
| Record created | 2026-08-09T23:50:12Z |
| Repository HEAD at record time | `743006d` |

---

## Task 1 aggregate regression (Plan 61-12 `<verify>` command, executed verbatim)

The plan `<verify>` chain was executed. Every segment before the known
environmental failure passed (exit 0); the chain terminates at the Phase 58
Skill segment with the two pre-existing failures documented in
`deferred-items.md` (NOT caused by Plan 61-12 changes, and left untouched per
scope boundary). Each segment's independent exit code is recorded below.

### T1-1 — Desktop boundary + committed-delta reflection (Node)

```
node --test apps/personal_intelligence_desktop/test/*.test.mjs apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Tests | 54 passed / 0 failed |
| Fingerprint | n/a (no checksum emitted) |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

> NOTE (deviation): the plan names the full-path fixture
> `apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs`, which does
> NOT match the `*.test.mjs` glob above. The fixture is therefore executed
> explicitly as its own recorded command (T1-1b) so every full-path assertion
> has deterministic automated evidence.

### T1-1b — Deterministic full-path replay fixture (Node, explicit)

```
node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Tests | 8 passed / 0 failed (D1–D8) |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

D1–D8 cover: fixed provider dispatch for last/recent/select + scope list/select
+ `conversation.session.create` (empty/runtime-scoped); safe-copy view models;
`evidence.sqlite_query` checksum-bound `statement_display` plus unknown-query /
tampered-display rejection; real Pi prompt/tool/idle turn; committed
delta publish/replay → exactly one Candidate; individual review / derived
projection / four proactive routes / recovery state; and the authority +
Phase 60 activation + no-second-store invariants.

### T1-2 — Phase 61 Python contract/integration batch

```
python -m pytest -q tests/integration/test_pi_kernel_events.py tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py tests/contract/test_harness_freshness.py tests/contract/test_harness_conversation_projection.py tests/integration/test_harness_reflection.py tests/integration/test_harness_proactive.py tests/contract/test_harness_candidate_review.py tests/contract/test_pi_domain_gateway.py tests/integration/test_harness_projection.py
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

This batch includes the Plan 61-12 extension to
`tests/integration/test_pi_kernel_events.py` (recovery-route truthfulness:
`test_recovery_routes_reject_without_actual_reconciliation`,
`test_recovery_rejections_never_append_success_events_or_false_cursor`,
`test_replay_task_recovery_never_claims_false_success`) — 6/6 pass.

### T1-3 — Phase 55 capability registry (Python)

```
python -m pytest tests/contract/test_project_capability_registry.py -q
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Registry checksum | `419b7a7bd23951c7ad0cb610e080576f7c4c960f8cf5ad88b3795e111fe13eba` (45 operations incl. `evidence.sqlite_query`) |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-4 — Phase 56 warehouse denial/invariants

```
python -m pytest tests/security/test_pi_warehouse_tool_containment.py -q
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Authority fingerprint (live) | canonical_db `71fc6575…ee6ac`, active_pointer `c111e654…4bc1a`, personal_db `227d8a10…7b7` (unchanged) |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-5 — Phase 58 Skill lease/selection

```
npm test --prefix apps/personal_intelligence_kernel -- --test-name-pattern=skill-engine
```

| Field | Value |
|-------|-------|
| Exit code | 1 |
| Result | FAIL (with 2 pre-existing failures documented in `deferred-items.md`; the three `skill-engine` tests themselves PASS) |
| Skill checksum | `pi-skills.json` sha256 `ce03b0f3…26e09`; `knowledge.research` manifest checksum prefix `db6d597440827f26` |
| Known failure 1 | `production capability registry loads the approved project surface` — expects 44 operations, `project-capabilities.json` contains 45 (registration of `evidence.sqlite_query` by Plan 61-04). Pre-existing; recorded in `deferred-items.md`; NOT fixed in Plan 61-12 (out of scope; Phase 61 closure owner). |
| Known failure 2 | `real Pi Skill -> domain tool -> isolated SQLite write -> verification` — `domain_test_server_unavailable:fetch failed`: requires a live Python domain test authority on the loopback, unavailable in this environment. Pre-existing, environmental. |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

> Environment note: on this Node v24.13.0 host the `--test-name-pattern`
> argument is not honored by the test runner (all kernel tests execute), which
> surfaces both pre-existing failures on this command. Recorded truthfully;
> both are out of Plan 61-12 scope.

### T1-6 — Phase 58 forbidden/recovery sequence

```
python -m pytest tests/integration/test_pi_skill_recovery.py -q
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Skill checksum | `pi-skills.json` sha256 `ce03b0f3…26e09` |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-7 — Phase 59 Kernel control reducer

```
node --test apps/personal_intelligence_kernel/test/runtime-control.test.mjs
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Policy checksum | `operation-schema.mjs` sha256 `bcd2547c…36b8d5`; `runtime-control.mjs` sha256 `af80ee94…c7786` |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-8 — Phase 59 cancel/resume/reconcile

```
python -m pytest tests/integration/test_pi_runtime_control.py -q
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Authority fingerprint | kernel `resource-policy.mjs` sha256 `6b30517b…07e2`; live authority fingerprints unchanged (T1-4) |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-9 — Phase 57/60 activation and exact rollback guards

```
python -m pytest tests/e2e/test_pi_snapshot_release.py tests/e2e/test_pi_capability_os_activation.py -q
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Policy checksum / active-pointer fingerprint | `active_pointer.txt` fixture `mode=legacy` (primary unactivated); live `knowledge_index_active.txt` `c111e654…4bc1a` unchanged |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

### T1-10 — Phase 61 preserved non-default provider mode

```
node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs
```

| Field | Value |
|-------|-------|
| Exit code | 0 |
| Result | PASS |
| Provider-mode fingerprint | `de3b29b0178cfec6e07d5d6b4a3ad4ab1bed61906bcaca59f2135e5809db5ca7` |
| Fixture ID | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Timestamp | 2026-08-09T23:50:12Z |

---

## Six-step UAT sequence — automated evidence rows (Task 1 stage)

Each numbered step's deterministic automated evidence is supplied by the
fixture; the blocking Electron walking-skeleton manual pass is recorded by
Task 3 against the same step numbers.

| Step | Scope | Evidence command | Status |
|------|-------|------------------|--------|
| 1. | last/recent/select, scope list/select, empty session create; no browser/body persistence; empty/stale/partial/pagination states | D1 + D2 (fixture) | PASS (automated) |
| 2. | Real Pi lifecycle and palette focus | D4 + D6 (fixture); conversation-turn 18/18 | PASS (automated) |
| 3. | SQLite card: identity/checksum/two freshness legs; `受控查询` / `已执行的脱敏 allowlisted statement` renders only server `statement_display`; unknown-query/tamper rejection; no raw SQL/schema/value | D3 (fixture); T1-2 evidence-sqlite batch | PASS (automated) |
| 4. | Committed delta / replay; exactly one Candidate | D5 (fixture); T1-1 delta-reflection 54/54 | PASS (automated) |
| 5. | Four-option Candidate review, derived projection, deterministic proactive control/quiet/cluster/dismiss/undo | D6 (fixture) | PASS (automated) |
| 6. | cancel / resume / outcome_unknown; never false success | D7 (fixture); T1-7 + T1-8 + T1-2 extension | PASS (automated) |

---

## No-browser / no-paid / no-activation assertions

- [ ] 不使用浏览器：no browser, live `data/` or `var/` personal store was opened or read for evidence (deterministic replay fixtures only).
- [ ] No paid model or live provider call was made (`providerMode=replay`; persisted dashscope config not engaged by any recorded command).
- [ ] No activation, promotion, rollback, pointer-change or destructive CLI path was invoked (fixture records the complete dispatched-operation set; no authority-mutation operation appears).
- [ ] Phase 60 activation state unchanged: `active_pointer.txt` fixture stays `mode=legacy`; primary remains unactivated; live authority fingerprints unchanged.
- [ ] No second conversation fact store: only the four governed Kernel DBs exist after traversal (`events.sqlite`, `pi_kernel_tasks.sqlite`, `pi_kernel_sessions.sqlite`, `pi_kernel_candidates.sqlite`).
- [ ] No localStorage/disk body persistence and no raw SQL/physical schema/parameter value/credential/body sentinel appears in any recorded envelope, store or log.

## Known deferred / out-of-scope items (recorded truthfully)

1. Phase 58 Skill segment (`npm test --test-name-pattern=skill-engine`) exits 1
   because the pre-existing capability-registry operation count (44 expected vs
   45 present) and the environmental `skill-warehouse-e2e` Python-domain-server
   requirement surface when all kernel tests execute on this Node v24 host.
   Both are already tracked in `.planning/.../deferred-items.md`; neither is
   caused by Plan 61-12 and neither was modified here.
2. Desktop `turn`/`review` provider request-field alignment with the Kernel
   route bodies (recorded in the 61-11 SUMMARY field-mapping risk) is not
   changed here; the fixture traverses the real Kernel routes directly with the
   exact route bodies and the desktop route provider for navigation/session
   intents. Phase 61 closure owner to reconcile the desktop request mapping.
3. Fixture filename `desktop-uat-fixture.mjs` is not covered by the plan's
   `*.test.mjs` glob; it is executed explicitly (T1-1b). Flagged for the phase
   summary so the closure can either rename the glob or the fixture.
