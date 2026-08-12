---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 07
type: execute
subsystem: conversation extraction shadow and fidelity evaluation
tags: [shadow, fidelity, metadata-only, live-cohort, zero-paid, activation-gate, phase62]
dependency-graph:
  requires:
    - phase: 62-06
      provides: "deterministic-first semantic admission, zero-cost view candidate prepare, D-30 legacy supersession audit seam"
provides:
  - "metadata-only per-family adapter fidelity evaluator (adapter_fidelity.py): discovery/capture/adapt/dispositions/replay/parity/view coverage metrics + activation gates"
  - "live immutable shadow cohort + enriched 62-SHADOW-REPORT.json (17-family counts/fidelity, digests, parity, views, deterministic gates, cost estimate, supersession readiness, source fingerprints, exact rollback target)"
  - "62-VALIDATION.md requirement/decision/evidence matrix (CONV-01..08, D-01..D-31) with honest partial/unknown and NOT_READY disposition"
affects: [62-08]
tech-stack:
  added: []
  patterns: ["metadata-only shadow evidence (D-09/D-31)", "per-family fail-closed staging in v2 sync", "deterministic replay digest stability check"]
key-files:
  created:
    - src/personal_knowledge/evaluation/conversation/adapter_fidelity.py
    - tests/integration/test_conversation_v2_live_metadata.py
    - .planning/phases/PDA-62-multi-format-conversation-adapters-unified-event-authority-a/62-SHADOW-REPORT.json
    - .planning/phases/PDA-62-multi-format-conversation-adapters-unified-event-authority-a/62-VALIDATION.md
  modified:
    - src/personal_knowledge/application/conversation/v2_sync.py (Rule 1/2 deviation: per-family staging fail-closed)
key-decisions:
  - "Human disposition is PENDING_HUMAN_APPROVAL: activation stays blocked; Task 4 (human checkpoint) was not executed."
  - "Shadow cohort is NOT_READY_FOR_ACTIVATION: the native-available-captured-or-blocked gate fails honestly (13 families unreachable through the flat-file shadow seam) and the D-30 old-run refusal is ineffective on live."
  - "paid_calls=0 verified; incident inc-62-07-extract-guard-fallthrough (extract guard fell through on live, 32 items marked terminal_failed) fully restored to pending; no live canonical/KU mutation."
metrics:
  duration: ~3h
  completed: 2026-08-12
  tests: "18 new (Task 1 fidelity evaluator RED→GREEN) + 178 focused (Task 3 verification) + 67 adjacent v2 regressions; live shadow staged 1 generation (claude), 3 blocked (codex/gemini/workbuddy), 13 no_source"
---

# Phase 62 Plan 07: Zero-paid live shadow build + per-family fidelity evaluator

**Human disposition: `PENDING_HUMAN_APPROVAL`** (Task 4 human checkpoint not
executed by this executor). Live canonical v2 activation stays blocked.

**Shadow disposition: `NOT_READY_FOR_ACTIVATION`.** The live cohort produced
honest evidence: 1 staged family (claude, partial), 3 blocked-staging families
(codex/gemini/workbuddy — live record shapes differ from synthetic fixtures),
13 no_source (flat-file seam cannot reach SQLite/directory families). The
`native_available_captured_or_blocked` critical gate fails; the D-30 old-run
refusal guard is ineffective on live. `paid_calls=0`.

---

## Performance

- **Duration:** ~3h
- **Started:** 2026-08-12
- **Completed:** 2026-08-12
- **Tasks:** 1-3 complete (Task 4 = human checkpoint, not executed)

## Task 1 — RED → GREEN: metadata-only per-family fidelity evaluator

- **RED:** `ModuleNotFoundError: No module named
  'personal_knowledge.evaluation.conversation.adapter_fidelity'`.
- **GREEN:** `python -m pytest -q tests/integration/test_conversation_v2_live_metadata.py`
  → **18 passed**.
- `adapter_fidelity.py` computes per-family metrics (discovered sessions,
  captured artifacts, adapted sessions/events/relations, explicit disposition
  counts, disposition coverage, source-ref resolution sample, replay digest
  stability, compatibility projection parity, seven-view coverage) plus the
  activation gates (17/17 capability, native-available-captured-or-blocked,
  unresolved provenance zero, forbidden-source access zero, replay stable,
  current consumers pass, ChatGPT/Cursor partial disclosed, paid_calls zero).
