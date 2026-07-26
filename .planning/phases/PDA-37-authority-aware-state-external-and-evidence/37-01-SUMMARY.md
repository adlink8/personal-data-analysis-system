---
phase: 37-authority-aware-state-external-and-evidence
plan: 01
subsystem: api
tags: [cockpit, ui-projection, evidence, zod, external-context, snapshot-binding, checksum]

# Dependency graph
requires:
  - phase: 36-secure-projection-and-cockpit-baseline
    provides: "36-01's `_SAFE_ERRORS`/`_origin_policy`, 36-02's `_SAFE_FAILURE_CODES`/`_KNOWN_CONFIRMATION_STATES`-locked ui_projection.py envelope, 36-03's endpoint-bound Zod `envelope()` factory — this plan extends all three for new state/external/evidence operations rather than forking them"
provides:
  - "personal_state.get 每条断言新增 current_value_checksum(与既有 current_assertion_id + data.snapshot_id 构成 evidence.resolve 的稳定引用三元组)"
  - "external_delta.get 的 canonical External fact DTO:fact_checksum、source_ids(一次性只读 join 还原)、服务端派生 freshness(level/reason,独立于 lifecycle 记录状态轴)"
  - "CockpitProjectionService.evidence_resolve.get(REST:GET /ui/evidence/resolve,GET-only)——唯一只读证据下钻入口,三种 subject_type(personal_state/external_fact/decision)统一校验 stable_id/snapshot_id/checksum 后仅调度到既有 state.explain/external.explain/recommendations.get 三条只读路径"
  - "固定 status 词表 ok/mismatch/expired/abstain/not_found/authority_unavailable,单 authority 意外故障隔离为 partial(而非异常穿透/500),结构非法输入直接 400"
  - "前端 evidenceResolveEnvelopeSchema + useEvidenceResolve hook + 三个真实捕获 fixture(personal-state.json/external-delta.json 更新、evidence-resolve.json 新增)"
affects: [37-02-render-authority-aware-state-and-external, 37-03-evidence-surface-and-widget-containment, 38-guarded-project-decision-workspace]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "只读证据解析(evidence_resolve.get)是唯一允许浏览器下钻到 state.explain/external.explain/recommendations.get 的入口;调用方必须先持有由某次 Projection 响应给出的 stable_id+snapshot_id+checksum,服务端重新拉取当前记录后逐字段比对——不匹配即 mismatch/expired,绝不静默回退到最新记录"
    - "typed status 而非布尔 ok/error:mismatch(binding 不匹配)、expired(snapshot/run 绑定失效)、abstain(evidence 不满足可用性但仍返回可用元数据)、not_found(未知资源)、authority_unavailable(真实 authority 故障,隔离为 partial)五者互斥且可区分,遵循 D-36 的'单 authority 故障=partial,不是 500'先例"
    - "canonical DTO 的安全关键字段一律 Zod `.nullable()`(键恒在)而非 `.nullish()`(键可省略)+ `.passthrough()`——producer 漏发键会立即 fail closed,而不是被宽松 schema 悄悄吞掉(D-37-02 对 pitfall #7 的直接回应)"
    - "一次性只读聚合 join(External fact→source_id)沿用 36-02 的 `_outcome_counts`/`_action_states` 先例:mode=ro+query_only=ON 连接、单条 SQL 覆盖全部 fact_ids,不做 N+1 explain 调用"

key-files:
  created:
    - tests/contract/test_ui_projection_evidence.py
    - apps/personal_decision_cockpit/src/test/fixtures/evidence-resolve.json
  modified:
    - src/personal_knowledge/services/ui_projection.py
    - src/personal_knowledge/services/api_server.py
    - tests/contract/test_ui_projection_state_external.py
    - apps/personal_decision_cockpit/src/api/schemas.ts
    - apps/personal_decision_cockpit/src/api/hooks.ts
    - apps/personal_decision_cockpit/src/test/fixtures/personal-state.json
    - apps/personal_decision_cockpit/src/test/fixtures/external-delta.json
    - apps/personal_decision_cockpit/src/test/schemas.test.ts
    - apps/personal_decision_cockpit/src/test/liveContract.test.ts
    - apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx
    - apps/personal_decision_cockpit/src/test/mockData.ts

