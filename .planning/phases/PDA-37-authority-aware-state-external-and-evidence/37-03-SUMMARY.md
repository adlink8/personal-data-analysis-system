---
phase: 37-authority-aware-state-external-and-evidence
plan: 03
subsystem: ui
tags: [cockpit, react, evidence-drawer, mcp-widget, sandbox, personal-state, external-context, decision-workspace]

# Dependency graph
requires:
  - phase: 37-authority-aware-state-external-and-evidence
    provides: "37-01's evidence_resolve.get 契约（六态词表 ok/mismatch/expired/abstain/not_found/authority_unavailable）、useEvidenceResolve hook 与 EvidenceReferenceInput 类型、canonical PersonalAssertionSchema（current_value_checksum）/ExternalFactSchema（fact_checksum）/RecommendationDetailSchema（recommendation_checksum + snapshot_id）；37-02's ClaimKindBadge/LifecycleBadge/ConfirmationStateBadge/FreshnessBadge/StatePanel 共享语义组件 — 本计划只消费这些已锁定契约与组件，不重新发明"
provides:
  - "components/evidence/EvidenceDrawer.tsx：唯一的通用只读证据下钻抽屉，复用 useEvidenceResolve，六态逐一区分渲染（含 authority_unavailable 的有界可恢复降级），键盘可操作（Esc/Tab 焦点圈/焦点还原），无任何写入控件"
  - "PersonalStatePage/ExternalContextPage/DecisionWorkspacePage 三处'查看证据'入口：分别用 personalAssertionReference/externalFactReference/decisionEvidenceReference 三个纯函数从卡片已持有字段组装稳定引用三元组，缺失任一字段返回 null 即不渲染入口（不构造伪 evidence）"
  - "components/evidence/WidgetDiagnosticCard.tsx：遗留 MCP Widget（Data Browser/Memory Graph/Relation Review）的诊断容器——固定 allowlist origin、最小 sandbox（仅 allow-scripts）、referrerPolicy=no-referrer、同源 system status + 受控超时判定不可用时渲染非空 recovery card"
  - "重写的 pages/evidence/EvidencePage.tsx：先声明 current-object Evidence Drawer 是权威只读路径，再把三个 Widget 收口进显式'诊断 / 历史集成'区域"
affects: [38-guarded-project-decision-workspace]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "任何新增的'查看证据'入口一律用一个纯函数（xxxReference）从渲染时已持有的字段组装 EvidenceReferenceInput，缺任一字段返回 null 而不是拼凑/回退到其它记录；组件只在 reference 非 null 时渲染入口——OverviewPage 因其 overview.get 的 top_items/decision.items 服务端从未暴露 checksum/snapshot 字段，被判定为'当前没有满足条件的对象'而非改动遗漏"
    - "EvidenceDrawer 只在持有具体 reference 时被挂载（父组件用 state 是否非 null 控制挂载/卸载，而非 open 布尔翻转），避免在未触发'查看证据'的既有测试（appSmoke/OverviewPage.test.tsx 等）里也需要 mock useEvidenceResolve"
    - "跨源遗留 iframe 容器统一走 WidgetDiagnosticCard：sandbox 只给 allow-scripts（不含 allow-same-origin/顶层导航/弹窗/下载/表单），referrerPolicy=no-referrer，URL 必须落在写死的 ALLOWED_WIDGET_ORIGIN 内；可用性判断三态（同源 system status 确认可达/确认不可达/未知)，只有'已确认不可达'才跳过 iframe 改渲染 recovery card，'未知'态仍尝试加载并叠加超时提示，不把未知误判为任何一个确定态"
