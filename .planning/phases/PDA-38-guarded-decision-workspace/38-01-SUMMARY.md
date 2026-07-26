---
phase: 38-guarded-decision-workspace
plan: 01
subsystem: ui
tags: [cockpit, react, zod, decision-workspace, dec-01, fail-closed, orchestration-handoff]

# Dependency graph
requires:
  - phase: 36-secure-projection-and-cockpit-baseline
    provides: "z.literal-bound decision_cockpit_projection_v1 envelope factory (schemas.ts) that this plan extends for decision_workspace.get's RecommendationDetailSchema"
  - phase: 37-authority-aware-state-external-and-evidence
    provides: "EvidenceDrawer + decisionEvidenceReference already wired on DecisionWorkspacePage's header (37-03); this plan does not fork or modify that read-only evidence path"
provides:
  - "RecommendationDetailSchema 新增 target/expected_benefit/costs_constraints/assumptions/contraindications 五个字段，锚定真实 intelligence/decision/schema.py::Recommendation dataclass 命名（当前 recommendations.get 尚未透出，页面显式渲染'未提供'）"
  - "DecisionComparisonSection（决策比较 DEC-01）：在 DecisionWorkspacePage 显式列出问题/目标/硬约束与成本/风险预算/候选方案/不行动基线/机会成本/假设/反面证据/停止条件，缺字段显式'未提供'而非省略或用单一分数替代"
  - "DecisionCenterPage 卡片新增 Personal SnapshotChip，使 snapshot 绑定在列表页即持续可见"
  - "computeEntryGateReasons：只读工作区 → guarded 会话的 fail-closed 资格门，命中 workspace_partial/binding_missing/expired/closed_state/non_project_domain/evidence_insufficient 任一原因即隐藏'记录行动/结果'入口，替换为阻断说明 + 刷新恢复路径"
  - "mockData.ts 新增 7 个 decision_workspace fixture 变体（字段缺失现状 + 6 种资格门阻断场景）"
affects: [39-truthful-feedback-and-runtime, 40-browser-uat]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "DTO 字段補齐但真实端点尚未populate 时：锚定同一后端 dataclass 的真实字段名（而非发明新名），并在 schema.ts 顶部注释里显式记录'哪些字段当前恒为 undefined、为什么、一旦后端补齐无需再改 schema'——DEC-01 概念中没有任何真实字段可锚定的（goal/no_action_baseline/risk_budget 逐条建议维度/多候选比较/opportunity_cost/stop_conditions）不新增 schema 字段，只在 UI 层显式标注'未提供'+原因，避免 DTO 混入从未由服务端发出的虚构字段"
    - "fail-closed 资格门只读取服务端已给出的 envelope/recommendation 字段（partial/snapshot_id/expires_at/confirmation_state/domain/support），复用既有 expiryLevel()/CLOSED_CONFIRMATION_STATES 词表而不是发明新的本地风险判断；网关是纯函数（computeEntryGateReasons），UI 只做条件渲染，服务端 guard policy 仍是手工构造路由参数时的最终权威"

key-files:
  created: []
  modified:
    - apps/personal_decision_cockpit/src/api/schemas.ts
    - apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx
    - apps/personal_decision_cockpit/src/pages/decisions/DecisionCenterPage.tsx
    - apps/personal_decision_cockpit/src/test/DecisionWorkspacePage.test.tsx
    - apps/personal_decision_cockpit/src/test/mockData.ts