key-decisions:
  - "External fact 的 evidence.resolve 结果与 external_delta.get 保持同一隐私边界:不返回 facts.get 底层携带的 raw `value` 字段,即使 External 权威本身允许读取该值——一致性优先于'能读就都给'"
  - "Decision 的 evidence.resolve 直接复用 DecisionFeedbackService.recommendations_get 既有的全链 checksum 校验(payload/run/support 三层),非 recommendation_missing 的其余 DecisionServiceError(如 recommendation_checksum_mismatch)一律归为 authority_unavailable——代表底层链路完整性问题,与'调用方引用只是过期'语义不同,不得混为一谈"
  - "personal_state 分支对 run_missing/snapshot_missing/snapshot_not_validated 三个 IntelligenceServiceError code 统一归为 expired(而非 authority_unavailable):这三者都表示'当前 snapshot 语境已不可再被解释',呼应 36-02 对 run_missing 的既有'空状态非异常'先例,而不是把它当成一次意外故障"
  - "External fact 的 source identity 通过新增 `_external_fact_source_ids` 一次性 join(external_fact_support→external_observations)还原,而不是省略该字段——RESEARCH.md 明确把'source identity'列为 canonical DTO 必需字段之一"
  - "[deviation] ExternalContextPage.tsx 与 test/mockData.ts 做了计划外的最小适配:canonical DTO 移除 fact_type/observed_at/单值 source_id 后,该未在本计划 files_modified 内的页面会直接编译失败(tsc 报错)且其 RTL 测试断言的文案也会落空。为保证本计划自身要求的 `npm run build`/`npm run test` 通过,做了字段改名级别的最小修复(fact_type→predicate、source_id→source_ids[0]、去掉不再存在的 observed_at),未触碰任何 UX/布局/freshness 消费逻辑——这些仍留给 37-02"

patterns-established:
  - "任何新增 /ui/* 只读端点如果需要下钻到某个具体记录,应该复用 evidence_resolve.get 的三段式校验(stable_id/snapshot_id/checksum 结构校验→仅调度既有 explain/get→逐字段比对当前记录)模式,而不是各自发明新的资源标识/路径读取方式"
  - "Zod canonical DTO 新增安全关键字段时用 `.nullable()`(必须键)而不是 `.nullish()`(可选键),让 producer 端漏发字段在测试里 fail closed 而不是被 passthrough 悄悄吸收"

requirements-completed: [STATE-02, STATE-03, EVID-01]

# Metrics
duration: ~2h30min
completed: 2026-07-26
---

# Phase 37 Plan 01: Authority-aware State, External and Evidence — Read DTO/Resolver Contract Summary

**服务端新增快照绑定的只读证据解析入口 `evidence_resolve.get`(REST `GET /ui/evidence/resolve`)覆盖 personal_state/external_fact/decision 三类 stable 引用,同步补全 personal_state.get 的断言 checksum 与 external_delta.get 的 canonical External DTO(fact_checksum/source_ids/服务端派生 freshness),并把前端 Zod 契约、hooks 与三份真实捕获 fixture 全部对齐,收口 Phase 37 的读侧真值结算前置工作。**

## Performance

- **Duration:** ~2h30min
- **Tasks:** 3
- **Files modified:** 13 (2 created: `tests/contract/test_ui_projection_evidence.py`、`apps/personal_decision_cockpit/src/test/fixtures/evidence-resolve.json`；11 modified)

## Accomplishments

