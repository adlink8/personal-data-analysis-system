---
phase: 37-authority-aware-state-external-and-evidence
plan: 02
subsystem: ui
tags: [cockpit, react, claim-lifecycle, freshness, external-context, personal-state, overview, accessibility]

# Dependency graph
requires:
  - phase: 37-authority-aware-state-external-and-evidence
    provides: "37-01's canonical PersonalAssertionSchema（current_value_checksum）/ExternalFactSchema（fact_checksum、source_ids、服务端派生 freshness）、evidence_resolve.get 契约与 36-03 的 envelope()/CLOSED_CONFIRMATION_STATES 先例 — 本计划只渲染这些已锁定字段，不新增或重新推导服务端字段"
provides:
  - "components/authority/ClaimLifecycleBadges.tsx：ClaimKindBadge/LifecycleBadge/ConfirmationStateBadge 三个可复用组件，分别覆盖 claim/object kind、record lifecycle（Personal+External 记录状态并集）、decision confirmation_state 三条独立轴线；闭集之外字符串一律原样展示，不静默丢弃；HISTORICAL_LIFECYCLE_STATUSES 是展示分组而非伪造的 lifecycle 值"
  - "FreshnessBadge 改为只呈现服务端派生的 level/reason（与 external fact.freshness 同词表 unknown/valid/expiring_soon/expired），移除浏览器 <24h/<7d 阈值计算；无 level 时诚实回退为「未分级」"
  - "StatePanel 新增 offline/stale/conflict 三态（共 7 态），与 partial/error 明确区分；offline 用于 network_error 全局不可达场景（role=alert）"
  - "OverviewPage：Now Stack/决策队列改用共享 ConfirmationStateBadge；变化卡片改用 LifecycleBadge；isError 按 ApiError.code 区分 offline/error"
  - "PersonalStatePage：断言卡/近期变化/生命周期摘要条改用共享组件；新增 assertionReadinessNote 对 conflict/stale/expired/无证据断言显式说明暂不能作为决策确认依据"
  - "ExternalContextPage：事实卡直接消费 fact.lifecycle/fact.freshness；缺失 lifecycle/freshness/来源标识/事实校验和时显式标为 partial；updated=[] 显式陈述为 authority limitation 而非「无更新」"
affects: [37-03-evidence-surface-and-widget-containment, 38-guarded-project-decision-workspace]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "claim kind（Fact/Observation/Inference/Recommendation/Confirmation）、record lifecycle（current/stale/conflict/resolved/expired/superseded/invalid/unknown/uncertain/future）、decision confirmation_state 三条轴统一收敛到 components/authority/ClaimLifecycleBadges.tsx，页面不得再各自维护重复的 XXX_META 映射表"
    - "FreshnessBadge 的 level/reason 只接受服务端已计算好的值；调用方省略 level 时组件回退为 unknown/「未分级」，绝不用 Date.now() 与本地阈值重新推断——任何未来新增的服务端 freshness 字段应直接透传给这个 props，而不是在页面内再写一次年龄判断"
    - "isError 分支统一按 ApiError.code === 'network_error' 选择 StatePanel variant='offline'，其余错误一律 variant='error'；三页面（Overview/PersonalState/External）保持同一判定，不各自发明新的错误分类"
    - "必需字段缺失（External fact 的 lifecycle/freshness/来源标识/事实校验和）在卡片内显式渲染为 partial 提示，而不是复用可选字段的『未提供』占位——两者视觉与文案都不同，避免 producer/consumer 字段漂移被掩盖"

key-files:
  created:
    - apps/personal_decision_cockpit/src/components/authority/ClaimLifecycleBadges.tsx
    - apps/personal_decision_cockpit/src/test/ClaimLifecycleBadges.test.tsx
    - apps/personal_decision_cockpit/src/test/OverviewPage.test.tsx
  modified:
    - apps/personal_decision_cockpit/src/components/authority/AuthorityBadge.tsx
    - apps/personal_decision_cockpit/src/components/feedback/FreshnessBadge.tsx
    - apps/personal_decision_cockpit/src/components/feedback/StatePanel.tsx
    - apps/personal_decision_cockpit/src/test/StatePanel.test.tsx
    - apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx
    - apps/personal_decision_cockpit/src/pages/state/PersonalStatePage.tsx
    - apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx
    - apps/personal_decision_cockpit/src/test/ExternalContextPage.test.tsx

