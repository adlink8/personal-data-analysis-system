# Personal Decision Cockpit（个人决策驾驶舱）

独立的个人决策智能前端。设计契约：`.planning/research/v1.4-decision-cockpit-ui/UI-SPEC.md`。

> **基线状态（2026-07-26）：** 只有 **Phase 36（Secure Projection and Cockpit
> Baseline）** 已完成计划执行与验证收口——同源 Origin/CORS 传输安全、
> Projection 安全错误信封与物理只读边界、前端 Zod DTO/vocabulary 契约锁定；
> 详见 [`../../.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md`](../../.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md)。
> **Phase 37–40（状态/证据、决策工作区、反馈与主动提醒、硬化与真实浏览器
> UAT）尚未逐阶段验证收口。** 下方功能范围、"验收清单"与"已完成"措辞描述的
> 是既有实现代码与目标产品契约（implementation candidate），**不代表对应
> Phase 已通过验收或 v1.4 已发布**；只有在各自 Phase 的计划执行、测试与
> `36-VERIFICATION.md` 同类证据记录完成后，才构成可审计基线的一部分。

## 本轮范围（Phase 36–39 等价）

- 应用壳：桌面侧栏（1024+）/ 平板横条（768–1023）/ 移动底部五栏（<768），全局顶栏（快照、新鲜度、系统状态点、主题/密度切换、新建决策入口）。
- 今日总览（`/ui/overview`）：Now Stack、目标与约束、变化与风险、待决策事项、主动提醒预览、外部环境摘要、新鲜度 Footer。任何一节为 null 时只降级该卡片，不整页白。
- 个人状态（`/ui/personal-state`，路由 `/state` 与 `/state/:domain`）：Personal Snapshot + 生命周期摘要条（current/stale/conflict/resolved/expired）、八领域网格（目标/约束/观察/状态计数、红色冲突标记、健康/财务/关系高风险域提示）、领域详情（事实/观察/推断分组 + "内容经隐私封存，仅展示元数据"）、近期变化时间线。
- 外部环境（`/ui/external/delta`，路由 `/external`）：External Snapshot 计数、"外部事实不会自动成为个人事实。"显著提示条、新增/更新/即将过期/冲突四组 Delta 事实卡（缺字段显式"未提供"）、来源 Allowlist 表格、地区/类型纯客户端筛选。
- 决策中心（`/ui/decision-queue`，路由 `/decisions`，Phase 38）：六组看板（需要关注/等待确认/执行中/等待结果/已完成/已关闭，每组标题含计数）、Decision Card（短码 ID + domain/kind/horizon/置信度 + confirmation_state/action_state 双状态徽标 + expires_at 临近/已过 amber 强调 + current_sequence）、空队列"当前没有待决策事项"+下一步引导。
- 决策工作区（`/ui/decision/workspace`，路由 `/decisions/:id`，Phase 38）：头部（recommendation_id、domain/scope、双状态、SnapshotChip、expires_at、"记录行动/结果"入口）、三栏（决策条件 / 方案与证据 support[] 证据引用行 + 关联分析 run / 建议与限制 + 缺失信息说明）、底部标签页（历史链上字段等宽渲染 / 结果 outcomes / 效果 effectiveness——`causal_claim==false` 时显著标注"非因果评估：结果不证明建议导致了结果"）。节级降级：某一 Authority 失败只降级该节。
- 行动与结果（`/ui/actions/recent` + `/ui/calibration/overview`，路由 `/actions`，Phase 39）：摘要条（total_available / shown / with_outcome / awaiting_outcome）；每条推荐一个六节点纵向 OutcomeTimeline（建议/决策/行动开始/行动完成/结果/效果评估，达成=绿色勾"已达成"、未达=灰点"未达成"，event_id 短码、sequence、checksum 短码等宽渲染，节点间竖向连线，点击 ID 可回决策工作区）；outcome 展开区（实际完成/耗时/成本/满意度/副作用等真实字段尽力渲染，缺失显"未提供"，固定提示"结果记录不自动证明建议导致了结果。"）；effectiveness 在 `causal_claim==false` 时显著标注"非因果评估"；底部 CalibrationPanel（protocol 卡：verdict/status/sample_size、INCONCLUSIVE 时展示 inconclusive_reasons 与"样本不足或协议偏离"说明、causal_claim==false 标注、summary_limitations）。单条组装失败（error）只降级该条。"记录结果"链到 `/sessions/new?intent=observe&from=/actions`，页面如实说明会话链严格线性、不能跳段，不做伪造跳段入口。
- 主动提醒（`/ui/proactive/summary`，路由 `/proactive`，Phase 39）：需要现在处理 / 可延后两组 ProactiveCard（领域 chips、candidate_id 短码、candidate_class/presentation_kind、importance 尽力解析 score/level、reason_codes 触发依据、valid_from~expires_at、current_control_eligible + current_control_reason_codes）；已抑制与冷却中 / 历史为诚实空态（该状态不列入 eligible inbox），提供 candidate_id 输入框调 `/proactive/controls/status` 逐条查看；查看证据调 `/proactive/candidate/explain` 展开 explanation/limitations；metrics 键值区（噪声预算等真实字段）+ notes 说明条。
- Guarded 写入（Phase 38，spec §5.3）：顶栏"新建决策"对话框（goal + constraints 动态行 + weights 键值 + 固定 domain=project/risk_budget=low 只读）→ prepare → ConfirmDrawer（操作名称 / exact preview JSON 只读折叠展开 / 将新增 Event 说明 / "不会执行的动作"固定提示 / preview_checksum / idempotency_key / 风险提示 / 具体文案确认按钮）→ confirm → OperationResult（sequence/event_id/checksum）→ 会话推进视图 `/sessions/:id`（DecisionStageStepper + 仅合法下一跳可点 + 每跳独立 preview/confirm；`intent=observe&from=/actions` 进入时显示"不能跳段"amber 说明并回链行动与结果页）。失败走 TypedRecoveryPanel（按 error.code 分类恢复说明，retryable 给"重试"），`replayed==true` 显示"已返回原事件，未重复写入"。写流程契约详见 [`docs/write-flow.md`](docs/write-flow.md)。
- 系统状态（`/ui/system/status`）：用户态区 + 默认折叠的开发者区域。
- 证据中心：嵌入 MCP 服务（8789）托管的三个 Widget。
- 全部八个主导航页面均为真实实现，占位页已清空（"更多"菜单中亦无占位）。