key-files:
  created:
    - apps/personal_decision_cockpit/src/components/evidence/EvidenceDrawer.tsx
    - apps/personal_decision_cockpit/src/components/evidence/WidgetDiagnosticCard.tsx
    - apps/personal_decision_cockpit/src/test/EvidenceDrawer.test.tsx
    - apps/personal_decision_cockpit/src/test/EvidencePage.test.tsx
    - apps/personal_decision_cockpit/src/test/DecisionWorkspacePage.test.tsx
  modified:
    - apps/personal_decision_cockpit/src/pages/evidence/EvidencePage.tsx
    - apps/personal_decision_cockpit/src/pages/state/PersonalStatePage.tsx
    - apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx
    - apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx
    - apps/personal_decision_cockpit/src/components/icons.tsx
    - apps/personal_decision_cockpit/src/test/mockData.ts
    - apps/personal_decision_cockpit/src/test/PersonalStatePage.test.tsx
    - apps/personal_decision_cockpit/src/test/ExternalContextPage.test.tsx

key-decisions:
  - "OverviewPage.tsx 复核后判定无需改动：overview.get 的 _personal_section/_decision_section（ui_projection.py）从未向 top_items/decision.items 暴露 checksum 或 snapshot_id 字段（无论是否 passthrough），因此 Overview 上任何汇总项都无法组装出完整的 stable_id+snapshot_id+checksum 三元组；遵循计划'不为统计数或缺失 authority 构造伪 evidence'的强约束，未写永远不会触发的守卫代码，未产生 diff，未提交（与 37-01/37-02 对未改动文件的处理先例一致）"
  - "Decision 的证据入口只挂在 recommendation 本身（DecisionWorkspacePage 头部），不为 support[] 逐条建 personal_state 引用：SupportEntrySchema 没有暴露 assertion_kind/subject/domain/scope/predicate 状态键，无法满足 personal_state 分支要求的完整 state key，强行拼凑会违反'不构造伪 evidence'"
  - "EvidenceDrawer 采用挂载即视为打开的生命周期（无独立 open 布尔），由三个调用页面各自的 state（reference 是否非 null）控制挂载/卸载；相比复用 ConfirmDrawer 的 open 翻转模式，此设计让未触发'查看证据'交互的既有测试（appSmoke.test.tsx、OverviewPage.test.tsx 等）无需改动即可继续通过，因为组件树里根本不存在该 hook 调用"
  - "WidgetDiagnosticCard 的 sandbox 只给 allow-scripts（不含 allow-same-origin），这是刻意的功能降级：遗留 Widget 因此运行在与自身来源不同的不透明 origin 中，若其内部依赖同源 XHR 可能受限；接受该限制，因为 Phase 37 明确把这些 Widget 定位为受限诊断集成而非需要完整功能的当前权威"

patterns-established:
  - "任何新的证据下钻入口都必须调用 EvidenceDrawer（Task 1 交付），不得在页面内重新实现抽屉、六态渲染或 useEvidenceResolve 之外的读取路径"
  - "任何新的跨源 iframe 集成都应复用 WidgetDiagnosticCard 而不是裸写 <iframe>：allowlist 校验、最小 sandbox、referrerPolicy、非空降级卡与受控超时是这个组件的固定契约"

requirements-completed: [EVID-01]

# Metrics
duration: ~2h30min
completed: 2026-07-26
---

# Phase 37 Plan 03: Authority-aware State, External and Evidence — Evidence Surface and Widget Containment Summary

**把 Phase 37 Plan 01 锁定的 `evidence_resolve.get` 六态只读契约接成一个跨页面复用的 EvidenceDrawer，从 Personal State、External Context 与 Decision Workspace 三处对象卡片开出"查看证据"入口（缺失稳定引用三元组时不构造伪入口），并把遗留 MCP Widget 收口为显式的、受限的、非空降级的诊断/历史集成，使 Evidence Drawer 成为唯一的当前对象权威只读证据路径。**

## Performance

- **Duration:** ~2h30min
- **Tasks:** 3
- **Files modified:** 13（5 新建：EvidenceDrawer.tsx、WidgetDiagnosticCard.tsx、EvidenceDrawer.test.tsx、EvidencePage.test.tsx、DecisionWorkspacePage.test.tsx；8 修改）