key-decisions:
  - "AuthorityBadge/SnapshotChip 两个文件虽在计划 files_modified 内，但只有 AuthorityBadge 需要真正修改（补齐此前缺失的图标，满足『颜色不能是唯一提示』规则）；SnapshotChip 本身已经是纯中性边框展示（不依赖颜色传达真假语义），复核后判定无需改动，未产生 diff，未提交——与 36-03 对 client.ts 的处理先例一致（无需改动就不强行改动）。"
  - "test/mockData.ts 同样在三个任务的 files_modified 内，但既有 fixture（PERSONAL_STATE_ENVELOPE 的冲突/偏旧断言、EXTERNAL_DELTA_ENVELOPE 的 f1 完整/f2 缺 lifecycle+freshness/f3 冲突+expiring_soon、OVERVIEW_ENVELOPE 的 proposed 决策项）已经覆盖本计划新增测试所需的全部场景，未做改动，未提交。"
  - "Forecast/Recommendation/Confirmation 三个 claim kind 在 personal_state.get 的真实数据中从不出现（provenance_class 闭集仅 fact/observation/inference）；ClaimKindBadge 仍定义了 recommendation/confirmation 两个变体供 Overview 的决策侧数据复用（决策项本质是 Recommendation Candidate，其 confirmation_state 即 Confirmation 轴），但不in personal_state 侧强行伪造一个从不存在的 Forecast claim kind——到期/horizon 改用一个内联的琥珀色时钟徽标呼应 Forecast 的视觉语言，而不是新增一个没有权威支撑的 claim 类型。"
  - "StatePanel 新增的 stale/conflict 两态目前只有组件级测试覆盖（ClaimLifecycleBadges 测试之外的 StatePanel.test.tsx 新增用例），三个页面目前没有触发条件天然对应『整节数据偏旧』或『整节存在冲突』的整段展示场景（冲突/偏旧信息已经在断言卡/事实卡逐条展示，粒度更细更准确）；offline 态则在三页面 isError 分支都有真实接线（network_error 触发）。这不是遗漏——组件已就绪、测试已锁定行为，未来若某个 Authority 需要整节 stale/conflict 展示可以直接复用，不需要再扩展 StatePanel。"

patterns-established:
  - "任何新增的 claim/lifecycle/confirmation 展示需求，先查 components/authority/ClaimLifecycleBadges.tsx 是否已有对应轴的 Badge/meta 函数，而不是在页面内新建一份局部映射表。"
  - "FreshnessBadge 的调用方必须显式想清楚『这个时间戳有没有配套的服务端 level』——没有就只传 asOf（诚实展示为『未分级』），不得为了『看起来更有信息量』而自行编造 level。"

requirements-completed: [STATE-01, STATE-02, STATE-03]

# Metrics
duration: ~2h
completed: 2026-07-26
---

# Phase 37 Plan 02: Authority-aware State, External and Evidence — Render Authority-aware State and External Summary

**把 Phase 37 Plan 01 锁定的 Projection 读模型（含 canonical External DTO 与断言 checksum）渲染成可日常理解的 Cockpit 界面：新增跨页面复用的 claim/lifecycle/confirmation 语义组件，FreshnessBadge 改为纯服务端派生展示，StatePanel 扩展 offline/stale/conflict 三态，Overview、Personal State、External 三页面在此基础上分别补齐真值分组、决策确认可用性提示与 External 必需字段缺失的 partial 标注。**

## Performance

- **Duration:** ~2h（含中途两次宿主进程中断后的状态核验与续作）
- **Tasks:** 3
- **Files modified:** 11（3 新建：ClaimLifecycleBadges.tsx、ClaimLifecycleBadges.test.tsx、OverviewPage.test.tsx；8 修改）

## Accomplishments

