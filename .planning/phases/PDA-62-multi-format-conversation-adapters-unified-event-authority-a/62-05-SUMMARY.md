---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 05
type: execute
subsystem: conversation adapters
tags: [extraction-views, extraction-policy, view-repository, lineage, replaceable-trace, phase62]
dependency-graph:
  requires:
    - phase: 62-04
      provides: "generation lifecycle, read-only active-generation event repository seam, deterministic compatibility projection"
provides:
  - "seven deterministic derived view builders (Turn/NativeTrace/Episode/CompactionWindow/Session/Topic/CrossSession) with stable generation+builder-version+evidence-set view ids"
  - "versioned replaceable ExtractionPolicy (priority bands, fidelity threshold, freshness/novelty, dedup/supersession, budgets, abstain/block reasons) and policy digest"
  - "generation/policy-bound view repository (additive ce_view_* tables) with idempotent rebuild, policy revision, generation drift, stale marking, lineage resolution and no authority mutation"
affects: [62-06, 62-07, 62-08]
tech-stack:
  added: []
  patterns: ["replaceable extraction policy (D-22/D-23)", "view lineage + evidence_event_refs (D-24)", "additive companion view schema beside event authority (D-16)"]
key-files:
  created:
    - src/personal_knowledge/application/conversation/extraction_views.py
    - src/personal_knowledge/application/conversation/extraction_policy.py
    - src/personal_knowledge/application/conversation/view_repository.py
    - tests/unit/test_conversation_extraction_views.py
    - tests/contract/test_conversation_extraction_policy.py
    - tests/integration/test_conversation_view_repository.py
  modified: []
key-decisions:
  - "Trace is one replaceable view: NativeTraceView is produced only from explicit source-native trace/turn/loop ids; adjacency guesses are never labeled native (D-20)."
  - "View identity = view type + generation + builder version + ordered evidence event set; rebuilds are identical and never re-run adapters (D-21)."
  - "Initial ExtractionPolicy locks CompactionWindow first (dense navigation signal), then native trace/episode (incl. turn), session, topic, cross-session; changing priority is a policy-only operation (D-22/D-23)."
  - "Compaction priority can never override missing evidence refs or low fidelity; candidates carry derived_from_view lineage and stable evidence_event_refs (D-24)."
  - "View persistence is additive ce_view_* companion tables bound to one staged generation and one policy digest; it never writes canonical_* compatibility rows, KU tables, or the authority pointer (D-16/D-17)."
patterns-established:
  - "Pattern 4: Replaceable extraction policy — adapters emit evidence semantics; view builders emit reproducible windows; policy ranks view types/fidelity/freshness/novelty and a new digest changes only queue ranks."
  - "Deterministic view fidelity aggregation: any member loss / missing native boundary / missing relation reduces the view fidelity; partial/unknown is never reported complete (D-13)."
  - "Contradiction slots are first-class deterministic view members (retained_and_compacted, native_id_collision) and persist through lineage resolution (D-24)."
requirements-completed: [CONV-06]
metrics:
  duration: ~75min
  completed: 2026-08-12
  tests: "61 new (31 views unit + 16 policy contract + 14 view repository integration); 145 adjacent 62-01..62-04 regressions passed; 39 downstream/legacy regressions passed; diff --check clean; compileall OK"
---

# Phase 62 Plan 05: Replaceable extraction views + versioned policy

**Deterministic seven-view extraction pipeline (Turn/NativeTrace/Episode/CompactionWindow/Session/Topic/CrossSession) with stable generation+builder+evidence view IDs, a versioned replaceable ExtractionPolicy whose trace/compaction priorities change scheduling without touching event identities, and a generation/policy-bound view repository that persists lineage without creating a fact authority.**

## Performance

- **Duration:** ~75 min
- **Started:** 2026-08-12
- **Completed:** 2026-08-12
- **Tasks:** 3 (all GREEN)
- **Files modified:** 6 created (3 production + 3 tests); no existing production files modified

## Accomplishments