### Proactive 写入限制

REST 只暴露 `/agent/session/*` 与 `/search/*` 写路由，**没有 proactive 写路由**：Snooze / Suppress / 限定 Scope / Restore 在页面上为 disabled，title 与卡片内文案均注明"该写入由 MCP 工具或 pk CLI 提供，REST 未暴露"，不做假按钮或静默不可点。本轮不新增任何写入路径；所有写入仍只走 Guarded 显式确认会话流。

**Phase 40（硬化与 Live UAT）尚未执行**：无障碍/响应式硬化、真实浏览器 UAT 与下方"验收清单"逐项勾选均未发生——组件级 Vitest（`npm run test`）与 `npm run build` 通过不等同于 Phase 40 的真实浏览器验收；该阶段结果只能在 Phase 40 自己的 PLAN/SUMMARY/VERIFICATION 中如实记录。

## 技术栈

React 18 + TypeScript + Vite 6 + Tailwind CSS 3.4 + TanStack Query v5 + Zod 3 + react-router-dom 6；vitest + Testing Library。

## 开发

> 以下 `npm`/`node` 命令在 Windows PowerShell 中同样有效：从项目根
> `Set-Location apps\personal_decision_cockpit`（或直接在本目录）执行即可，无需切换 shell。

```powershell
npm install
npm run dev
```