key-decisions:
  - "decision_workspace.get 的真实数据模型（intelligence/decision/service.py::_metadata()）目前只暴露单一 recommendation，且从未透出 goal/hard_constraints（作为独立字段）/risk_budget（逐条维度）/no_action_baseline/opportunity_cost/stop_conditions/多候选比较——这些概念不属于本计划 files_modified 范围内可修改的任何前端文件能填补的真实数据缺口（需要 Python 服务端改动，超出本计划授权范围）。按 37-03 先例（OverviewPage 因服务端未暴露 checksum 字段而判定无需改动）的同一原则：不臆造字段，UI 对这些概念显式渲染'未提供'并注明原因；只对确有真实 dataclass 字段名可锚定的 5 个字段（target/expected_benefit/costs_constraints/assumptions/contraindications）补齐 schema"
  - "风险预算（risk_budget）在 UI 层按 recommendation.domain==='project' 派生显示为 low：这不是臆造，而是引用系统级不变量（analysis/schema.py::ALLOWED_DOMAINS={project}、orchestration/generation.py 硬编码 risk_budget='low'）——每份文档都确认 project 域的受控会话严格且唯一固定为 low；非 project 域则显式'未提供'并说明原因"
  - "DECISION_WORKSPACE_ENVELOPE 基线 fixture 的 domain 从 'career' 改为 'project'、expires_at 从写死的过去日期改为 2099 年：前者是因为该 fixture 现在同时充当'DEC-01 完整比较'与'资格门合格样例'，两者都要求 project 域；后者是必要修复——原值是相对当时'现在'的过去日期，会随系统真实时钟推移使既有测试意外失败（在本计划执行当天，2026-07-27，该 fixture 事实上已经'过期'）"
  - "Task 2（DEC-01 比较 + SnapshotChip）与 Task 3（资格门）虽然计划文件列表大量重叠（都触碰 DecisionWorkspacePage.tsx 与其测试文件），仍作为两个独立、顺序应用、各自通过全量验证的提交完成——通过先实现类 2 变更提交、再叠加类 3 变更提交的方式，保证每个 commit 都是独立可回滚、真实反映单个任务范围的最小 diff，而不是把两个任务的 diff 揉在一次提交里"

patterns-established:
  - "任何新增的 DEC-01 风格'决策比较'字段渲染都应遵循 ComparisonField/ComparisonListField 的'value ?? 未提供'+可选 note 说明模式，而不是省略字段或用综合分数代替"
  - "任何新增的只读→受控会话资格门都应是纯函数（输入 envelope + 已验证的 recommendation 字段，输出阻断原因数组），UI 只做条件渲染；不得在网关函数内发起网络请求或修改除本地 state 外的任何状态"

requirements-completed: [DEC-01]

# Metrics
duration: ~2h40min
completed: 2026-07-27
---

# Phase 38 Plan 01: Guarded Decision Workspace — Workspace Truth and Entry Gate Summary

**Decision Workspace 现在显式比较 DEC-01 全部十项决策维度（问题/目标/硬约束与成本/风险预算/候选方案/不行动基线/机会成本/假设/反面证据/停止条件），对当前 Projection 尚未暴露的概念如实标注"未提供"而非臆造；partial/binding-missing/stale/closed-state/非-project-域/证据不足六种真值不足场景现在会隐藏"记录行动/结果"guarded 入口，替换为只读阻断说明与刷新恢复路径。**

## Performance

- **Duration:** ~2h40min
- **Tasks:** 3
- **Files modified:** 5（schemas.ts、DecisionWorkspacePage.tsx、DecisionCenterPage.tsx、DecisionWorkspacePage.test.tsx、mockData.ts — 与计划 `files_modified` 完全一致，无范围外改动）

## Accomplishments

- `schemas.ts`：`RecommendationDetailSchema` 新增 `target`/`expected_benefit`/`costs_constraints`/`assumptions`/`contraindications` 五个字段，逐一锚定后端真实 `intelligence/decision/schema.py::Recommendation`/`RecommendationDraft` dataclass 字段名（与本 schema 其余字段 subject/domain/scope/horizon/rationale_codes 同一来源）。深入追踪确认：当前 `recommendations.get`/`_metadata()` 投影器**尚未透出**这五个字段（真实响应恒缺失），已在 schema 顶部详细注释记录这一后端只读服务范围外的真实差距，不做静默假设。
- 新建 `DecisionComparisonSection`（"决策比较（DEC-01）"）：在工作区头部之后、既有三栏之前插入全宽比较区，逐项渲染决策问题/目标/硬约束与成本/风险预算/候选方案/不行动基线/机会成本/假设/反面证据/停止条件；风险预算按 `domain==='project'` 系统级不变量显式派生为 `low`，候选方案行同时呈现新增的 `target`/`expected_benefit`；对当前 Projection 真数据模型（单一 recommendation，无多候选比较字段）无法覆盖的概念，逐项显式"未提供"并注明原因，不用单一分数替代解释（D-38-01）。
- `DecisionCenterPage` 卡片新增 Personal `SnapshotChip`，使 D-38-02 要求的 snapshot 绑定持续可见延伸到列表页，不必进入工作区才能看到。
- 新建 `computeEntryGateReasons` fail-closed 资格门：只消费服务端已给出的 `envelope.partial`/`recommendation.snapshot_id`/`expires_at`（复用既有 `expiryLevel()`）/`confirmation_state`（复用 `CLOSED_CONFIRMATION_STATES` 与既有徽标词表一致）/`domain`/`support.length`，命中任一原因即视为不合格。不合格时"记录行动/结果"guarded 入口不渲染，替换为逐条列出阻断原因的只读说明 + "刷新后重试"（复用 `query.refetch`）+ "查看证据"恢复提示；合格时保留既有入口与 case_id 预填提示不变。资格门只做浏览器侧提前展示，服务端既有 guard policy（Phase 33/36/37）仍是手工构造路由参数时的最终权威（T-38-04：不重算风险、不修复 binding、不伪造 case reference）。
- `mockData.ts`：`DECISION_WORKSPACE_ENVELOPE` 补齐 DEC-01 完整样例（domain 改为 `project`，expires_at 改为远期日期修复时钟漂移隐患）；新增 `DECISION_WORKSPACE_FIELDS_MISSING/EXPIRED/CLOSED/NON_PROJECT/NO_EVIDENCE/UNBOUND/PARTIAL_ENVELOPE` 七个变体，每个只改动触发单一阻断原因所需的字段。
- `DecisionWorkspacePage.test.tsx` 新增 11 个测试：3 个 DEC-01 比较用例（完整样例列表/风险预算渲染、字段缺失现状的"未提供"回退计数、非 project 域说明）+ 8 个资格门用例（6 种阻断原因各一次、刷新按钮调用 `refetch`、合格样例入口保留）。