- `ui_projection.py` 的 `_personal_state_detail` 现在把 `state.current` 早已计算出的 `current_value_checksum` 透传到每条断言卡片,使 `current_assertion_id` + `data.snapshot_id` + `current_value_checksum` 构成 evidence.resolve 可验证的稳定引用三元组,不再只暴露前两者。
- `_external_delta_section` 重写为 canonical External fact DTO:新增 `fact_checksum`(来自 `facts.get` 既有的 `payload_checksum`)、`source_ids`(经新增的一次性只读 `_external_fact_source_ids` join 从 `external_fact_support`→`external_observations` 还原,复用 36-02 的 `_outcome_counts` 先例避免 N+1)、以及服务端派生的 `freshness`(`{level, reason}`,相对 `snapshot.activated_at` 计算,与 `lifecycle` 记录状态是独立轴,不合并成一个颜色字段)。
- 新增 `CockpitProjectionService.evidence_resolve.get` + REST 路由 `GET /ui/evidence/resolve`(无对应 POST 路由,零写入路径):三种 subject_type 统一先做结构校验(stable_id/snapshot_id/checksum,personal_state 另需完整 state key),再仅调度到 `IntelligenceService.state.explain`、`DecisionIntelligenceReadService.external.explain`、`DecisionFeedbackService.recommendations.get` 三条既有只读路径之一;返回固定 status 词表(`ok`/`mismatch`/`expired`/`abstain`/`not_found`/`authority_unavailable`),mismatch/expired 绝不回退到最新记录,单 authority 意外故障隔离为 `partial`(而非异常穿透或伪装成 mismatch)。
- External 分支与 `external_delta.get` 保持同一隐私边界(不返回底层 `facts.get` 携带的 raw `value`);Decision 分支复用既有全链 checksum 校验,非 `recommendation_missing` 的完整性错误统一归为 `authority_unavailable`。
- 前端 `schemas.ts` 新增 `evidenceResolveEnvelopeSchema`(遵循 36-03 建立的 `envelope(operation, dataSchema)` 工厂)、`hooks.ts` 新增只读 `useEvidenceResolve`(reference 不全时不发请求,GET-only 无可写 payload);`ExternalFactSchema` 改为 canonical 字段集(不再与 `fact_type`/`observed_at`/`source_id` 旧字段并存),安全关键字段从 `.nullish()` 改为 `.nullable()`(键恒在)以 fail closed。
- `personal-state.json`/`external-delta.json` 两份既有捕获 fixture 用真实服务端数据重新生成/补齐新字段;新增 `evidence-resolve.json`(真实 external_fact 成功路径捕获)。`schemas.test.ts`/`liveContract.test.ts` 新增 evidence_resolve 全 status 覆盖与 canonical 字段缺失即 fail closed 的回归。

## Task Commits

Each task was committed atomically:

1. **Task 1: 扩展 Projection 的权威元数据与 canonical External DTO** - `af7cc05` (feat)
2. **Task 2: 实现快照绑定的只读证据解析 Projection 与 REST 路由** - `ccf18c2` (feat)
3. **Task 3: 同步客户端 schema、hooks 与受控真实响应 fixtures** - `ccd47ff` (feat)

**Plan metadata:** this SUMMARY commit (docs), to follow.

## Files Created/Modified

