---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 06
type: execute
subsystem: conversation extraction admission
tags: [semantic-admission, deterministic-first, replay, candidate-prepare, view-policy, superseded-legacy, phase62]
dependency-graph:
  requires:
    - phase: 62-05
      provides: "deterministic seven-view builders (extraction_views.py), replaceable ExtractionPolicy, generation/policy-bound ViewRepository (derived_from_view + evidence_event_refs lineage)"
provides:
  - "deterministic-first, abstention-capable semantic admission seam (semantic_admission.py): structured admit/reject/abstain, reason codes, bounded redacted judge payload with evidence allowlist, deterministic ReplayJudge (zero paid calls)"
  - "view/policy/evidence-bound candidate prepare ledger (view_candidate_prepare.py): CandidateRunKey bound to active generation + view builder version + policy digest + semantic prompt/schema version + evidence digest; estimates per view type/family; legacy message-level runs superseded_policy via append-only audit; ce_candidate_* additive tables"
  - "pk-ku view-inspect / view-prepare / view-status commands + typed extract blocks for vc_* and superseded ir_* run ids (no paid extraction path)"
affects: [62-07, 62-08]
tech-stack:
  added: []
  patterns: ["deterministic-first gate + abstention-capable replay semantic gate (D-26/D-27)", "version-keyed zero-cost prepare ledger with supersession audit (D-24/D-30)", "typed paid-extraction block returning approval/pilot requirement (D-31)"]
key-files:
  created:
    - src/personal_knowledge/evaluation/conversation/semantic_admission.py
    - src/personal_knowledge/application/knowledge/view_candidate_prepare.py
    - tests/unit/test_semantic_admission_gate.py
    - tests/contract/test_view_candidate_prepare.py
    - tests/integration/test_view_candidate_ledger.py
  modified:
    - src/personal_knowledge/application/ku.py
key-decisions:
  - "Deterministic rejection (structure/privacy/secret/injection/unsupported source/empty evidence/invalid lineage) runs before any judge invocation and can never be overridden by the model; abstention is first-class (D-26)."
  - "The judge payload is bounded redacted view metadata + authorized event handles only; a judge can never add evidence outside the allowlist (D-27 / Pitfall 5)."
  - "Decision records preserve reason codes, claims, evidence handles, assessments and limitations — never a sensitive prompt body (D-27)."
  - "Candidate prepare is keyed by active generation + view builder version + policy digest + semantic prompt/schema version + evidence digest; a run approaches extraction only when every component matches and evidence resolves (Pattern 3)."
  - "Legacy message-level prepare runs (ir_*: 3,224 user + 21,263 assistant, 24,487 calls) are classified superseded_policy through an append-only audit transition; their 24,487 ledger rows/caches are never deleted (D-30)."
  - "No paid extraction path exists in Phase 62: pk-ku extract returns typed blocked errors for vc_* (names the separate approval/pilot requirement) and superseded ir_* run ids; view-prepare writes estimates/ledger only (D-31)."
requirements-completed: [CONV-07, CONV-08]
metrics:
  duration: ~105min
  completed: 2026-08-12
  tests: "61 new (26 semantic admission unit + 26 candidate prepare contract + 9 candidate ledger integration); adjacent regressions: ku CLI (pk_ku_cli/history/doctor/lifecycle/reconcile), knowledge gate/eligibility/extraction/prepare-floor, event repo/generations/sync/compat/adapters/snapshots, view repo/policy/views all passed; pk-ku doctor --skip-ports OK; git diff --check clean; compileall OK"
---

# Phase 62 Plan 06: Deterministic-first evidence-bound semantic admission + zero-cost view candidate prepare

**Replaces absorb-everything/message-regex preparation with a deterministic-first, evidence-bound semantic admission seam and a version-keyed zero-cost view candidate prepare path — while keeping every paid extraction path blocked.**

## Performance

- **Duration:** ~105 min
- **Started:** 2026-08-12
- **Completed:** 2026-08-12
- **Tasks:** 3 (all GREEN)
- **Files modified:** 3 created (2 production + 1 test split into 3 test files), 1 existing production file modified (`src/personal_knowledge/application/ku.py`)

## Accomplishments