- 前端起在 `http://127.0.0.1:5173/app/`。
- 需要 rag-api 运行在 `http://127.0.0.1:8000`（提供 `/ui/overview`、`/ui/system/status`、`/ui/personal-state`、`/ui/external/delta`、`/ui/decision-queue`、`/ui/decision/workspace`、`/ui/actions/recent`、`/ui/proactive/summary`、`/ui/calibration/overview` 投影，`/proactive/candidate/explain`、`/proactive/controls/status` 直读，与 `/agent/session/*` 写端点）；dev server 已把 `/ui`、`/intelligence`、`/decision`、`/proactive`、`/agent`、`/knowledge`、`/health`、`/stats` 代理过去。
- 证据中心的 Widget 需要 MCP 服务运行在 `http://127.0.0.1:8789`。

### 写入功能的服务端前提

- 会话写操作（prepare/confirm/preview/execute）需要 rag-api 环境设置
  **`PERSONAL_DATA_ORCHESTRATION_SECRET`（≥32 字节随机值）**；未配置时所有写操作返回
  `confirmation_secret_unavailable`（前端 TypedRecoveryPanel 会给出恢复说明），只读页面不受影响。
- stock rag-api **未注入 generation runner**：会话链的 generate 跳会返回
  `generation_provider_unavailable`；publish 及之后各跳不受影响，会话停在 confirmed 不中断。
- 写流程完整契约（transition 链、各步请求体、错误码分类、replay 语义）见
  [`docs/write-flow.md`](docs/write-flow.md)。

## 构建

```powershell
npm run build
```

产物在 `dist/`，由 rag-api 以静态文件托管在 `http://127.0.0.1:8000/app/`（`base: /app/`），生产不新增常驻前端进程。

## 测试

```powershell
npm run test
```

包含：投影信封 Zod 契约测试（overview / system.status / personal-state / external-delta / decision-queue / decision-workspace 完整样例 + partial 样例 + facts 缺字段宽松样例 + workspace 缺 id 400 样例；Phase 39：actions-recent 完整 + 单条 error + outcome 缺字段宽松样例、proactive-summary 完整 + groups/metrics 为 null + 未知字段样例、calibration-overview 完整 + 单条协议 error 样例）、StatePanel 状态模型测试（error `role="alert"`、partial 列 Authority）、个人状态页（八领域网格 / 冲突与高风险标记 / 详情 claim 分组）与外部环境页（免责声明 / Delta 四组 / 客户端筛选）渲染测试、决策中心页（六组看板 + 双状态徽标 + 到期强调 + 空队列引导）、行动与结果页（摘要条 / 六节点时间线已达成·未达成 / 等宽校验字段 / outcome 真实字段 + 固定提示 / 非因果标注 / 记录结果链接 / 单条 error 降级 / CalibrationPanel INCONCLUSIVE 说明）、主动提醒页（now/deferrable 分组卡片 / 已抑制与历史诚实空态 + 控制状态查询入口 / 写按钮 disabled + REST 未暴露说明 / metrics 与 notes 渲染）、ConfirmDrawer（preview_checksum/idempotency_key 展示、具体确认文案、"不会执行的动作"固定提示）、TypedRecoveryPanel（retryable 重试、Replay 态、已知服务端限制恢复说明）、orchestration client（confirm preview 原样回传、别名路由、错误信封规范化、幂等键与 actor hash 形态）、**全路由渲染冒烟（Phase 40，`appSmoke.test.tsx`：mock 全部 API hooks 后用 createMemoryRouter 复用生产路由表逐条挂载 11 条路由，断言 h1/标志文案不抛错；含 REST 离线 role="alert" 用例）**。

## 安全与传输边界（Phase 36 基线）

- **同源（same-origin）优先：** 生产 `/app` 与全部 `/ui/*`、`/agent/session/*` API 由同一个
  rag-api 进程（`http://127.0.0.1:8000`）以相对路径提供，浏览器发出的是同源 fetch，不需要也不会
  下发 `Access-Control-Allow-Origin: *`。