- **Seven deterministic view builders** (`extraction_views.py`): view ids are `sha256(view_type|generation|builder_version|sorted evidence set)` so identical rebuilds are byte-identical without re-running adapters. `NativeTraceView` is emitted only from explicit source-native trace/turn/loop IDs; `EpisodeView` uses versioned deterministic relation-component heuristics with a partial `session_fallback`; `CompactionWindowView` binds each summary to its compacted/retained sets with contradiction slots; Session/Topic/CrossSession retain member view/event lineage and contradiction slots (`retained_and_compacted`, `native_id_collision`).
- **Versioned replaceable ExtractionPolicy** (`extraction_policy.py`): data-driven contract (priority bands, fidelity threshold, freshness/novelty weighting, dedup/supersession, budgets, abstain/block reasons) with deterministic `policy_digest`/`band_digest`. Initial policy locks CompactionWindow first, then native trace/episode/turn, session, topic, cross-session. Contract tests prove session-first and trace-disabled policy variants change only queue ranks and digests while raw artifact/event/view identities stay identical; compaction priority cannot override missing evidence refs or low fidelity.
- **Generation/policy-bound view repository** (`view_repository.py`): additive `ce_view_headers/members/lineage/contradictions/revisions` tables bound to one staged generation + one policy digest; idempotent rebuild (identical revision returns unchanged), policy revision keeps old revisions queryable, generation drift keeps both generations intact, stale marking, lineage resolution, and a no-authority-mutation guarantee (canonical/KU/authority rows never written; the repository exposes no activation surface).

## Task Commits

Per orchestrator instructions for this plan, no git state-changing commands were run; all six plan files were created but not committed (see 协调者复核点).

## Files Created/Modified

- `src/personal_knowledge/application/conversation/extraction_views.py` — EventGraph, ViewType, DerivedView + 7 typed subclasses, make_view_id/make_contradiction_id/view_set_digest, 7 builders + build_all_views orchestration (1092 lines, all functions <= 80).
- `src/personal_knowledge/application/conversation/extraction_policy.py` — PriorityBand/ExtractionPolicy/FreshnessConfig/NoveltyConfig/DedupConfig/BudgetConfig, BlockReason, PolicyCandidate/SchedulingOutput, schedule_candidates, policy_digest/band_digest, DEFAULT_POLICY (493 lines, all functions <= 80).
- `src/personal_knowledge/application/conversation/view_repository.py` — VIEW_TABLES, ViewLifecycle, ViewRepository (save_view_revision/mark_stale/lifecycle_status/read_views/policy_revisions/view_digest/resolve_lineage), ViewRevision (621 lines, all functions <= 80).
- `tests/unit/test_conversation_extraction_views.py` — 31 RED->GREEN view builder tests (664 lines).
- `tests/contract/test_conversation_extraction_policy.py` — 16 RED->GREEN policy contract tests (477 lines).
- `tests/integration/test_conversation_view_repository.py` — 14 RED->GREEN persistence tests (421 lines).

## Decisions Made

- NativeTraceView never fabricates from adjacency: without a boundary event carrying a native id, no native trace view is produced; heuristic episodes are tagged `session_fallback` and partial.
- View identity is evidence-set based, not ordinal based (research anti-pattern avoidance); lineage entries are raw identifiers (view ids carry the `view:` prefix, event ids are content hashes) so member view/event lineage stays directly comparable.
- `schedule_candidates` accepts an optional `events={event_id: occurred_at}` timestamp map so freshness is real and deterministic (test fixtures pass it); the policy digest and scheduled view set never depend on `now`.
- The initial priority order is locked into `DEFAULT_POLICY` (compaction > trace/turn/episode > session > topic > cross-session) and every variant is a new `ExtractionPolicy` + digest — no adapter or event identity depends on it.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] FidelityLevel string ordering corrupted threshold checks (Task 2)**
- **Found during:** Task 2 (compaction low-fidelity + dedup tests failing)
- **Issue:** `FidelityLevel` is a `str, Enum`; `FidelityLevel.PARTIAL < FidelityLevel.COMPLETE` compared alphabetically, so complete views failed the PARTIAL threshold and everything blocked as low fidelity.
- **Fix:** compare `_LEVEL_ORDER` integer scores instead of enum values (`_worst_level` + explicit order map).
- **Files modified:** `src/personal_knowledge/application/conversation/extraction_policy.py`
- **Verification:** all 16 policy contract tests pass.