- **Deterministic-first semantic admission gate** (`semantic_admission.py`): `SemanticVerdict(admit|reject|abstain)`, `ReasonCode` (structure/privacy/secret/injection/unsupported-source/no-evidence/invalid-lineage deterministic codes + evidence-outside-allowlist/malformed-judge post-judge safety + abstain codes), `Assessment/AssessedDimension` (novelty/durability/specificity/future-usefulness/contamination/contradiction), `JudgeInput` (bounded redacted view content + authorized event handles only), `SemanticGate.evaluate`, `ReplayJudge` (zero-paid deterministic provider), `make_replay_key` (same inputs → same digest) and `DecisionRecord` (reason codes only — never a prompt body). Deterministic rejections short-circuit before the judge is invoked and are non-bypassable; the judge can never add evidence outside the allowlist; abstention is first-class.
- **View/policy/evidence-bound prepare ledger** (`view_candidate_prepare.py`): `CandidateRunKey` bound to active generation + view builder version + policy digest + semantic prompt/schema version + evidence digest; `CandidateRunRepository` writes additive `ce_candidate_runs/estimates/audit` rows; estimates report calls/tokens/cost per view type and family (deterministic local arithmetic); prepare is idempotent by key; version mismatches, unresolved evidence and legacy run ids are rejected. Legacy message-level runs are classified `superseded_policy` via an append-only `ce_candidate_audit` transition — their 24,487 ledger rows/caches are never deleted (D-30).
- **`pk-ku` command surface** (`ku.py`): added `view-inspect` (active generation, policy/view counts, deterministic exclusions, semantic-gate replay coverage, pending estimates, `blocked_pending_user_cost_approval`), `view-prepare` (zero-cost estimates/ledger) and `view-status` (per-run ledger status / legacy superseded audit). `pk-ku extract` now returns typed blocked errors (exit 2) for `vc_*` run ids (naming the separate approval/pilot requirement) and for superseded `ir_*` run ids, via a read-only probe that never creates tables on the live conversation DB. Daily `ir_*` extract behavior is unchanged (existing tests pass).

## Task Commits

Per orchestrator instructions for this plan, no git state-changing commands were run; all six plan files were created but not committed (see 协调者复核点).

## Files Created/Modified

- `src/personal_knowledge/evaluation/conversation/semantic_admission.py` — semantic admission gate (new, all functions ≤ 80 lines).
- `src/personal_knowledge/application/knowledge/view_candidate_prepare.py` — prepare ledger + orchestration (new, all functions ≤ 80 lines).
- `tests/unit/test_semantic_admission_gate.py` — 26 RED→GREEN unit tests.
- `tests/contract/test_view_candidate_prepare.py` — 26 RED→GREEN contract tests (incl. Task 3 CLI block surface).
- `tests/integration/test_view_candidate_ledger.py` — 9 RED→GREEN integration tests (incl. 24,487-row legacy preservation).
- `src/personal_knowledge/application/ku.py` — `view-inspect`/`view-prepare`/`view-status` subcommands + extract guards (modified).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Plan `files_modified` named a non-existent `src/personal_knowledge/application/knowledge/ku.py` (Task 3)**
- **Found during:** initial plan read
- **Issue:** the plan and executor brief point to `src/personal_knowledge/application/knowledge/ku.py`, but the actual product CLI lives at `src/personal_knowledge/application/ku.py` (that is where `build_parser`/`main` and the existing `pk-ku` subcommands are defined; `tests/unit/test_pk_ku_cli.py` imports it from there).
- **Fix:** implemented Task 3's command surface in the real path `src/personal_knowledge/application/ku.py` (listed under `## Files Created/Modified` as the modified existing production file).
- **Files modified:** `src/personal_knowledge/application/ku.py`
- **Verification:** `test_pk_ku_cli.py` + new contract CLI tests all pass.

**2. [Rule 1 - Bug] `DEFAULT_POLICY` missing from view_candidate_prepare module scope (Task 3)**
- **Found during:** CLI smoke test (`view-inspect` failed with `NameError: name 'DEFAULT_POLICY' is not defined`)
- **Issue:** the orchestration functions referenced `DEFAULT_POLICY` without importing it.
- **Fix:** imported `DEFAULT_POLICY` at module level from `extraction_policy`.
- **Files modified:** `src/personal_knowledge/application/knowledge/view_candidate_prepare.py`

**3. [Rule 2 - Missing critical] Legacy extract guard could create candidate tables on the live conversation DB (Task 3)**
- **Found during:** review of `_cmd_extract` guard (guard called `repository.create_schema()` on the authority DB)
- **Issue:** a CLI guard must never write DDL to a live authority DB (AGENTS.md hard constraint; 62-05 no-authority-mutation).
- **Fix:** rewrote `_assert_legacy_not_superseded` as a read-only probe (read-only URI connection, returns False on missing table/file). Verified with a live-canonical test that no `ce_candidate_*` tables are created.
- **Files modified:** `src/personal_knowledge/application/knowledge/view_candidate_prepare.py`