- **开发期跨源 allowlist：** 仅当用 `npm run dev`（`5173`）访问 `8000` 后端时才需要显式 CORS；服务端
  内置 `127.0.0.1:5173`/`localhost:5173`，如需其它开发端口，在启动 rag-api 前设置
  `PK_COCKPIT_DEV_ORIGINS`（逗号分隔的完整 Origin 列表，例如
  `$env:PK_COCKPIT_DEV_ORIGINS = "http://127.0.0.1:5174"`）；未命中 allowlist 或本机同源的 Origin
  一律被拒绝，返回安全错误 `origin_not_allowed`，不下发跨源 CORS 头。
- **mutation 只有一条闸门：** 全部 `/agent/session/*` 写路由（prepare/confirm/preview/execute 及其
  各阶段别名）在进入编排逻辑之前先做 Origin 校验；跨源请求在读取/解析请求体之前即被拒绝，不产生任何
  会话、ledger 或 authority 副作用。
- **唯一允许的写语义：** 前端不新增、也不绕过任何写路径——所有写入仍是既有 `project + low` 受控会话
  契约（`prepare → exact preview → explicit confirm → 幂等 execute`），UI 侧确认永远不是身份认证，
  服务端 preview checksum/幂等键才是权威。
- **浏览器不拥有事实 authority：** Cockpit 只消费版本化只读 `decision_cockpit_projection_v1` 信封；
  不直接连接 SQLite/Chroma，不裁决 lifecycle/current，不计算或改写 Serving Snapshot、Active Pointer
  或 Calibration promotion。
- **浏览器不管理进程：** 前端不启动、不停止、也不重启 REST/MCP/Tunnel/Chroma 中的任何一个；
  服务生命周期完全由既有 supervisor（见 [`docs/AGENTS.md`](../../docs/AGENTS.md) §3.3）拥有，
  Cockpit 系统状态页只读展示健康探测结果。
- **安全错误信封：** transport 层（`cockpit_asset_not_found`/`cockpit_not_built`/
  `origin_not_allowed`/`internal_error`）与 Projection 层的公开 limitation/error 字段均来自固定
  allowlist code/message，不拼接请求路径、`str(exc)`、密钥、provider 响应体或
  confirmation token/HMAC；详细诊断只写本地 stderr。
- **本轮范围之外（v1.5 候选，未激活）：** Personal Knowledge Wiki / Topic Page / backlinks / LLM
  Wiki 叙述在本基线中 not shipped，Phase 36 不新建任何个人事实 authority 或离线个人数据持久化。

## 验收清单（Live UAT，Phase 40 — 未执行）

> **以下清单目前全部未勾选，代表尚未执行，不是遗漏勾选。** 它是 Phase 40 的
> 目标验收范围，只有在 Phase 40 计划实际逐条跑通真实浏览器后才能勾选并写入
> 该 Phase 自己的 SUMMARY/VERIFICATION；在此之前不得引用为"已验收"。
>
> 前置：`npm run build` 后由 rag-api 托管 `http://127.0.0.1:8000/app/`（或 `npm run dev` 代理到 8000）；
> rag-api 运行在 8000，证据中心 Widget 需 MCP 运行在 8789。
> 逐条在真实浏览器执行并勾选；失败项回到 spec §17 对应节定位。

### E2E 流程（spec §17.3）