## Task Commits

Each task was committed atomically:

1. **Task 1: 把 Workspace DTO 收口为可解释的决策比较与真值状态** — `53df764` (feat)
2. **Task 2: 实现完整决策比较与持续可见的 authority/evidence 上下文** — `1db53e5` (feat)
3. **Task 3: 把只读工作区到会话的 handoff 约束为 fail-closed 资格门** — `27167bb` (feat)

**Plan metadata:** this SUMMARY commit (docs), to follow.

## Files Created/Modified

- `apps/personal_decision_cockpit/src/api/schemas.ts` — `RecommendationDetailSchema` 新增 5 个 DEC-01 相关字段 + 详细的"当前恒缺失"说明注释
- `apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx` — 新增 `DecisionComparisonSection`（DEC-01 比较）与 `computeEntryGateReasons`（fail-closed 资格门），改造 `WorkspaceBody` 的写入 CTA 为条件渲染
- `apps/personal_decision_cockpit/src/pages/decisions/DecisionCenterPage.tsx` — 卡片新增 Personal SnapshotChip
- `apps/personal_decision_cockpit/src/test/DecisionWorkspacePage.test.tsx` — 新增 DEC-01 比较（3）与资格门（8）共 11 个测试
- `apps/personal_decision_cockpit/src/test/mockData.ts` — DEC-01 完整样例补齐 + 7 个资格门/字段缺失 fixture 变体

## Decisions Made

见 frontmatter `key-decisions`。摘要：decision_workspace.get 真实数据模型没有 goal/hard_constraints（独立字段）/risk_budget（逐条维度）/no_action_baseline/opportunity_cost/stop_conditions/多候选比较的任何真实字段可锚定（这是后端只读服务的范围外缺口，本计划无 Python 改动授权），故这些概念在 UI 显式"未提供"而非发明 schema 字段；risk_budget 按 project 域系统级不变量派生显示为 low（非臆造，是对已发布系统约束的如实引用）；基线 fixture 的 domain/expires_at 做了必要修正（分别是"复用同一 fixture 覆盖两类场景"与"消除随时钟推移失败的隐患"）；Task 2/3 虽同文件重叠仍拆成两个顺序应用、各自独立验证的提交。

## Deviations from Plan

**1. [Scope-appropriate interpretation] DEC-01 的多个决策维度在真实后端数据模型中没有可锚定字段**