- 新建 `components/authority/ClaimLifecycleBadges.tsx`：`ClaimKindBadge`（fact/observation/inference/recommendation/confirmation）、`LifecycleBadge`（Personal 的 current/stale/conflict/resolved/expired 与 External 的 superseded/invalid 并集，外加 state_projection 偶发的 unknown/uncertain/future 兜底）、`ConfirmationStateBadge`（proposed/accepted/rejected/deferred/revoked，闭集与 36-03 `_KNOWN_CONFIRMATION_STATES` 完全一致）。三条轴独立可识别，闭集之外的字符串原样展示而非丢弃，`HISTORICAL_LIFECYCLE_STATUSES` 明确标注为展示分组而非伪造的第三种 lifecycle 值。
- `FreshnessBadge` 重写：不再用 `Date.now()` 与 `<24h/<7d` 阈值本地推断新鲜度，改为只接受服务端给出的 `level`（`unknown/valid/expiring_soon/expired`，与 37-01 的 `fact.freshness.level` 同词表）与 `reason`；调用方未提供 level 时诚实回退为「未分级」而不是编造判断。`AuthorityBadge` 补齐此前缺失的图标（此前只有颜色+文字，违反『颜色不能是唯一提示』规则）。`StatePanel` 从 4 态扩展到 7 态，新增 `offline`（整个同源 API 不可达，role=alert）、`stale`（记录/快照偏旧，展示更新时间+重新同步入口）、`conflict`（陈述冲突不自动选边）。
- `OverviewPage`：Now Stack 与决策队列卡片改用 `ConfirmationStateBadge` 展示 `confirmation_state`（图标+文字，取代纯文字或纯色 pill）；变化与风险卡片改用 `LifecycleBadge`；到期信息新增琥珀色时钟徽标呼应 spec 的 Forecast 视觉语言；`isError` 分支按 `ApiError.code === 'network_error'` 区分 `offline`/`error` 两种独立可见状态；本地 `CLOSED_CONFIRMATION_STATES` 改为复用共享模块的同名闭集，消除跨文件重复定义。
- `PersonalStatePage`：断言卡改用共享 `ClaimKindBadge`/`LifecycleBadge`，移除页面本地重复的 `CLAIM_META`/`STATUS_META`；新增 `assertionReadinessNote`，对 `conflict`/`stale`/`expired`/`evidence_count===0` 的断言显式说明「暂不能作为决策确认依据」及处理方向（只陈述已有权威字段，不新增裁决逻辑，不提供 prepare/confirm 控件，遵循 D-37-04）；`isError` 同样接入 offline/error 区分。
- `ExternalContextPage`：事实卡直接渲染 `fact.lifecycle`（`LifecycleBadge`）与 `fact.freshness.level/reason`（`FreshnessBadge`），不再用 `valid_from` 做本地新鲜度推断；新增 `missingRequiredFactFields` 检测 lifecycle/freshness/来源标识/事实校验和缺失，缺失时卡片显式标注为 partial（而非与可选字段共用的『未提供』占位）；Delta「更新」分组 `updated=[]` 时不再显示「无」，改为显式陈述「External 权威未提供逐事实更新事件」的 limitation。
- 新增 `ClaimLifecycleBadges.test.tsx`（27 用例）、`OverviewPage.test.tsx`（7 用例，appSmoke.test.tsx 未覆盖的 claim/lifecycle 视觉语义与单一 Authority 降级回归）；`StatePanel.test.tsx`（+3 用例覆盖 offline/stale/conflict）、`ExternalContextPage.test.tsx`（+3 用例覆盖 lifecycle/freshness 渲染、必需字段 partial、offline 区分，原「更新组显示无」断言按新行为更新）。

## Task Commits

Each task was committed atomically:

1. **Task 1: 建立共享的 claim、lifecycle、authority 与服务端 freshness 视觉语义** - `dd9716e` (feat)
2. **Task 2: 更新 Overview 与 Personal State 的八领域真值展示** - `8105b6c` (feat)
3. **Task 3: 按独立 External authority 渲染来源、时效、冲突与显式限制** - `7f02d57` (feat)

**Plan metadata:** this SUMMARY commit (docs), to follow.

## Files Created/Modified

- `apps/personal_decision_cockpit/src/components/authority/ClaimLifecycleBadges.tsx`（新建）— claim kind / record lifecycle / decision confirmation 三条独立轴的共享语义组件
- `apps/personal_decision_cockpit/src/components/authority/AuthorityBadge.tsx` — 补齐图标（personal/external/analysis/pilot/calibration 各一枚），保留原有五色语义
- `apps/personal_decision_cockpit/src/components/feedback/FreshnessBadge.tsx` — 改为只呈现服务端 level/reason，移除本地时钟阈值判断
- `apps/personal_decision_cockpit/src/components/feedback/StatePanel.tsx` — 新增 offline/stale/conflict 三态
- `apps/personal_decision_cockpit/src/pages/overview/OverviewPage.tsx` — ConfirmationStateBadge/LifecycleBadge 接入、offline 区分、复用共享 CLOSED_CONFIRMATION_STATES
- `apps/personal_decision_cockpit/src/pages/state/PersonalStatePage.tsx` — 共享徽标接入、assertionReadinessNote、offline 区分
- `apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx` — 服务端 lifecycle/freshness 接入、必需字段 partial 标注、updated limitation、offline 区分
- `apps/personal_decision_cockpit/src/test/ClaimLifecycleBadges.test.tsx`（新建）、`src/test/OverviewPage.test.tsx`（新建）、`src/test/StatePanel.test.tsx`、`src/test/ExternalContextPage.test.tsx` — 对应回归测试

## Decisions Made

见 frontmatter `key-decisions`。摘要：SnapshotChip.tsx 与 test/mockData.ts 复核后判定本计划无需改动（现有实现/fixture 已满足要求），未产生 diff，未提交；Forecast/Recommendation/Confirmation 三个 claim kind 中只有 Recommendation/Confirmation 在 personal_state 侧真实存在对应场景，Forecast 用琥珀色时钟徽标呼应视觉语言而非伪造新 claim 类型；StatePanel 的 stale/conflict 两态目前是组件级就绪但页面级未触发（细粒度断言/事实卡已经承担了该职责），offline 态在三页面都有真实接线。