## Accomplishments

- 新建 `components/evidence/EvidenceDrawer.tsx`：唯一的通用只读证据下钻抽屉，只依赖 Plan 37-01 的 `useEvidenceResolve`（GET-only，reference 不全不发起请求）。恒定回显调用方已提交的稳定引用（subject_type/stable_id/snapshot_id/checksum），六态（`ok`/`mismatch`/`expired`/`abstain`/`not_found`/`authority_unavailable`）逐一区分渲染不同的横幅文案、色调与 next_actions；`ok`/`abstain` 展示 authority、snapshot、checksum、freshness（服务端 `as_of`/`valid_from`，不做本地新鲜度推断）、claim/lifecycle/confirmation 徽标、关联证据/支撑证据列表与 uncertainty；`authority_unavailable` 明确框定为单 Authority 故障隔离而非页面级异常。键盘可操作：Esc 关闭、Tab 焦点圈、卸载后焦点还原（复用 `ConfirmDrawer` 已验证的模式）；组件采用"挂载即视为打开"的生命周期（父组件用 reference 是否非 null 控制挂载），无任何写入控件、sealed value、原始正文或 HMAC/confirmation material。
- `PersonalStatePage`：断言卡新增"查看证据"，由 `personalAssertionReference` 纯函数从 `current_assertion_id`+`current_value_checksum`+所属领域 `data.snapshot_id`+完整 `key` 组装引用，任一缺失返回 `null` 即不渲染入口。`ExternalContextPage`：事实卡新增"查看证据"（`externalFactReference`：`fact_id`+`fact_checksum`+`snapshot.snapshot_id`），Delta 四组与"全部事实"回退列表均已接线。`DecisionWorkspacePage`：头部新增只读"查看证据"（`decisionEvidenceReference`：`recommendation_id`+`snapshot_id`+`recommendation_checksum`），与既有"记录行动/结果"guarded 会话入口并列但互不干扰，不新增、替换或绕过任何 session/action/outcome/prepare/confirm/execute 流程或服务端 guard policy。
- `OverviewPage.tsx` 复核后判定无需改动：其 `overview.get` 的 `personal.top_items`/`decision.items` 服务端从未暴露 checksum/snapshot 字段，不存在可组装完整稳定引用三元组的对象；遵循"不为统计数或缺失 authority 构造伪 evidence"的强约束，未写入永远不会触发的守卫代码，未产生 diff，未提交。
- 新建 `components/evidence/WidgetDiagnosticCard.tsx`：Widget URL 只能来自写死的 `ALLOWED_WIDGET_ORIGIN`（`http://127.0.0.1:8789`）并做 allowlist 校验；iframe 使用最小 `sandbox="allow-scripts"`（不含 allow-same-origin/顶层导航/弹窗/下载/表单）与 `referrerPolicy="no-referrer"`，`title` 显式标注"诊断/历史集成，非当前 Personal State 权威"。可用性判定三态：同源 `system status`（`ports.mcp.up`）确认不可达时直接渲染非空 recovery card（状态说明 + 重试 + 新窗口诊断链接），不渲染必然失败的空白 iframe；system status 本身查询失败/未知时按"未知"处理，仍尝试加载并叠加受控超时（默认 4000ms）提示；iframe `onLoad` 只清除"尚未确认加载"提示，绝不产生任何"成功/已验证"文案，不被当作 authoritative success。
- 重写 `pages/evidence/EvidencePage.tsx`：页面先声明 current-object Evidence Drawer（Personal/External/决策工作区的"查看证据"）才是权威只读路径，再把 Data Browser、Memory Graph、Relation Review 三个 Widget 放入显式"诊断 / 历史集成"区域；Memory Graph 保留 D-37-05 的历史/非 SSOT 标注。
- 新增 `EvidenceDrawer.test.tsx`（12 用例，覆盖六态、传输层 offline/error 区分、隐私与写入控件缺席、焦点管理）、`EvidencePage.test.tsx`（6 用例，覆盖权威路径说明、sandbox/referrer 属性、MCP 可达/不可达/未知三态、Memory Graph 历史标注、受控超时）、`DecisionWorkspacePage.test.tsx`（4 用例，新建）；`PersonalStatePage.test.tsx`/`ExternalContextPage.test.tsx` 补充证据入口接线与稳定引用断言。