**4. [Rule 1 - Bug / test defects] Replay judge matching and evidence fixtures (Task 1)**
- **Found during:** Task 1 GREEN (12 tests failing)
- **Issue:** (a) `ReplayJudge` matched on full `JudgeInput` equality while test call sites built fresh payload objects; (b) `_turn_view` lineage used string concatenation that broke with an integer evidence ref; (c) secret/injection fixtures referenced `ev:a1`/`ev:u1` as evidence while the index only contained `ev:u1`, so the lineage check fired before the secret/injection checks.
- **Fix:** `ReplayJudge` cases keyed by deterministic `view_id`; lineage built via f-string; fixtures reduced evidence to the single indexed event for the secret/body tests.
- **Files modified:** `src/personal_knowledge/evaluation/conversation/semantic_admission.py` + `tests/unit/test_semantic_admission_gate.py`

**5. [Rule 1 - Bug] Extract guard read the wrong DB for the supersession audit (Task 3)**
- **Found during:** CLI smoke + audit review
- **Issue:** the guard initially checked `args.db` (KU unified DB), but supersession audits live in the conversation authority DB.
- **Fix:** guard reads `AGENT_CONVERSATIONS_DB` via a read-only probe; contract test patches `project_paths.AGENT_CONVERSATIONS_DB` to the temp ledger DB.
- **Files modified:** `src/personal_knowledge/application/ku.py` + `tests/contract/test_view_candidate_prepare.py`

**6. [Rule 2 - Missing critical] Over-80-line functions (Task 2/3)**
- **Found during:** function-length scan (project contract: every function ≤ 80 lines)
- **Issue:** `prepare_view_run` (110 lines) and `_write_candidate_ledger` (81 lines) exceeded the limit.
- **Fix:** extracted `_write_candidate_ledger` and `_record_view_audit` helpers; re-scanned all three production files clean.
- **Files modified:** `src/personal_knowledge/application/knowledge/view_candidate_prepare.py`

---

**Total deviations:** 6 auto-fixed (5 Rule 1, 1 Rule 2 bundle). No Rule 4 STOPs. All fixes were correctness requirements, fixture defects, or CLI-safety hardening; no scope creep.

## Issues Encountered

- `FidelityProfile.from_dict` was needed to hydrate events from the event repository (fidelity_json round trip).
- The view `metadata` for a `CompactionWindowView` requires `summary_event_id`; the contract fixture must supply it as both a field and metadata.
- `ce_candidate_audit` requires the schema to exist before `classify_legacy_run`; integration tests call `repository.create_schema()` explicitly (documented in the repository contract).

## User Setup Required

None - no external service configuration required. All tests are local and deterministic.

## Next Phase Readiness

- 62-07 can consume `SemanticGate`/`ReplayJudge`/`DecisionRecord` for admission coverage and `CandidateRunRepository` for candidate staging under the `ce_candidate_*` ledger.
- `view-inspect`/`view-prepare`/`view-status` give operators a zero-paid operational view of the new extraction model.
- No paid provider, no `pk-ku extract`, no live canonical/KU writes: D-31 preserved.

## Auth Gates

无。零付费：全部测试本地确定性（tmp_path），无 LLM/provider/网络调用；`pk-ku extract` 未在任何路径真实执行（vc_* 与 superseded ir_* 均被类型化 block，exit 2）；CLI smoke 实测 `view-inspect`/`view-prepare`/`view-status` 的 `paid_calls=0`。三个新模块代码扫描无 `requests/urllib/httpx/openai/http://` 等网络或 provider surface。

## Known Stubs

无。语义门在无 replay 命中时返回结构化 abstain（诚实语义，非 stub）；estimate 使用确定性 `_MODEL_ESTIMATES` 常量（`gemini-3.5-flash-lite` 仅用于价格估算，从不发起调用）；`view-prepare` 的 status 恒为 `blocked_pending_user_cost_approval`（D-31 设计的刻意状态，非占位）。

## Threat Flags

无。三个新模块零网络端点、零 provider 代码、零 schema 变更在信任边界之外（仅 additive `ce_candidate_*` 表，与 62-05 的 `ce_view_*` 同模式）；live `agent_conversations.sqlite`（mtime 2026-07-27）与 `var/db/` 未被本计划代码写（实测：read-only probe 不建表，测试全 tmp_path）；`.planning/spikes/` 与 `tmp/` 既有的未提交改动原样保留；`ce_candidate_*` 仅存 run key/estimates/evidence handles/audit 元数据，不含正文或凭据；候选持久化不写 canonical/KU/authority（有专项测试断言）。

## Self-Check: PASSED