- `src/personal_knowledge/services/ui_projection.py` — 断言 checksum 透传、canonical External fact DTO(`fact_checksum`/`source_ids`/`freshness`)+ `_external_fact_source_ids`/`_fact_freshness` 辅助函数、新增 `evidence_resolve.get` 操作与三个 `_resolve_*_evidence` 只读解析方法
- `src/personal_knowledge/services/api_server.py` — 新增 `GET /ui/evidence/resolve` 路由(GET-only,参数原样透传做结构校验)
- `tests/contract/test_ui_projection_state_external.py` — 断言/fact 新字段的形状与语义回归(checksum 与 state.explain 口径一致、freshness 服务端派生)
- `tests/contract/test_ui_projection_evidence.py`(新建) — 三种 subject_type 的成功/mismatch/expired/abstain/not_found/authority_unavailable 全覆盖、poisoned 异常不泄露、REST GET 通/POST 404、rest adapter 一致性、物理只读边界(权威库指纹 + 同模式只读连接拒绝写入)
- `apps/personal_decision_cockpit/src/api/schemas.ts` — `PersonalAssertionSchema` 加 `current_value_checksum`;`ExternalFactSchema` 重写为 canonical DTO;新增 `evidenceResolveEnvelopeSchema` 及相关类型
- `apps/personal_decision_cockpit/src/api/hooks.ts` — 新增 `useEvidenceResolve` + `EvidenceReferenceInput`
- `apps/personal_decision_cockpit/src/test/fixtures/{personal-state,external-delta}.json` — 用真实服务端数据重新捕获/补齐新字段；`evidence-resolve.json`(新建)— 真实 external_fact 成功路径捕获
- `apps/personal_decision_cockpit/src/test/schemas.test.ts` / `liveContract.test.ts` — evidence_resolve 全 status 回归、canonical 字段 fail-closed 回归、fixture 更新后的既有断言同步
- `apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx` / `src/test/mockData.ts` — [deviation，见下] 最小编译期适配

## Decisions Made

见 frontmatter `key-decisions`。摘要:External evidence.resolve 不返回 raw value(与 external_delta.get 同一隐私边界)；Decision 的非 `recommendation_missing` 完整性错误一律 `authority_unavailable`；personal_state 的 `run_missing`/`snapshot_missing`/`snapshot_not_validated` 统一归为 `expired`；新增一次性 join 还原 External fact 的 source identity（而非省略该 RESEARCH 明确要求的字段）。

## Deviations from Plan

**1. [Rule: 计划内文件改动导致计划外文件编译/测试失败] `ExternalContextPage.tsx` + `test/mockData.ts` 最小适配**

- **Found during:** Task 3 验证阶段（`npm run build`）
- **Issue:** `ExternalFactSchema` 从宽松 `fact_type`/`observed_at`/`source_id` 改为 canonical `subject`/`predicate`/`source_ids` 后，`ExternalContextPage.tsx`（不在本计划 `files_modified` 内，属于 37-02 范围）直接 `tsc` 报错（访问已不存在的字段），其配套的 `mockData.ts` 假数据与 `ExternalContextPage.test.tsx` 的文案断言也随之落空。
- **Fix:** 对 `ExternalContextPage.tsx` 做字段改名级别的最小适配（`fact.fact_type`→`fact.predicate`、`fact.source_id`→`fact.source_ids?.[0]`、去掉不再存在的 `fact.observed_at`，`FreshnessBadge` 暂时接入 `valid_from` 保持可编译），`mockData.ts` 的三条 fact 样例同步改名为 canonical 字段。未做任何 UX/布局改动，也未让页面消费新的服务端 `freshness`/证据下钻——这些仍是 37-02 的范围。
- **Files modified:** `apps/personal_decision_cockpit/src/pages/external/ExternalContextPage.tsx`, `apps/personal_decision_cockpit/src/test/mockData.ts`
- **Verification:** `npm run build` 从失败变为成功；`ExternalContextPage.test.tsx` 两个测试恢复通过；全量前端测试 138/138。
- **Committed in:** `ccd47ff`（Task 3 commit）

---

**Total deviations:** 1（计划外文件的最小编译期适配，非本计划范围的设计改动）。未触碰 `.planning/ROADMAP.md`/`STATE.md`/`README.md`，未 `git add -A`，每次提交前都用 `git status --short`/`git diff --stat` 核对暂存集合。

## Issues Encountered