## Task Commits

Each task was committed atomically:

1. **Task 1: 实现通用只读 Evidence Drawer 与 stable-reference 调用链** - `8040c66` (feat)
2. **Task 2: 从状态、External 与决策工作区接入同一证据下钻** - `fee86ad` (feat)
3. **Task 3: 收口 Evidence 页面与跨源 MCP Widget 的诊断降级** - `79828b9` (feat)

**Plan metadata:** this SUMMARY commit (docs), to follow.

## Files Created/Modified

- `apps/personal_decision_cockpit/src/components/evidence/EvidenceDrawer.tsx`（新建）— 通用只读证据抽屉
- `apps/personal_decision_cockpit/src/components/evidence/WidgetDiagnosticCard.tsx`（新建）— 遗留 Widget 诊断容器
- `apps/personal_decision_cockpit/src/pages/evidence/EvidencePage.tsx` — 重写为"权威路径说明 + 诊断集成区域"
- `apps/personal_decision_cockpit/src/pages/state/PersonalStatePage.tsx` — 断言卡"查看证据"入口
- `apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx` — 事实卡"查看证据"入口
- `apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx` — 建议头部"查看证据"入口
- `apps/personal_decision_cockpit/src/components/icons.tsx` — 新增 `IconSearch`（证据入口图标）
- `apps/personal_decision_cockpit/src/test/mockData.ts` — `PersonalAssertion` 补齐 `current_value_checksum`（含一条有意缺失样例）
- `apps/personal_decision_cockpit/src/test/{EvidenceDrawer,EvidencePage,DecisionWorkspacePage}.test.tsx`（新建）、`{PersonalStatePage,ExternalContextPage}.test.tsx`（补充）

## Decisions Made

见 frontmatter `key-decisions`。摘要：OverviewPage.tsx 因服务端从未暴露对应 checksum/snapshot 字段而判定无需改动，未产生 diff；Decision 证据入口只挂在 recommendation 本身，不为 support[] 逐条伪造 personal_state 引用（缺 state key）；EvidenceDrawer 用"挂载即打开"生命周期避免未涉及证据交互的既有测试需要额外 mock；WidgetDiagnosticCard 的 sandbox 只给 allow-scripts 是刻意的功能降级，接受遗留 Widget 可能因此损失部分同源功能。

## Deviations from Plan

None — 三个任务均严格按计划 `files_modified` 范围执行。`icons.tsx`（新增 `IconSearch`）与 `test/mockData.ts`（补齐 checksum 字段）虽不在计划 `files_modified` 显式列表内，但属于 Task 2 范围内页面变更所需的最小支撑改动（新图标、测试夹具补字段），未涉及任何 UX/契约层面的额外设计决策，已在 Task 2 commit message 中如实记录；`OverviewPage.tsx` 在计划范围内但复核后判定无需改动，未产生 diff、未提交（同 37-01/37-02 先例）。

## Issues Encountered