- **Found during:** Task 1，深入追溯 `decision_workspace.get` → `DecisionFeedbackService.recommendations_get` → `_metadata()` 的真实字段集合，以及 `intelligence/decision/schema.py`/`intelligence/pilot/schema.py`/`intelligence/analysis/schema.py` 三层 dataclass
- **Issue:** DEC-01 要求比较问题/目标/硬约束/风险预算/候选方案/不行动基线/成本/机会成本/假设/反面证据/停止条件/缺失信息/限制。深入追踪发现：当前 `decision_workspace.get` 的真实响应只包含单一 `recommendation` 对象，其字段集合（`_metadata()` 显式白名单）中，`goal`/`hard_constraints`（独立于 costs_constraints）/`risk_budget`（逐条建议维度）/`no_action_baseline`/`opportunity_cost`/`stop_conditions`/多候选比较**没有任何真实字段可映射**——这些概念只存在于尚未与本端点关联的 Pilot（`intelligence/pilot/schema.py::ProjectCase`）与 Analysis（`intelligence/analysis/schema.py::CandidateDraft`）权威中。补齐这一读侧的关联需要修改 `src/personal_knowledge/services/ui_projection.py` 或 `intelligence/decision/service.py`，均为 Python 文件，超出本计划 `files_modified`（仅限 5 个前端文件）授权范围。
- **Fix:** 只对确有真实同一 dataclass（`intelligence/decision/schema.py::Recommendation`）字段名可锚定的 5 个字段（`target`/`expected_benefit`/`costs_constraints`/`assumptions`/`contraindications`）补齐 `RecommendationDetailSchema`；DEC-01 中没有任何真实字段可锚定的概念在 `DecisionComparisonSection` 中显式渲染"未提供"+ 具体原因说明（例如"Projection 当前未暴露决策目标字段"），不发明虚构 schema 字段掩盖这一真实数据缺口。
- **Files modified:** `apps/personal_decision_cockpit/src/api/schemas.ts`（新增字段 + 详细注释）、`apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx`（`DecisionComparisonSection` 对应"未提供"分支）。
- **Verification:** `decisionSchemas.test.ts`（6/6）与 `DecisionWorkspacePage.test.tsx` 新增的字段缺失/非 project 域用例验证"未提供"分支渲染正确；`npm run build` 类型检查通过。
- **Committed in:** `53df764`（Task 1）、`1db53e5`（Task 2）。

**2. [Necessary fixture fix] 基线 fixture 的 domain 与 expires_at 需要修正才能同时满足 DEC-01 完整样例与资格门合格样例**

- **Found during:** Task 1，为 DEC-01 完整比较样例与 Task 3 资格门"合格样例"设计同一份基线 fixture 时
- **Issue:** 既有 `DECISION_WORKSPACE_ENVELOPE.data.recommendation.domain` 为 `'career'`（Phase 38 只开放 `project` 域的受控会话，`'career'` 会被新资格门判定为不合格）；`expires_at` 为写死的相对当时"现在"的过去日期（`2026-07-26T00:00:00Z`），会随系统真实时钟推移使既有测试与新资格门测试意外失败——本计划执行当天（2026-07-27）该日期事实上已经过期。
- **Fix:** `domain` 改为 `'project'`；`expires_at` 改为远期日期 `2099-01-01T00:00:00Z`（与 mockData.ts 中其它同类 fixture 惯例一致）。
- **Files modified:** `apps/personal_decision_cockpit/src/test/mockData.ts`。
- **Verification:** 既有 4 个 EVID-01 证据下钻测试（依赖同一 fixture）与新增的 DEC-01/资格门测试全部通过；全量前端回归 214/214。
- **Committed in:** `53df764`（Task 1）。

---

**Total deviations:** 2（1 处范围内的合理解释——不臆造后端未提供的字段；1 处必要的 fixture 修复，避免相对日期随时钟漂移失败）。均未偏离本计划 `files_modified` 范围，也未产生非计划授权的服务端改动。

## Issues Encountered