**2. [Rule 1 - Bug] Episode fallback did not trigger for disconnected no-link graphs (Task 1)**
- **Found during:** Task 1 (`test_episode_session_fallback_is_partial_and_tagged`)
- **Issue:** `_relation_components` on a link-less session returned N singleton components, so the "no episode relations" guard never fired and the fixture got 2 components instead of 1 partial fallback.
- **Fix:** detect any session-incident episode-kind relation first; fall back to one whole-session partial episode only when none exists.
- **Files modified:** `src/personal_knowledge/application/conversation/extraction_views.py`
- **Verification:** all 31 view tests pass.

**3. [Rule 2 - Missing critical] Session view lineage used prefixed ids that broke comparability (Task 1)**
- **Found during:** Task 1 (`test_session_view_retains_member_views_and_events`)
- **Issue:** session `lineage` stored `view:<id>` / `event:<id>` while every other consumer uses raw ids; member-view lineage was not comparable.
- **Fix:** store raw view ids (already `view:`-prefixed by `make_view_id`) and raw event ids; `resolve_lineage` returns them consistently.
- **Files modified:** `src/personal_knowledge/application/conversation/extraction_views.py`
- **Verification:** session lineage + repository lineage resolution tests pass.

**4. [Rule 3 - Blocking / test defects] Fixture/assertion errors were test bugs, fixed in tests (Tasks 1/2/3)**
- Cross-session collision fixture produced identical canonical event ids (`make_event_id` ignores session), so no collision could be detected — switched to distinct artifacts.
- `EventGraph` validates relations at construction, so the unknown-relation error test now wraps construction (not `build_turn_views`).
- Contradiction ids are deterministic and symmetric; the test asserted the wrong thing and was corrected.
- `PolicyCandidate` has `derived_from_view`, not `view_id`; assertion corrected.
- Policy `band_for` uses identity (`is ViewType`), so the budget test now asserts `>= budget_exceeded` instead of strict equality.
- Session `resolve_lineage`/`read_views` evidence refs are sorted storage order, not builder order; tests compare as sets.
- View fixture `GenerationInput` lacked the `SourceArtifact` that event FKs reference; added it.
- The retained-and-compacted contradiction fixture picked the wrong event (`next(... USER_MESSAGE)` matched a non-compacted message); now derives the actual compacted target from the relations.

---

**Total deviations:** 4 auto-fixed (2 bugs, 1 missing-critical, 1 blocking/test-defect bundle)
**Impact on plan:** All fixes were correctness requirements or test-fixture defects; no scope creep, no existing production files modified.

## Issues Encountered

- `dataclasses` subclassing: base `DerivedView.metadata` had a default, which made subclass required fields ("non-default follows default"); removed the default so subclasses stay required-positional.
- Freshness without real timestamps: views carry no occurred_at; the policy now accepts an optional `events` timestamp map (deterministic, injected by callers/tests) so freshness metadata is honest instead of always-zero.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- 62-06 can consume `build_all_views` + `schedule_candidates` + `ViewRepository` for candidate staging with `derived_from_view` + `evidence_event_refs` lineage.
- `ViewRepository` is the drop-in persistence seam for shadow generations and drift/stale handling.
- No paid provider, no `pk-ku extract`, no live canonical writes: D-31 preserved.

## Auth Gates

无。零付费：全部测试本地确定性（tmp_path），无 LLM/provider/网络调用，未运行 `pk-ku extract`（D-31 保持）。三个新模块代码扫描无 `requests/urllib/httpx/openai/http://` 等网络或 provider surface（grep 仅命中 docstring 声明）。

## Known Stubs