- 无非预期问题。三个任务的 `<verify>` 命令与计划级 `<verification>` 均一次通过；`EvidenceDrawer.tsx` 首次实现时对 `EvidenceResult` 的可选数组字段（`uncertainty`/`evidence`/`rationale_codes`/`support`）访问未加防御性 `?? []`，在测试构造省略这些字段的裸对象时抛出 `Cannot read properties of undefined`——这与 37-01 记录的"canonical DTO 安全关键字段用 `.nullable()` 而非 `.nullish()`"教训一致（这里是数组默认值），已在同一任务提交前修复并补充覆盖用例。
- `.planning/ROADMAP.md`/`STATE.md` 按共享工作树纪律未在本计划中更新（这两个文件已被另一会话的 `.planning` 重组改动占用），需由协调方后续补记 Phase 37 完结状态。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 37 的读侧只读证据语义已全部收口：`evidence_resolve.get`（37-01）→ 渲染层语义组件（37-02）→ 通用 Evidence Drawer + 三处入口 + Widget 诊断降级（37-03）。EVID-01 的成功标准（用户可从 Personal/External/Decision 理解每个结论为何可信或为何不能行动；遗留 Widget 只辅助诊断，不越过 authority/snapshot/privacy 边界）已满足。
- Phase 38（受控决策工作区）应直接在 `DecisionWorkspacePage` 现有的"记录行动/结果"guarded 入口上叠加 readiness/truth gate，不需要改动本计划新增的"查看证据"只读路径；两者已验证互不干扰（`DecisionWorkspacePage.test.tsx` 显式回归了该点）。
- `EvidenceDrawer`/`WidgetDiagnosticCard` 均为可直接复用的共享组件：未来任何新对象类型的证据下钻应优先调用 `EvidenceDrawer`（传入符合 `EvidenceReferenceInput` 的稳定引用），任何新的跨源 iframe 集成应复用 `WidgetDiagnosticCard`，不应各自重新实现。
- **`.planning/ROADMAP.md`/`STATE.md` 进度更新推迟**：按共享工作树纪律，这两个文件已被另一会话的 `.planning` 重组改动占用，本计划未在这两个文件中记录进度，也未提交它们；后续需要由协调方把 Phase 37（含本 Plan 03，即 Phase 37 全部完成）状态并入这两个文件。

---
*Phase: 37-authority-aware-state-external-and-evidence*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `apps/personal_decision_cockpit/src/components/evidence/EvidenceDrawer.tsx` 包含 `EvidenceDrawer`、六态 `STATUS_META`、`ReferenceBlock`、`ResultDetail` —— 编辑与读回过程中确认。
- `apps/personal_decision_cockpit/src/components/evidence/WidgetDiagnosticCard.tsx` 包含 `ALLOWED_WIDGET_ORIGIN`、`sandbox="allow-scripts"`、`referrerPolicy="no-referrer"`、受控超时逻辑 —— 编辑与读回过程中确认。
- `git log --oneline 8040c66~1..79828b9` 恰好 3 个 commit（`8040c66`、`fee86ad`、`79828b9`），经 `git status --short`/`git diff --stat` 核对，每个 commit 只包含该任务范围内的文件（Task 2 额外包含已在 commit message 中记录的最小支撑改动 `icons.tsx`/`test/mockData.ts`）。
- 计划级 `<verification>` 重新执行：`npm run test -- --run src/test/EvidenceDrawer.test.tsx src/test/EvidencePage.test.tsx src/test/PersonalStatePage.test.tsx src/test/ExternalContextPage.test.tsx src/test/DecisionWorkspacePage.test.tsx` → 32 passed；`python -m pytest tests/contract/test_ui_projection_evidence.py -q` → 26 passed。
- 全量前端回归：`npm run test -- --run` → 203/203 passed（19 test files，较 37-02 完成时的 178 基线净增 25 个新测试）；`npm run build` → `tsc --noEmit` + `vite build` 均成功。
- `git diff --stat HEAD~3..HEAD` 确认全部改动均在 `apps/personal_decision_cockpit/` 内，未触碰任何 `src/personal_knowledge/services/*.py`、`tests/contract/*.py` 或其它服务端文件。
- `git status --short` 确认未提交任何 `.planning/ROADMAP.md`/`STATE.md`/`README.md`，也未触碰其它会话的未跟踪文件（`.planning/audits/`、`assets/evals/knowledge_units/eval_policy_v3-draft.yaml`、`tests/unit/test_extraction_salvage_parse.py`、`tools/migrations/*`、`src/personal_knowledge/application/knowledge/build_knowledge_units_prod.py`）。