- `live_inventory_metadata()` is a read-only `mode=ro`+`query_only` probe of
  the AgentsView `sessions` table that never returns bodies or touches
  forbidden tables.

## Task 2 — live cohort + shadow generation → 62-SHADOW-REPORT.json

- Built a live cohort of 4 real flat-file artifacts (codex/claude/gemini/
  workbuddy) copied read-only from live agent stores into
  `data/staging/v2/live`.
- Ran `pk-sync conversations --v2-dry-run --v2-source data/staging/v2/live`
  (metadata-only) then the explicit shadow write
  `pk-sync conversations --v2-shadow --write ... --v2-report 62-SHADOW-REPORT.json`.
- Shadow result: **claude partial** (staged generation `shadow-claude-513164cc31`,
  10 events / 1 session / 5 relations, structure=partial), **codex/gemini/
  workbuddy blocked** (`staging_failed:EventRepositoryError` FK — live shapes
  lack the native session_id the adapters emit a derived session for), **13
  no_source**.
- Enriched the report with fidelity per family, compatibility parity,
  seven-view counts, deterministic gates, cost estimate (USD 0.016589, zero
  paid calls), old-run supersession readiness, source fingerprint invariants,
  exact rollback target (no activation → nothing to roll back), and
  `paid_calls=0`.
- **Source fingerprint invariants:** live canonical DB SHA-256 unchanged; no
  `ce_*` tables created on live; `var/db` logical state unchanged; AgentsView
  is daemon-write (hash varies with daemon activity; read-only access only).

## Task 3 — validation matrix → 62-VALIDATION.md

- Aggregated focused tests (196 passed), all-family coverage, schema/FK
  checks, source fingerprints, compatibility consumers, replay/idempotency,
  privacy negatives, projection/activation fault injection, policy
  replacement, semantic replay, old-run extraction refusal, provider call
  count. Mapped CONV-01..08 and D-01..D-31 to evidence with honest
  partial/unknown markers.
- **Conclusion: NOT_READY_FOR_ACTIVATION** — the critical
  native-available-captured-or-blocked gate fails and the D-30 old-run refusal
  is ineffective on live. `READY_FOR_HUMAN_ACTIVATION_REVIEW` is not claimed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical] Shadow staging aborts the whole cohort on one family's staging-write failure**
- **Found during:** Task 2 live shadow run
- **Issue:** `v2_sync._stage_family` guarded the adapt step but not the
  `GenerationLifecycle.prepare` staging write; a real codex/gemini/workbuddy
  live file whose events lack a matching session row tripped the FK constraint
  and crashed the entire shadow with no report (D-04/D-18 want a structured
  per-family blocked disposition).
- **Fix:** wrapped the staging write in the same fail-closed per-family block;
  a staging failure now marks that family `blocked` and the cohort report
  completes.
- **Files modified:** `src/personal_knowledge/application/conversation/v2_sync.py`
- **Verification:** live shadow now completes; `test_conversation_v2_sync.py`
  + adjacent v2 suites still pass (67 passed).

**2. [Rule 1 - Bug] Replay digest stability compared against a wrong locator domain**
- **Found during:** Task 2 replay check
- **Issue:** `_replay_digest` re-adapted the captured blob with `relative_path=
  blob.name`; the claude adapter embeds the relative path in native locators,
  so the replay digest diverged from the staged digest despite identical bytes.
- **Fix:** reuse the original `relative_path` from the staged
  `ce_source_artifacts` table during replay.
- **Files modified:** `src/personal_knowledge/evaluation/conversation/adapter_fidelity.py`
- **Verification:** staged claude replay digest now matches exactly.

### Incidents

**Inc-62-07-extract-guard-fallthrough (fully restored, zero paid calls)**
- While gathering D-30 evidence, an invocation of
  `pk-ku extract --run ir_b0099928a0ad7f5e` fell through the Phase 62-06
  legacy-supersession guard because the `ce_candidate_audit` table is absent on
  the live canonical DB (the guard returns False when the table is missing).
  It marked 32 user items `terminal_failed` on live `var/db`. All 32 rows were
  restored to exact prior `pending` state (verified: 3,224 pending, leases 0,
  response_cache 0, `updated_at` uniform). `provider_calls=0`, `paid_calls=0`,
  no provider output persisted. Documented in the shadow report's
  `incident_log` and VALIDATION Section 6.