## Deviations from Plan

None — 三个任务均按计划 `files_modified` 范围执行；`AuthorityBadge.tsx`/`SnapshotChip.tsx`、`test/mockData.ts` 在计划范围内但被判定为无需改动的文件已在上方 key-decisions 中说明，未额外触碰计划外文件。

## Issues Encountered

- **执行过程中两次宿主进程中断**：均在核验 `git status --short`/`git diff --cached --stat` 确认暂存区与工作树内容完整、重新运行相关 Vitest 通过后继续/提交，未丢失或重复任何改动。三次任务提交前均执行了显式路径 `git add` 与提交前 `git status --short` 核对，未使用 `git add -A`/`git add .`。
- 未观测到 `test_all_projection_operations_are_physically_read_only`（Python 契约测试）相关的环境竞态问题——本计划未运行 Python 测试，因为三个任务的改动均为纯前端 TypeScript/React 文件，未触碰任何服务端文件、fixture 或契约测试；`git status --short` 全程确认服务端相关文件（`src/personal_knowledge/services/*.py`、`tests/contract/*.py`）未被读取、暂存或提交。
- 无其它非预期问题：三个任务的 `<verify>` 命令与计划级 `<verification>` 命令均一次或二次通过（第一次未通过均为测试断言需要按新实现调整，已在对应任务提交中一并修正）。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `components/authority/ClaimLifecycleBadges.tsx` 现在是 claim/lifecycle/confirmation 三条轴的唯一权威展示层，Phase 37 Plan 03（证据面/Widget 收口）与 Phase 38（受控决策工作区）新增页面如需展示这些轴，应直接复用该模块的 Badge/meta 函数，不应新建局部映射表。
- `FreshnessBadge` 的新签名（`level`/`reason`/`asOf`）已经准备好承接未来任何新增的服务端 freshness 字段（例如若 37-03 的证据面需要展示证据本身的新鲜度），无需再改造组件本身。
- `StatePanel` 的 `offline`/`stale`/`conflict` 三态已就绪且有测试覆盖，37-03 的证据抽屉与 MCP Widget 容器化如遇到「整段数据偏旧」或「整段存在冲突」场景可直接复用，不需要重新发明。
- `evidence_resolve.get`（37-01 已交付）仍未被本计划任何页面消费——`PersonalStatePage`/`ExternalContextPage` 目前只展示 metadata，尚未提供证据下钻入口；这是 37-03（"关闭证据面"）明确的下一步范围，不是本计划遗漏。
- **`.planning/ROADMAP.md`/`STATE.md` 进度更新推迟**：按共享工作树纪律，这两个文件已被另一会话的 `.planning` 重组改动占用（与 37-01 SUMMARY 记录的情况相同），本计划未在这两个文件中记录进度，也未提交它们；后续需要由协调方把 Phase 37 Plan 02 完成状态并入这两个文件。

---
*Phase: 37-authority-aware-state-external-and-evidence*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `apps/personal_decision_cockpit/src/components/authority/ClaimLifecycleBadges.tsx` 包含 `ClaimKindBadge`、`LifecycleBadge`、`ConfirmationStateBadge`、`HISTORICAL_LIFECYCLE_STATUSES`、`CLOSED_CONFIRMATION_STATES` —— 编辑与读回过程中确认。
- `git log --oneline dd9716e~1..7f02d57` 恰好 3 个 commit（`dd9716e`、`8105b6c`、`7f02d57`），经 `git status --short`/`git diff --cached --stat` 核对，每个 commit 只包含该任务范围内的文件。
- 计划级 `<verification>` 重新执行：`npm run test -- --run src/test/ClaimLifecycleBadges.test.tsx src/test/StatePanel.test.tsx src/test/OverviewPage.test.tsx src/test/PersonalStatePage.test.tsx src/test/ExternalContextPage.test.tsx` → 46 passed。
- 全量前端回归：`npm run test -- --run` → 178/178 passed（16 test files，较 37-01 完成时的 138 基线净增 40 个新测试）；`npm run build` → `tsc --noEmit` + `vite build` 均成功。
- `git status --short` 确认未提交任何 `.planning/ROADMAP.md`/`STATE.md`/`README.md`，也未触碰其它会话的未跟踪文件（`.planning/audits/`、`assets/evals/knowledge_units/eval_policy_v3-draft.yaml`、`tests/unit/test_extraction_salvage_parse.py`、`tools/migrations/*`、`src/personal_knowledge/application/knowledge/build_knowledge_units_prod.py`）。