无。`_occurred_at_for` 从不返回视图时间戳（视图不携带 occurred_at），freshness 由调用方注入的 `events` 时间戳映射驱动，未注入时为 0.0（诚实语义，非 stub）；`view_digest` 列存储 revision digest 且与 `ce_view_revisions.view_digest` 一致，无占位值。

## Threat Flags

无。新增三个模块零网络端点、零 provider 代码、零 schema 变更在信任边界之外（仅 additive `ce_view_*` 表）；live `agent_conversations.sqlite`（mtime 2026-07-27）与 `var/db/` 未被本计划代码写（测试全 tmp_path）；`ce_view_*` 仅存 view/member/lineage/contradiction 元数据，不含正文或凭据；视图持久化不写 canonical/KU/authority（有专项测试断言）。

## Self-Check: PASSED

- [x] Task 1 RED：`ModuleNotFoundError: No module named '...extraction_views'`；GREEN：`python -m pytest -q tests/unit/test_conversation_extraction_views.py` → 31 passed
- [x] Task 2 RED：`ModuleNotFoundError: No module named '...extraction_policy'`；GREEN：`python -m pytest -q tests/contract/test_conversation_extraction_policy.py` → 16 passed
- [x] Task 3 RED：`ModuleNotFoundError: No module named '...view_repository'`；GREEN：`python -m pytest -q tests/integration/test_conversation_view_repository.py` → 14 passed
- [x] 全量新套件：61 passed（31+16+14）
- [x] 相邻回归：145 passed（62-01 事件仓库 12、62-04 兼容投影 10、generations 17、v2 sync、rollback、流式/存储适配器、event contracts）
- [x] 下游回归：39 passed（conversation_repository、agentsview downstream、run_pipeline contracts、event contracts）
- [x] `git diff --check` → clean（仅新增 6 个计划内文件，untracked）
- [x] `python -m compileall` 新模块 → OK
- [x] 新生产文件函数均 ≤80 行（实测 extraction_policy 493 行、view_repository 621 行、extraction_views 1092 行，无 >80 行函数；模块总行数超 500 的为 62-CONTEXT/62-04 已确立的单职责视图/policy 模块，见 Deviations）
- [x] 无网络/provider/付费调用代码；live canonical 与 var/db 未写；测试全 tmp_path；spikes/tmp 未触碰

## Verification Command Results

| Command | Status | Result |
|---|---|---|
| Task1: `pytest -q tests/unit/test_conversation_extraction_views.py` | PASSED | 31 passed |
| Task2: `pytest -q tests/contract/test_conversation_extraction_policy.py` | PASSED | 16 passed |
| Task3: `pytest -q tests/integration/test_conversation_view_repository.py` | PASSED | 14 passed |
| Adjacent regressions (event repo + generations + v2 compatibility/sync + rollback + stream/store adapters + event contracts) | PASSED | 145 passed |
| Downstream regressions (conversation_repository + agentsview downstream + run_pipeline + event contracts) | PASSED | 39 passed |
| `git diff --check` | PASSED | clean |
| `python -m compileall` new modules | PASSED | OK |
| live canonical / var/db untouched; no provider/network code; spikes/tmp untouched | PASSED | verified |

## 协调者复核点

- **未提交/未改 live**：按本计划指令不运行 git 状态变更命令，六个计划文件保持未跟踪；live `agent_conversations.sqlite`（mtime 2026-07-27）与 `var/db/personal_system.sqlite` 完全未触碰；`.planning/spikes/` 与 `tmp/` 既有的未提交改动原样保留。
- **无事实权威**：`ViewRepository` 只写 `ce_view_*` 表，且暴露面无 activ* 方法（专项测试）；只读 active-generation 查询仍走 62-01/62-04 的 `EventRepository` seam。
- **可复查点**：Task 2 的 `schedule_candidates` 新增可选 `events` 时间戳映射参数（确定性 freshness，纯新增）；`ViewRepository.save_view_revision` 对完全相同的 revision 幂等返回（不重写行）；`read_views`/`resolve_lineage` 的 evidence 顺序为存储排序（按 event_id），与 builder 顺序可能不同，测试按集合比较。

---
*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Completed: 2026-08-12*