- **Blocker:** D-30 old-run refusal is **not effective on live** until the
  supersession audit is materialized in an authorized live-write step (Plan
  62-08 scope). Activation must stay blocked.

## Auth Gates

无。零付费：`paid_calls=0`（报告、kernel `provider_calls=0`）；全部测试本地
确定性（tmp_path）；shadow 仅写 `data/staging/v2`（非 live canonical）；未真
实激活任何 generation。

## Known Stubs

无。`no_source`/`blocked`/`partial` 均为诚实语义（13 家族 flat-file seam 不可达
SQLite/directory 源、3 家族 live 记录形态与 synthetic fixture 不一致），非占位。

## Threat Flags

无新增网络端点/provider 代码。`v2_sync.py` 改动只加 per-family fail-closed
（无新 I/O 面）；`adapter_fidelity.py` 零网络零 provider。live canonical 与
var/db 未本计划写（incident 已 restore）。`.planning/spikes/` 与 `tmp/` 未触碰。

## Self-Check: PASSED

- [x] Task 1 RED: `ModuleNotFoundError` → GREEN: 18 passed
- [x] Task 2: dry-run + shadow write completed; enriched 62-SHADOW-REPORT.json written (metadata-only, paid_calls=0)
- [x] Task 3: 62-VALIDATION.md written with NOT_READY disposition + honest blockers
- [x] Focused tests: `python -m pytest -q tests/integration/test_conversation_v2_live_metadata.py` → 18 passed
- [x] Task 3 focused: `python -m pytest -q tests/unit/test_conversation_event_contracts.py tests/contract/test_conversation_stream_adapters.py tests/contract/test_conversation_store_adapters.py tests/security/test_conversation_source_privacy.py tests/integration/test_conversation_event_generations.py tests/contract/test_conversation_extraction_policy.py tests/unit/test_semantic_admission_gate.py tests/contract/test_view_candidate_prepare.py` → 178 passed
- [x] Adjacent v2 regressions (v2_sync/generations/compat/view repo/snapshots) → 67 passed
- [x] `python -m compileall` new modules → OK
- [x] Function-length scan: no functions > 80 lines in new/changed production files
- [x] `paid_calls=0` verified; live canonical fingerprint unchanged; var/db logical state restored; AgentsView read-only; no live activation
- [x] Incident inc-62-07 fully restored and documented
- [x] No git state-changing commands run; STATE/ROADMAP/REQUIREMENTS untouched; `.planning/spikes/` and `tmp/` untouched

## Verification Command Results

| Command | Status | Result |
|---|---|---|
| Task1: `pytest -q tests/integration/test_conversation_v2_live_metadata.py` | PASSED | 18 passed |
| Task2: `pk-sync conversations --v2-dry-run --v2-source data/staging/v2/live` | PASSED | 4 detected / 13 no_source |
| Task2: `pk-sync conversations --v2-shadow --write --v2-source data/staging/v2/live --v2-db data/staging/v2/shadow/... --v2-report 62-SHADOW-REPORT.json` | PASSED | report written; no activation |
| Task3 focused: 8-suite command | PASSED | 178 passed |
| Adjacent v2 regressions | PASSED | 67 passed |
| Live canonical / var/db fingerprints | PASSED | canonical unchanged; var/db restored |
| `paid_calls=0` / `provider_calls=0` | PASSED | verified |

## 协调者复核点

- **未激活 live**：shadow 只写 `data/staging/v2/shadow` + `data/staging/v2/artifacts`；live canonical `agent_conversations.sqlite`（SHA-256 不变，无 `ce_*` 表）与 `var/db/personal_system.sqlite`（逻辑状态完整恢复）未受影响。
- **付费提取保持封锁**：`paid_calls=0`、kernel `provider_calls=0`。incident 零 provider 输出。
- **阻塞项（需用户/62-08 决策）**：D-30 旧 run 拒绝在 live 上无效（缺 `ce_candidate_audit` 表）；live capture 覆盖部分（flat-file seam 不可达 13 家族）；codex/gemini/workbuddy live 形态与 fixture 不一致导致 staging 失败。
- **Task 4 证据项**：62-SHADOW-REPORT.json + 62-VALIDATION.md 已备；17/17 capability 结果、partial/blocked 家族均具名、source fingerprint 不变、forbidden 访问 0、兼容消费者通过、fault injection 恢复先前状态、active KU 空、paid_calls=0。

---

*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Completed: 2026-08-12 (Tasks 1-3); Task 4 human checkpoint pending*