- [ ] 1. 打开总览并显示三类 Snapshot（顶栏 Personal/External SnapshotChip + 各卡片数据，30 秒内看懂当前状态、风险与待决策事项）
- [ ] 2. 从提醒创建 Decision Case（`/proactive` 卡片「创建 Decision Case」→ `/sessions/new` → 填 goal/constraints/weights → prepare）
- [ ] 3. 查看 Analysis 和 Evidence（决策工作区三栏：决策条件 / 方案与证据 support[] / 建议与限制；`/evidence` 三个 Widget 可打开）
- [ ] 4. Prepare → Confirm → exact replay（ConfirmDrawer 核对 exact preview JSON / preview_checksum / idempotency_key / "不会执行的动作" → 显式确认；同一幂等键重试显示「已返回原事件，未重复写入」）
- [ ] 5. Decide → Action Start → Action Complete → Observe（`/sessions/:id` 逐跳推进，每跳独立 preview + 显式确认，无跳段入口）
- [ ] 6. 查看 Outcome 和 non-causal Effectiveness（`/actions` outcome 展开区真实字段 + effectiveness 显著标注「非因果评估」）
- [ ] 7. 查看 INCONCLUSIVE Calibration（`/actions` 校准总览：inconclusive_reasons + 「样本不足或协议偏离」说明）
- [ ] 8. Chroma/REST/MCP 单项离线时显示 partial 和恢复路径（停掉单项服务：对应卡片降级为 partial 并列出不可用 Authority；REST 全停：各页 error + 重试，不白屏）

### 视觉验收（spec §17.4）

- [ ] 320 宽度：无横向整体滚动；底部五栏导航可用；确认抽屉撑满、确认钮固定底部；看板/三栏转单列
- [ ] 768 宽度：顶栏下方横向导航条；无导航真空
- [ ] 1024 宽度：左侧固定导航；看板 2×3 网格
- [ ] 1440 宽度：内容居中 max-w-6xl，不拉伸变形
- [ ] 浅色 / 深色（顶栏主题切换，刷新后保持）
- [ ] 键盘导航：全站 Tab 可达、可见 focus 环；抽屉/对话框 Esc 关闭且 Tab 不逃逸；标签页可切换
- [ ] reduced motion（系统开启"减少动态效果"后无动画残留）
- [ ] 200% 缩放：布局不破、文字不裁切
- [ ] 中文长文本：长 goal / 长 predicate 不断版（break-words）
- [ ] 长 ID 与错误详情：长 recommendation_id / checksum / session_id 短码 + title 全量 + break-all，不撑破卡片

### 当前已知服务端限制（UAT 时预期内行为，非前端缺陷）

- **`PERSONAL_DATA_ORCHESTRATION_SECRET` 未配置**：所有写操作（prepare/confirm/preview/execute）返回
  `confirmation_secret_unavailable`，TypedRecoveryPanel 给出配置说明；只读页面不受影响。
- **stock rag-api 未注入 generation runner**：会话链 generate 跳返回 `generation_provider_unavailable`，
  会话停在 confirmed 不中断；publish 及之后各跳不受影响（需服务端注入 generation_runner 后才能走通）。
- **proactive 写不在 REST**：Snooze / Suppress / 限定 Scope / Restore 按钮 disabled 并注明
  「该写入由 MCP 工具或 pk CLI 提供，REST 未暴露」。

## 端口约定

| 服务 | 端口 | 说明 |
|------|------|------|
| Vite dev server | 5173 | 仅开发用 |
| rag-api（REST） | 8000 | 唯一后端，托管 `/app/` 与全部 API |
| GPT Apps MCP | 8789 | 托管证据中心三个 Widget |
| Tunnel | 8081 | 系统状态页仅展示其 up/down |

## 约束（来自 spec §15 / §5.3）

- localStorage 只写 `cockpit.theme`、`cockpit.density` 两个键，不持久化业务数据（actor hash 仅内存缓存，页面刷新即失效）。
- 浏览器日志不打印 API payload；错误规范化为 `{code, message}`（写操作为 `{code, category, message, retryable, recovery_actions}`）。
- 无外部 CDN / 字体 / 图片外链；字体用本地系统栈。
- 读取全部走只读 UI 投影；写入全部走后端 Guarded Orchestration（`/agent/session/*`），每跳 exact preview + 显式确认 + 幂等键，前端不提供"一键完成全部阶段"入口（spec §5.3 硬性）。