- **`test_ui_projection.py::test_all_projection_operations_are_physically_read_only` 环境竞态（按约定豁免，非本计划回归）**：另一会话的 `pk-ku extract` 进程持续写 `var/db/personal_system.sqlite` 的 `knowledge_units`/`evidence`/`cache` 类表（本次验证实测仅 `knowledge_response_cache` 行数在两次读之间变化），导致该测试的全库指纹比较偶发失败。已用两次独立读取直接验证：唯一变化的表是 `knowledge_response_cache`，与本计划改动的 `decision_*`/`personal_state_*`/`external_*` 权威表无关，属于 `36-VERIFICATION.md` 记录过的既有环境竞态先例，不计入本计划的通过/失败判定；本计划自建的 `tests/contract/test_ui_projection_evidence.py::test_evidence_resolve_is_physically_read_only` 改用只锚定相关表的指纹（而非全库表名扫描）以避免同样的假阳性。
- 无其它非预期问题：三个任务的 `<verify>` 命令与计划级 `<verification>` 均一次通过（除上述已知竞态豁免项外）。

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- `evidence_resolve.get` / `GET /ui/evidence/resolve` 已经是唯一的只读证据下钻入口，37-03（"关闭证据面"）应直接复用这条契约（三种 subject_type + 固定 status 词表）构建 EvidenceDrawer，而不是各自发明新的资源读取方式。
- `PersonalAssertionSchema`/`ExternalFactSchema` 现为 canonical、fail-closed 的形状；37-02 渲染 `PersonalStatePage`/`ExternalContextPage` 时应直接消费这些字段（含新的 `current_value_checksum`/`fact_checksum`/`source_ids`/`freshness`），不需要再猜测字段名。
- `ExternalContextPage.tsx` 目前只做了保持可编译的最小改名适配，仍然：(a) 用本地 `FreshnessBadge`（浏览器时钟推断）而非服务端新增的 `fact.freshness.level/reason`；(b) 未消费 `evidence_resolve.get`。这两点是 37-02/37-03 明确待办，不是本计划遗漏。
- Phase 36 的物理只读边界（权威库指纹 + 同模式只读连接拒绝写入）、安全失败目录（`_SAFE_FAILURE_CODES`/`_SAFE_ERRORS`）、`_KNOWN_CONFIRMATION_STATES` 词表锁定均未被绕过；`evidence_resolve.get` 完全复用而非新建这些机制。
- **`.planning/ROADMAP.md`/`STATE.md` 进度更新推迟**：按共享工作树纪律，这两个文件已被另一会话的 `.planning` 重组改动占用（大量无关的 diff），本计划未在这两个文件中记录进度，也未提交它们；后续需要由协调方把 Phase 37 Plan 01 完成状态并入这两个文件，或在这些改动落定/重置后补记。

---
*Phase: 37-authority-aware-state-external-and-evidence*
*Completed: 2026-07-26*

## Self-Check: PASSED

- `src/personal_knowledge/services/ui_projection.py` 包含 `_evidence_resolve_get`、`_resolve_personal_state_evidence`、`_resolve_external_fact_evidence`、`_resolve_decision_evidence`、`_external_fact_source_ids`、`_fact_freshness` —— 编辑过程中读回确认。
- `git log --oneline af7cc05~1..ccd47ff` 恰好 3 个 commit（`af7cc05`、`ccf18c2`、`ccd47ff`），经 `git diff --stat`/`git status --short` 核对，每个 commit 只包含该任务 `files_modified` 范围内的文件（Task 3 额外包含已在 SUMMARY 中记录为 deviation 的两个文件）。
- 计划级 `<verification>` 重新执行：`python -m pytest tests/contract/test_ui_projection_state_external.py tests/contract/test_ui_projection_evidence.py -q` → 36 passed；`npm run test -- --run src/test/schemas.test.ts src/test/liveContract.test.ts` → 76 passed。
- 扩展回归：四个 `test_ui_projection*.py` + `test_cockpit_transport_security.py`（排除已知竞态的 1 项）→ 101 passed, 1 deselected；前端全量 `npm run test -- --run` → 138/138；`npm run build` → tsc --noEmit + vite build 均成功。
- `git status --short` 确认未提交任何 `.planning/ROADMAP.md`/`STATE.md`/`README.md`，也未触碰其它会话的未跟踪文件（`.planning/audits/`、`assets/evals/knowledge_units/eval_policy_v3-draft.yaml`、`tests/unit/test_extraction_salvage_parse.py`、`tools/migrations/*`）。
