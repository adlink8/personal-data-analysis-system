# Requirements: v1.4 Decision Cockpit UI

**Defined:** 2026-07-22  
**Core Value:** 以长期个人数据为内部状态、以外部社会环境为外部状态，在隐私安全、证据可回查和不确定性可解释的前提下，为用户提供可验证、可反馈、可持续校准的个人决策支持。

## v1.4 Requirements

### Projection and Secure Transport

- [ ] **CCK-01**: 用户可通过版本化的只读 Cockpit Projection 查看汇总数据；浏览器不直连 SQLite/Chroma，不创建影子 SSOT，也不改变 Serving Snapshot、Active Pointer、KU lifecycle、External authority 或 Calibration promotion。
- [x] **CCK-02**: 生产 Cockpit 使用 loopback same-origin `/app` 与 API；移除 wildcard CORS，开发期仅允许显式来源，所有 mutation route 拒绝跨 origin 请求且不产生写入。
- [ ] **CCK-03**: UI Projection 在 authority 不可用时返回可验证的 `partial`、freshness、snapshot bindings 和 safe limitations；异常文本、路径、PII、密钥、provider body 与 confirmation/HMAC 不出现在 DOM、console 或 API 错误。
- [ ] **CCK-04**: Cockpit 代码、Projection、契约测试和构建说明进入可审计版本基线；未通过对应验证的 WIP 不得在 README 或计划中标为已交付。

### Current State, External Context and Evidence

- [ ] **STATE-01**: 用户可在总览和个人状态中查看当前目标、约束、变化、风险、决策队列与数据新鲜度，并明确区分 Fact、Observation、Inference、Forecast、Recommendation、Confirmation、Conflict 与 Historical。
- [ ] **STATE-02**: 用户可查看独立 External Context 的来源、地区、有效期、lifecycle、冲突和限制；External Fact 不会被显示或写入为 Personal Fact。
- [ ] **STATE-03**: 每个可操作的状态或决策结论显示 authority/snapshot/freshness/evidence 信息；binding mismatch、stale、conflict、partial 或 evidence 不足时不得允许 prepare/confirm/execute。
- [ ] **EVID-01**: 用户可从当前状态、External 或决策对象只读下钻到稳定的证据标识和可用详情；MCP Widget 或关联 authority 不可用时显示非空降级状态和恢复说明，不将旧 Memory Graph 说成当前 Personal State 权威。

### Guarded Decision Workflow

- [ ] **DEC-01**: 用户可在 Decision Workspace 比较决策问题、目标、硬约束、风险预算、候选方案、不行动基线、成本、机会成本、假设、反面证据、停止条件、缺失信息与限制。
- [ ] **DEC-02**: 用户只能在低风险 `project` 域通过 `prepare → exact preview → explicit confirm → commit` 写入；预览清楚显示将创建的事件、不会执行的动作、checksum、sequence、idempotency key 和具体确认文案。
- [ ] **DEC-03**: 用户在重复 confirm 时看到同一事件的 exact replay；preview 过期、sequence/binding/integrity/confirmation/risk/runtime 错误和 provider outcome unknown 都走 typed recovery，无自动重试或更换 payload。

### Feedback, Proactive and Runtime Truthfulness

- [ ] **FDB-01**: 用户可浏览 Recommendation → Decision → Action → Outcome → Effectiveness → Calibration 的完整 append-only 历史，且所有结果明确保留 `causal_claim=false` 与样本/限制说明。
- [ ] **FDB-02**: 用户可查看 Proactive 候选、协调、用户控制历史和 Calibration 状态；未暴露的 REST 写入能力必须诚实禁用或说明，UI 不新增自动 promotion 或外部动作。
- [ ] **RUN-01**: 用户可分别看到 REST、MCP、Tunnel、Chroma 与 authority freshness 的真实健康状态；Cockpit 只读展示，不启动、停止或重启任何服务。

### Product Quality and Acceptance

- [ ] **UX-01**: Cockpit 在 320/768/1024/1440 宽度、键盘导航、可见焦点、Esc 抽屉关闭、reduced motion、200% 缩放、长中文与长 ID 情况下保持可读可用；图表有等价文字或表格信息。
- [ ] **UX-02**: REST 全离线、MCP Widget 不可用、Chroma 不可用或单 authority 不可用时，页面显示准确的 empty/partial/stale/offline/recovery 状态，不把缓存或空白页伪装为当前结果。
- [ ] **QA-01**: `npm run build`、前端 Vitest、UI Projection Python 契约、orchestration/replay/privacy 的相关测试均通过，并包含 DTO、状态分类、跨 origin 无写入、preview 篡改/过期与重复确认回归。
- [ ] **QA-02**: 完成并记录至少一次真实浏览器端到端 UAT，覆盖同源 read、低风险 prepare/confirm/exact replay、响应式/无障碍、服务降级、证据下钻与隐私检查；失败时有明确回滚或恢复记录。

## v1.5+ Requirements

### Personal Knowledge Wiki Projection

- **WIKI-01**: 基于活跃权威和 Snapshot 构建只读 Project、Goal、Decision 等主题页，不新建个人事实 SSOT。
- **WIKI-02**: 主题页展示来源、历史、关联决策和 backlinks，并由变化检测标记 stale、生成 Candidate、受控发布。
- **WIKI-03**: LLM 只能生成受证据约束的页面叙述候选；页面文案不会反馈写入 KU/Chroma 作为事实权威。

## Out of Scope

| Feature | Reason |
|---|---|
| Personal Wiki / Topic Pages / Backlinks | 需要独立 materialization、staleness 与发布治理；明确后置到 v1.5。 |
| 新的个人事实库、客户端数据库或浏览器 lifecycle 规则 | 会形成影子 SSOT，破坏现有 authority 边界。 |
| automatic external action、automatic promotion、自动替用户决定 | 违背用户主权、风险控制和已有 v1.3 契约。 |
| health/finance/relationship 等高风险写入域 | v1.4 只允许已有 `project + low` 受控试点。 |
| 浏览器持久化 raw personal data 或离线缓存 | 未设计加密、撤销、过期与隐私清除策略。 |
| 新的前端框架、SSR、多租户或独立 Node 生产服务 | 本地单用户产品无需扩大运行面；复用 Vite build + Python `/app`。 |

## Traceability

| Requirement | Phase | Status |
|---|---|---|
| CCK-01..04 | Phase 36 | Pending |
| STATE-01..03, EVID-01 | Phase 37 | Pending |
| DEC-01..03 | Phase 38 | Pending |
| FDB-01..02, RUN-01 | Phase 39 | Pending |
| UX-01..02, QA-01..02 | Phase 40 | Pending |

**Coverage:**

- v1.4 requirements: 18 total
- Mapped to phases: 18
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-22*  
*Last updated: 2026-07-22 after v1.4 research synthesis*