- [x] Task 1 RED：`ModuleNotFoundError: No module named '...semantic_admission'`；GREEN：`python -m pytest -q tests/unit/test_semantic_admission_gate.py` → 26 passed
- [x] Task 2 RED：`ModuleNotFoundError: No module named '...view_candidate_prepare'`；GREEN：`python -m pytest -q tests/contract/test_view_candidate_prepare.py tests/integration/test_view_candidate_ledger.py` → 35 passed（26+9）
- [x] Task 3 验证：`python -m pytest -q tests/contract/test_view_candidate_prepare.py tests/unit/test_knowledge_unit_gate.py` → 40 passed（26 新增 contract + 14 KU gate 无回归）
- [x] 全量新套件：61 passed（26 语义门 unit + 26 prepare contract + 9 ledger integration）
- [x] ku CLI 回归：`test_pk_ku_cli.py` 全过（含 `extract` 非增量/默认 model/watermark 系列）；`history`/`doctor`/`lifecycle`/`reconcile` unit 全过
- [x] 相邻回归：event repository/generations/v2 sync/compat、stream/store adapters、snapshots、view repository/policy/views、knowledge eligibility/extraction/prepare-floor/unit contracts、agentsview downstream、run_pipeline contracts 全过
- [x] `pk-ku doctor --skip-ports` → OK（exit 0，read-only）
- [x] `git diff --check` → clean（仅既有 .planning/spikes 的 LF/CRLF 警告，非本计划文件）
- [x] `python -m compileall` 新/改模块 → OK
- [x] 新生产文件函数均 ≤80 行（实测 semantic_admission.py、view_candidate_prepare.py 无超限；ku.py 仅既有 build_parser/_cmd_watermark 超限，非本次改动）
- [x] 零付费/无 provider 代码；live canonical 与 var/db 未写（read-only probe 实测不建表）；测试全 tmp_path；spikes/tmp 未触碰
- [x] D-30 复核：`test_legacy_rows_preserved_when_superseded` 写入 24,487 行 legacy items → classify 后行数不变、audit append-only、`assert_extraction_authorized` 抛 `LegacyRunSupersededError`

## Verification Command Results

| Command | Status | Result |
|---|---|---|
| Task1: `pytest -q tests/unit/test_semantic_admission_gate.py` | PASSED | 26 passed |
| Task2: `pytest -q tests/contract/test_view_candidate_prepare.py tests/integration/test_view_candidate_ledger.py` | PASSED | 35 passed (26 + 9) |
| Task3: `pytest -q tests/contract/test_view_candidate_prepare.py tests/unit/test_knowledge_unit_gate.py` | PASSED | 40 passed |
| New-suite total | PASSED | 61 passed |
| ku CLI regression (`test_pk_ku_cli.py`) | PASSED | all passed |
| Adjacent regressions (event repo/generations/sync/compat + adapters + snapshots + view repo/policy/views + knowledge gate/eligibility/extraction/prepare-floor + downstream contracts) | PASSED | all passed |
| `pk-ku doctor --skip-ports` | PASSED | exit 0 |
| `git diff --check` | PASSED | clean |
| `python -m compileall` new/modified modules | PASSED | OK |
| live canonical / var/db untouched; no provider/network code; spikes/tmp untouched | PASSED | verified |

## 协调者复核点

- **未提交/未改 live**：按本计划指令不运行 git 状态变更命令，六份计划文件保持未跟踪；live `agent_conversations.sqlite`（mtime 2026-07-27）与 `var/db/personal_system.sqlite` 完全未触碰；`.planning/spikes/` 与 `tmp/` 既有的未提交改动原样保留（`git status` 仍显示 spike 文件 M）。
- **付费提取保持封锁**：三条独立防线——(1) `SemanticGate` 只接受注入 judge，模块内无 provider 代码；(2) `CandidateRunRepository.assert_extraction_authorized` 对 `vc_*` 抛 `ViewExtractionBlockedError`（含 approval/pilot 文案）、对 legacy 抛 `LegacyRunSupersededError`；(3) `pk-ku extract` 对 `vc_*`/superseded `ir_*` 返回 exit 2。`view-prepare` 只写 estimates/ledger。CLI smoke 实测 `paid_calls=0`。
- **旧 runs 审计保留**：`test_legacy_rows_preserved_when_superseded` 写入 3,224+21,263=24,487 legacy items → `classify_legacy_run` 后行数不变（仅 append `ce_candidate_audit`），`assert_extraction_authorized` 拒绝执行；`test_audit_transition_is_append_only` 验证重复 classify 只增审计、不删行。
- **语义门可 replay**：`make_replay_key` 对同输入同 digest；`test_gate_is_fully_replayable` 断言两次 evaluate 决策与 replay_key 全等；`test_gate_deterministic_across_verdicts` 断言 admit/reject/abstain 均带确定性 replay_key；全部 26 个 unit 用例用 `ReplayJudge`（零调用成本）。
- **路径偏离说明**：Task 3 的实际实现文件为 `src/personal_knowledge/application/ku.py`（计划 `files_modified` 写的 `application/knowledge/ku.py` 不存在），见 Deviations #1。

---
*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Completed: 2026-08-12*