- 深入追溯发现 Decision Workspace 依赖的是 v1.2 时期的 `intelligence/decision`（`decision_recommendations`/`decision_runs` 表）而非 v1.3 Guarded Orchestration 的 `intelligence/pilot`/`intelligence/analysis`（`ProjectCase`/`CandidateDraft`）——两者是并行存在的两套决策记录体系，尚未在 `decision_workspace.get` 层面关联。DEC-01 规格（`.planning/research/v1.4-decision-cockpit-ui/UI-SPEC.md` §7.3）描述的"多候选（A/B/C/D/E）结构化比较表"属于后者尚未提供的能力；本计划严格在前端授权范围内如实呈现这一差距，未创建任何新的服务端关联或事实权威。这一发现建议记录给 Phase 39/未来 Phase 38 后续计划：若要真正关闭 DEC-01 的多候选/no_action_baseline/stop_conditions 缺口，需要一个明确的、Python 范围内的服务端计划（`ui_projection.py`/`intelligence/decision/service.py`），并交由后续的 gsd-plan-phase 排期。
- Task 2 与 Task 3 都改动 `DecisionWorkspacePage.tsx`/`DecisionWorkspacePage.test.tsx` 的同一函数区域（`WorkspaceBody` 头部渲染块）。为保持"一个任务一个原子提交"的执行纪律，采用了"先实现 Task 2 + Task 3 合并态 → 验证通过 → 临时回退 Task 3 部分 → 提交 Task 2 → 重新应用 Task 3 部分 → 再验证 → 提交 Task 3"的顺序化流程，确保每个 commit 都是独立、真实反映单任务范围的最小 diff，而不是回填一个人为分割的假 diff。
- 未触碰 `.planning/ROADMAP.md`/`STATE.md`/`apps/personal_decision_cockpit/README.md`（按共享工作树纪律，另一并行会话正在改动 `.planning/` 与 `docs/wiki/`），进度记录推迟给协调方；执行过程中 `git status --short` 在每次 commit 前确认过仅暂存本计划范围内的显式路径，未使用 `git add -A`/`git add .`。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 38 Plan 01（Workspace truth and entry gate）已完成：DEC-01 决策比较在浏览器中可验证（对无法从当前 Projection 满足的维度诚实标注"未提供"），Phase 37 truth gate（partial/stale/conflict/binding mismatch/证据不足）现在会真实阻断 Decision Workspace 到 guarded 会话的入口，不再是无条件可达。
- Plan 38-02（"Exact confirmation and linear session advance"，per `38-RESEARCH.md` 的三计划划分）可以在本计划的资格门之上继续推进 prepare/preview/confirm/replay 审计，不需要改动本计划新增的 `DecisionComparisonSection`/`computeEntryGateReasons`（两者都是纯只读/纯函数，未触碰任何 session/orchestration 状态）。
- **已知的后续缺口（建议排期而非本计划范围）：** DEC-01 的 goal/no_action_baseline/risk_budget（逐条建议维度）/opportunity_cost/stop_conditions/多候选比较目前在 `decision_workspace.get` 的真实数据模型中没有可读字段——需要一个专门的 Python 服务端计划（`ui_projection.py`/`intelligence/decision/service.py`，可能需要关联 Pilot `ProjectCase`/Analysis `CandidateDraft`）来真正补齐，而不是本计划能在前端授权范围内解决的问题。
- `.planning/ROADMAP.md`/`STATE.md` 进度更新推迟（同 36-03/37-03 先例）：这两个文件已被并行会话的 `.planning` 重组改动占用，本计划未在其中记录进度，也未提交它们。

---
*Phase: 38-guarded-decision-workspace*
*Completed: 2026-07-27*

## Self-Check: PASSED

- `apps/personal_decision_cockpit/src/api/schemas.ts` 包含 `target`/`expected_benefit`/`costs_constraints`/`assumptions`/`contraindications` 五个新字段及其"当前恒缺失"注释——编辑与读回过程中确认。
- `apps/personal_decision_cockpit/src/pages/decisions/DecisionWorkspacePage.tsx` 包含 `DecisionComparisonSection`、`computeEntryGateReasons`、`ENTRY_GATE_REASON_LABELS`、`CLOSED_CONFIRMATION_STATES`——编辑与读回过程中确认。
- `git log --oneline 53df764~1..27167bb` 恰好 3 个 commit（`53df764`、`1db53e5`、`27167bb`），经 `git status --short` 核对，每个 commit 只包含该任务范围内的文件。
- 计划级 `<verification>` 重新执行：`npm run test -- --run src/test/decisionSchemas.test.ts src/test/DecisionCenterPage.test.tsx src/test/DecisionWorkspacePage.test.tsx` → 23/23 passed。
- 全量前端回归：`npm run test -- --run` → 214/214 passed（19 test files，较计划执行前的 203 基线净增 11 个新测试）；`npm run build` → `tsc --noEmit` + `vite build` 均成功。
- `git status --short` 确认未提交任何 `.planning/ROADMAP.md`/`STATE.md`/`apps/personal_decision_cockpit/README.md`，也未触碰其它并行会话的 `docs/wiki/*.md`/`.planning/future-milestones/*` 改动。
