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
> **Status:** Task 1 (Plan 61-12) automated evidence recorded; Task 2 (Plan
> 61-12) completed the six executable UAT steps with per-step evidence rows,
> safe receipt status fields, redaction instructions, no-browser/no-paid/
> no-activation assertions and PASS/FAIL/BLOCKED verdicts. The six numbered
> steps (1. last/recent/select + scope list/select + empty session, 2. real Pi
> lifecycle and palette focus, 3. controlled-query display, 4. committed
> delta/replay, 5. review/projection/proactive, 6. cancel/resume/
> outcome_unknown) show PASS (automated). **Task 3 (Plan 61-12) blocking
> human checkpoint: human approved on 2026-08-10 ("Phase 61 desktop UAT
> approved")** — the blocking Electron walking-skeleton manual pass is
> recorded against this same record and the overall UAT is now PASS.

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
| Task 2 revision (Plan 61-12) | 2026-08-09 (six executable steps + safe receipt fields + redaction + assertions + verdicts); repository HEAD `e01dc24` |

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

## Six-step UAT sequence — executable checks and evidence rows

Each numbered step is executable against the redacted deterministic replay
fixture (`fixture:desktop-uat:replay:1a4ab12b2a5af038`). The automated evidence
rows below were recorded by Task 1 (Plan 61-12); the blocking Electron
walking-skeleton manual pass is recorded by Task 3 against the same step
numbers. Step verdicts are PASS/FAIL/BLOCKED against the automated evidence
only; the manual pass remains pending until Task 3.

| Step | Scope | Primary evidence | Step verdict |
|------|-------|------------------|--------------|
| 1. | last/recent/select, scope list/select, empty session create; no browser/body persistence; empty/stale/partial/pagination states | D1 + D2 (fixture); R1–R3 view-models; T1-1, T1-2, T1-3 | PASS (automated) |
| 2. | Real Pi lifecycle and palette focus | D4 (fixture); T1-10 conversation-turn 18/18; R13/R14 palette/focus | PASS (automated) |
| 3. | SQLite card: identity/checksum/two freshness legs; `受控查询` / `已执行的脱敏 allowlisted statement` renders only server `statement_display`; unknown-query/tamper rejection; no raw SQL/schema/value | D3 (fixture); T1-2 evidence-sqlite batch; T1-3 registry; T1-4 fingerprints | PASS (automated) |
| 4. | Committed delta / replay; exactly one Candidate, no duplicate | D5 (fixture); T1-1 delta-reflection; T1-2 reflection batch | PASS (automated) |
| 5. | Four-option Candidate review, derived projection, deterministic proactive control/quiet/cluster/dismiss/undo | D6 (fixture); T1-2 review/projection/proactive batch | PASS (automated) |
| 6. | cancel / resume / outcome_unknown; never false success | D7 (fixture); T1-7, T1-8, T1-2 extension | PASS (automated) |

### Step 1. Navigation/session split — last/recent/select, project scope list/select, new empty session; empty/stale/partial/pagination states; no browser/body persistence

**Executable checks**

1. Startup restores the last conversation through the fixed Python-canonical `conversation.thread.last` provider, or declares a truthful empty state; no browser is opened and no live `data/`/`var/` store is read.
2. `conversation.thread.recent` lists recent conversations and `conversation.thread.select` selects one, both served by the Python canonical authority; pagination/`hasMore` is preserved.
3. `conversation.project_scopes.list` / `conversation.project_scope.select` serve scope navigation from the Python canonical authority; stale/unknown scope status is never labelled current.
4. `conversation.session.create` creates only empty, runtime-scoped Kernel Session metadata (`session_id`, `project_scope_id`, `created_at`, `status="empty"`) plus an empty thread view; it never claims canonical history, `localStorage`, disk or any storage surface.
5. Empty/stale/partial/paginated thread states are preserved truthfully in the view models (safe copies); mutating the view model never reaches the bridge fixture data.
6. Malformed scope and untrusted sender are denied before any provider work; all routes stay `http://127.0.0.1` localhost-only.

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Desktop boundary + navigation/session view-models (R1–R3, IPC allowlist) | `node --test apps/personal_intelligence_desktop/test/*.test.mjs apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs` | 0 | PASS | n/a (no checksum emitted) | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Fixture D1 + D2 (fixed provider dispatch, empty session, no storage surface) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Python canonical scope/history contract | `python -m pytest -q tests/contract/test_harness_conversation_projection.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Capability registry bindings (scope/session operations) | `python -m pytest tests/contract/test_project_capability_registry.py -q` | 0 | PASS | Registry checksum `419b7a7bd23951c7ad0cb610e080576f7c4c960f8cf5ad88b3795e111fe13eba` (45 operations) | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** session `status=empty`; thread `state`, `pagination.hasMore`, `truncated`, `freshness.status`; scope `freshness.status`; `canonicalHistory=false`. No prompt/completion/body/credential/token/SQL/schema/parameter value/display text is recorded.

**Redaction:** all thread display text is replaced by `REDACTED_*` markers; malformed-scope and untrusted-sender probes use synthetic identifiers only.

**Assertions:** 不使用浏览器 — the fixture never opens an Electron window and never reads live `data/`/`var/` personal stores; no paid provider call; no activation/promotion/rollback/pointer change; no localStorage/disk body persistence.

**Step 1 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

### Step 2. Real Pi lifecycle and palette focus

**Executable checks**

1. One real turn (`POST /v1/conversations/turn`) runs the Pi lifecycle on the real Kernel route: exactly one `AgentSession.prompt()` with `source=rpc` and `expandPromptTemplates=false`, a leased tool set including `evidence.sqlite_query` and `knowledge.search`, `waitForIdle` awaited, and `dispose` in `finally`.
2. The pre-prompt projection provider injects only the approved derived projection (`version=1`, `status=current`, never `provenance_class="fact"`).
3. Only safe event categories (`tool_call`, `tool_result`, `settled`) project; prompt/completion/body/credential/SQL/schema/value sentinels never appear in the response or the four governed Kernel DBs; no display text is persisted.
4. Ctrl/Cmd+K command palette exposes exactly `receipt.open` (查看 receipt) and `proactive.manage` (管理主动提醒); any other command is rejected.
5. Layer manager traps focus; Esc closes palette → drawer → modal in strict LIFO order and returns focus to the invoking control.

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Fixture D4 (real Pi turn on real Kernel route) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Preserved non-default provider mode + turn lifecycle | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | 0 | PASS (18/18) | Provider-mode fingerprint `de3b29b0178cfec6e07d5d6b4a3ad4ab1bed61906bcaca59f2135e5809db5ca7` | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Palette + focus view-models (R13/R14) | `node --test apps/personal_intelligence_desktop/test/*.test.mjs apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** turn `state=settled`, `success`, `profile=conversation`, `skill_id`, event `category` list, lease tool names, receipt IDs and checksums. No prompt/completion/body/credential/token/SQL/schema/parameter value/display text is recorded.

**Redaction:** the fixture uses sentinel values (secret/raw-body/prompt/completion/credential/SQL/schema/parameter-value/thinking prefixes) that are asserted absent from every envelope and store; only redacted markers are recorded here.

**Assertions:** 不使用浏览器 — real Kernel/Electron-boundary traversal with no Electron window, no live `data/`/`var/` store; no paid provider (providerMode=replay); no activation/promotion/rollback/pointer change; no localStorage/disk body persistence.

**Step 2 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

### Step 3. SQLite evidence card — identity/checksum, two freshness legs, safe controlled-query display

**Executable checks**

1. The governed evidence card (`SQLite · 只读查询`) renders database identity, query checksum, both freshness legs (source→AgentView and AgentView→canonical), truncation and limits — matching the UI-SPEC card contract.
2. Expanding `受控查询` (`已执行的脱敏 allowlisted statement`) displays only the immutable server-derived `statement_display` bound by checksum to `query_id` + descriptor version + sorted parameter-name set; the exact display string is `conversation.evidence_messages.v1(session_id, after, limit)`.
3. Unknown query id, tampered display (checksum mismatch), changed parameter-name set and hostile raw-SQL/schema/parameter-value payloads are rejected; the receipt and card never carry raw SQL, physical schema or parameter values.
4. The main-process receipt normalization drops an unverified `statement_display` before the renderer; a hostile card never renders.
5. Read-only/write-denial invariants hold and authority fingerprints stay stable (Phase 56 warehouse containment).

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Fixture D3 (checksum-bound `statement_display`, unknown/tamper rejection) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| SQLite tool unit + integration | `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Registry includes `evidence.sqlite_query` | `python -m pytest tests/contract/test_project_capability_registry.py -q` | 0 | PASS | Registry checksum `419b7a7bd23951c7ad0cb610e080576f7c4c960f8cf5ad88b3795e111fe13eba` (45 operations) | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Warehouse denial/invariants (authority stable) | `python -m pytest tests/security/test_pi_warehouse_tool_containment.py -q` | 0 | PASS | Authority fingerprints unchanged: canonical_db `71fc6575…ee6ac`, active_pointer `c111e654…4bc1a`, personal_db `227d8a10…7b7` | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** `receipt_id`, `database_id`, `source`, `query_id`, `descriptor_version`, `query_checksum`, `row_count`, `limit`, `truncated`, `bytes`, `duration_ms`, `status`, `binding`, `freshness` legs. No raw SQL, physical schema/table/column name or parameter value is recorded.

**Redaction:** only the logical allowlisted statement display string is recorded; raw SQL, physical schema/table/column names and parameter values exist solely as negative fixture sentinels asserted absent and are never quoted here.

**Assertions:** 不使用浏览器 — no browser window, no live store; no paid provider; no activation/promotion/rollback/pointer change; no localStorage/disk body persistence; no raw SQL/schema/value rendered.

**Step 3 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

### Step 4. Committed delta / replay — exactly one Candidate, no duplicate

**Executable checks**

1. `conversation.delta.committed` is appended through the real internal committed producer route with the internal capability header; the public generic events route rejects the same event.
2. The durable EventJournal replays the committed delta; the real dispatcher consumes it exactly once and stages exactly one unique Candidate identity.
3. Re-running the dispatcher against the same events dispatches nothing new — no duplicate Candidate is ever minted.
4. Failed-dispatch/retry truth is covered by the delta-reflection contract (T1-1).

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Committed-delta reflection contract (combined desktop + delta-reflection) | `node --test apps/personal_intelligence_desktop/test/*.test.mjs apps/personal_intelligence_kernel/test/conversation-delta-reflection.test.mjs` | 0 | PASS (54/54) | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Fixture D5 (publish/replay → exactly one Candidate) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Reflection contract batch | `python -m pytest -q tests/integration/test_harness_reflection.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** delta event id (redacted), `duplicate=false`/`replay=true`, dispatcher `dispatched=1`, `failures=0`, staged candidate identity count `1`, `rule_version`. No prompt/completion/body/credential/token/SQL/schema/parameter value is recorded.

**Redaction:** committed-delta envelopes use synthetic checksums/watermark fixtures; no canonical or private content is recorded.

**Assertions:** 不使用浏览器 — no browser, no live store; no paid provider; no activation/promotion/rollback/pointer change; reflection entered only through the committed producer route and journal replay.

**Step 4 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

### Step 5. Candidate review, derived next-turn projection, fixed proactive routes

**Executable checks**

1. Individual `candidate.review` through the real Kernel → Gateway bridge returns a `reviewed` receipt with `feedback_id`, never a promotion/rollback/watermark/active-pointer claim; feedback is append-only and metadata-only.
2. The strict four-value conflict disposition (accept/edit/ignore paths, `keep_existing`/`replace_existing`/`coexist_by_context`/`defer_judgment`) is validated by the candidate-review and domain-gateway contracts; unknown/missing disposition rejects; batch acceptance rejects.
3. Next-turn derived projection (`personal.model_projection.get`, fixed GET route) returns only the approved derived version (`version=1`, `provenance_class=inference`, `status=current`, `corrigible`, never labelled a personal fact) and is injected only as a projection, never a fact.
4. The four fixed proactive routes (`proactive.state.get`, `proactive.controls.update`, `proactive.dismiss`, `proactive.dismiss.undo`) stay metadata-only and deterministic; one evidence cluster yields exactly one merged card (`已合并 2 条同簇证据`), quiet hours and append-only feedback semantics are retained, and escalation tiers stay `静默 badge → 行内卡 → 抽屉 → 需要确认才 modal`.
5. Private/override/schedule/value inputs are rejected before Gateway dispatch (no bridge call made).

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Fixture D6 (review/projection/four proactive routes) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Candidate review + domain gateway contracts | `python -m pytest -q tests/contract/test_harness_candidate_review.py tests/contract/test_pi_domain_gateway.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Projection contract (accepted → versioned projection) | `python -m pytest -q tests/integration/test_harness_projection.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Proactive determinism | `python -m pytest -q tests/integration/test_harness_proactive.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** review `status=reviewed`, `candidate_id` (redacted), `feedback_id`, `receipt_id`, `receipt_checksum`, `metadata_only`; projection `version`, `provenance_class`, `status`, `confidence`, `support_count`/`conflict_count`; proactive `operation`, `cluster_key` (redacted), `feedback_id`, `merged_count`, `quiet_hours`, `escalation` tiers. No prompt/completion/body/credential/token/SQL/schema/parameter value is recorded.

**Redaction:** Candidate, evidence and cluster identifiers use synthetic fixture ids; no canonical content, projection text or personal values are recorded.

**Assertions:** 不使用浏览器 — no browser, no live store; no paid provider; no activation/promotion/rollback/pointer change; feedback is append-only and never silently expands permissions or values.

**Step 5 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

### Step 6. cancel / resume / outcome_unknown — no false success

**Executable checks**

1. A turn that never settles yields `state=outcome_unknown` with `success=false` and aborts the hung session; `outcome_unknown` is never a success envelope.
2. A pre-aborted turn yields `state=cancelled` with `success=false`; the renderer shows `已取消：没有写入，也没有保留部分结果。` and never renders success.
3. Reconcile requires an explicit terminal state (`task_reconcile_state_required`); missing/nonexistent task, bogus `succeeded_now` state and non-resumable task never reconcile to success and never claim `succeeded`.
4. Resume/cancel of a nonexistent task fail closed (`task_not_found`) without any Gateway bridge call or unauthorized write.

**Evidence rows (recorded Task 1, verbatim)**

| Evidence | Command | Exit | Result | Checksum / authority fingerprint | Timestamp | Fixture ID |
|---|---|---|---|---|---|---|
| Fixture D7 (cancel/outcome_unknown/reconcile truth) | `node --test apps/personal_intelligence_desktop/test/desktop-uat-fixture.mjs` | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Kernel control reducer | `node --test apps/personal_intelligence_kernel/test/runtime-control.test.mjs` | 0 | PASS | Policy checksum `operation-schema.mjs` sha256 `bcd2547c…36b8d5`; `runtime-control.mjs` sha256 `af80ee94…c7786` | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Cancel/resume/reconcile Python | `python -m pytest tests/integration/test_pi_runtime_control.py -q` | 0 | PASS | Kernel `resource-policy.mjs` sha256 `6b30517b…07e2`; live authority fingerprints unchanged | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Kernel events recovery truthfulness (61-12 extension) | `python -m pytest -q tests/integration/test_pi_kernel_events.py` (within T1-2 batch) | 0 | PASS | n/a | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |
| Activation/rollback guards unchanged | `python -m pytest tests/e2e/test_pi_snapshot_release.py tests/e2e/test_pi_capability_os_activation.py -q` | 0 | PASS | `active_pointer.txt` fixture `mode=legacy` (primary unactivated); live `knowledge_index_active.txt` `c111e654…4bc1a` unchanged | 2026-08-09T23:50:12Z | `fixture:desktop-uat:replay:1a4ab12b2a5af038` |

**Safe receipt status fields recorded:** turn `state` (`outcome_unknown`/`cancelled`), `success=false`, abort count, renderer `isSuccess=false` + status text keys, reconcile error codes (`task_reconcile_state_required`, `task_not_found`, `task_not_resumable`, `stale_version`). No prompt/completion/body/credential/token/SQL/schema/parameter value is recorded.

**Redaction:** nonexistent-task and reconcile probes use synthetic task/session ids only; no private content is recorded.

**Assertions:** 不使用浏览器 — no browser, no live store; no paid provider; no activation/promotion/rollback/pointer change; recovery never appends a false success event or false cursor.

**Step 6 verdict:** PASS (automated) — manual walking-skeleton pass pending Task 3.

---

## No-browser / no-paid / no-activation assertions

These assertions were enforced by the Task 1 fixture and its sentinel walkers;
each step above re-states its applicable subset. The final manual confirmation
is recorded by Task 3.

- [ ] 不使用浏览器：no browser, live `data/` or `var/` personal store was opened or read for evidence (deterministic replay fixtures only).
- [ ] No paid model or live provider call was made (`providerMode=replay`; persisted dashscope config not engaged by any recorded command).
- [ ] No activation, promotion, rollback, pointer-change or destructive CLI path was invoked (fixture records the complete dispatched-operation set; no authority-mutation operation appears).
- [ ] Phase 60 activation state unchanged: `active_pointer.txt` fixture stays `mode=legacy`; primary remains unactivated; live authority fingerprints unchanged.
- [ ] No second conversation fact store: only the four governed Kernel DBs exist after traversal (`events.sqlite`, `pi_kernel_tasks.sqlite`, `pi_kernel_sessions.sqlite`, `pi_kernel_candidates.sqlite`).
- [ ] No localStorage/disk body persistence and no raw SQL/physical schema/parameter value/credential/body sentinel appears in any recorded envelope, store or log.

## Safe receipt status fields (recorded only)

Receipts are recorded as metadata-only status fields, never as private content:

- Session: `session_id`, `project_scope_id`, `created_at`, `status`
- Thread/view: `state`, `pagination.hasMore`, `truncated`, `freshness.status`, `canonicalHistory`
- Turn: `state`, `success`, `profile`, `skill_id`, event `category` list
- Evidence: `receipt_id`, `database_id`, `source`, `query_id`, `descriptor_version`, `query_checksum`, `row_count`, `limit`, `truncated`, `bytes`, `duration_ms`, `status`, `binding`, `freshness` legs
- Review/projection: `status`, `feedback_id`, `receipt_id`, `receipt_checksum`, `metadata_only`, `version`, `provenance_class`, `confidence`, support/conflict counts
- Proactive: `operation`, `cluster_key`, `feedback_id`, `merged_count`, `quiet_hours`, escalation tiers
- Recovery: turn `state` (`outcome_unknown`/`cancelled`), `success=false`, reconcile error codes

## Redaction instructions

1. Never record prompt, completion, body, credential, token, raw SQL, physical
   schema/table/column names, parameter values, or selected-thread display text.
2. Replace any display text with `REDACTED_*` markers (as the fixture does).
3. Record only: verbatim command, exit code, PASS/FAIL/BLOCKED, checksum or
   authority fingerprint, ISO timestamp, and redacted fixture ID.
4. Re-run the sentinel walkers after any manual edit and confirm no sentinel or
   forbidden key appears before committing.

## Overall UAT status

| Stage | Status |
|-------|--------|
| Step 1 — navigation/session split | PASS |
| Step 2 — real Pi lifecycle and palette focus | PASS |
| Step 3 — SQLite card display integrity | PASS |
| Step 4 — committed delta / replay | PASS |
| Step 5 — review / projection / proactive | PASS |
| Step 6 — cancel / resume / outcome_unknown | PASS |
| Blocking Electron walking-skeleton manual pass | PASS (Task 3 human approval 2026-08-10) |
| Overall | PASS |

> Truthful state: automated full-path evidence is recorded above; the Task 3
> blocking human checkpoint approved the six steps on 2026-08-10
> ("Phase 61 desktop UAT approved"). Phase 61 closure
> (nyquist/Wave 0 completion) is recorded in `61-VALIDATION.md` and
> `61-12-SUMMARY.md`.

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
