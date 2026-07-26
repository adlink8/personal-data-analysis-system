# Roadmap: 个人数据分析项目

## Milestones

- ✅ **v1.1 Knowledge Unit Evaluation & Product Hardening** — Phases 01–27, shipped 2026-07-18 ([archive](milestones/v1.1-ROADMAP.md))
- ✅ **v1.2 External Context & Low-risk Decision Intelligence Pilot** — Phases 28–31, shipped 2026-07-18 ([archive](milestones/v1.2-ROADMAP.md))
- ✅ **v1.3 Agent Productization** — Phases 32–35, shipped 2026-07-18 ([archive](milestones/v1.3-ROADMAP.md))
- 🚧 **v1.4 Decision Cockpit UI** — Phases 36–40, requirements defined 2026-07-22
- 🚧 **v1.4.1 Data Layer Remediation** — Phases 41–42, initiated 2026-07-26 from data-layer audit

## v1.4.1 Goal

收口 2026-07-25/26 数据层审计中确认的两个设计级问题：抽取疆域重定义（assistant 证据轨扶正、覆盖矩阵、eligible 口径统一）与会话级去重键架构。代码级 quickfix（F-01~F-14、C2）已先行落地，本里程碑处理需要设计决策的部分。

## v1.4 Goal

把已验证的 Personal State、External Context、Decision、Action/Outcome、Proactive、Evidence 与 Guarded Orchestration 组织为可日常使用的本地 Web 驾驶舱；所有读取保持 authority/snapshot/evidence 可追溯，所有浏览器写入仅限既有 `project + low` 的 `prepare → exact preview → explicit confirm → commit/replay` 受控路径。

本里程碑不创建新的事实 SSOT、不引入客户端个人数据缓存、不自动执行外部动作或 promotion。Personal Knowledge Wiki Projection 明确后置为 v1.5。

> **2026-07-22 实现对账：**Cockpit 与 Projection 的大部分代码已作为未提交 WIP 存在；
> Phase 36–40 是对既有实现的安全、证据、真值、运行时和真实浏览器验收收口，不是从零新建。
> 当前仍不得把 v1.4 声称为完成。逐项证据见
> [`.planning/audits/V1.4-IMPLEMENTATION-PLAN-RECONCILIATION-2026-07-22.md`](audits/V1.4-IMPLEMENTATION-PLAN-RECONCILIATION-2026-07-22.md)。

## Phase Ordering

```text
36 安全 Projection 与应用基线
→ 37 状态、External 与证据真值展示
→ 38 受控决策工作区与确认
→ 39 反馈、主动提醒与运行时真值
→ 40 产品硬化与真实浏览器 UAT
```

顺序依据是独立的失败与回滚边界：

1. 先收口 CORS、DTO、safe error 和只读 Projection，避免浏览器成为影子 authority 或跨域 mutation 面。
2. 再证明 UI 能诚实表达 Personal、External、partial、stale 与证据。
3. 仅在读取、快照和证据语义可信后，对既有低风险确认写入完成真值门与 fail-closed 加固；不在前置阶段人为关闭现有受控流程。
4. 反馈只能读取已确认的 append-only 决策链，不新增自动化。
5. 完整工作流出现后，才进行真实浏览器、故障、隐私和无障碍验收。

## Phases

### Phase 36: Secure Projection and Cockpit Baseline

**Goal:** 建立可审计、版本化、只读且同源安全的 Cockpit 基线，使浏览器只能消费服务端 Projection，不能绕过现有 authority 或受控编排。

**Requirements:** CCK-01, CCK-02, CCK-03, CCK-04

**Depends on:** v1.3 Agent Productization 的 REST、Guarded Orchestration 和 authority contracts
**Plans:** 4/4 plans executed — Phase 36 closed

**Success criteria:**

1. Cockpit 通过版本化 `decision_cockpit_projection_v1` 和相对同源 API 获取读取结果；浏览器不直连 SQLite/Chroma，不裁决 lifecycle，不修改任何 authority、Serving Snapshot 或 promotion。
2. 生产 `/app` 与 API 使用 loopback same-origin；移除 wildcard CORS，开发期仅允许显式来源；跨 origin mutation 被拒绝且确认无写入。
3. DTO、Zod schema、真实 response fixture 与 Python contract 一致；`partial`、freshness、snapshot bindings、limitations 和安全错误具有稳定、不泄露 PII、路径、密钥、provider body 或 confirmation/HMAC 的契约。
4. Cockpit、Projection、测试和构建说明进入可审计版本基线；构建、定向测试与 requirements traceability 能证明现有 WIP 未被提前宣称为已交付。

### Phase 37: Authority-aware State, External and Evidence

**Goal:** 把当前个人状态、独立 External Context 和证据下钻接入 Cockpit，并准确表达事实类型、时效、冲突、部分可用与恢复路径。

**Requirements:** STATE-01, STATE-02, STATE-03, EVID-01

**Depends on:** Phase 36
**Plans:** 3 documented; 0 executed

**Success criteria:**

1. Overview 与 Personal State 页面展示当前目标、约束、变化、风险、决策队列和新鲜度，并清晰区分 Fact、Observation、Inference、Forecast、Recommendation、Confirmation、Conflict 与 Historical。
2. External 页面展示独立来源、地区、有效期、lifecycle、冲突和限制；任何 External Fact 不被显示或写入为 Personal Fact。
3. 每个可操作状态和决策结论均可展示 authority、snapshot、freshness 与 evidence binding；binding mismatch、stale、conflict、partial 或证据不足时，UI 不允许进入 prepare/confirm/execute。
4. 用户可从状态、External 和决策对象下钻稳定证据标识及只读详情；MCP Widget 或关联 authority 不可用时显示非空 degraded/recovery 状态，且遗留 Memory Graph 明确仅为历史/诊断视图，而非当前 Personal State 权威。

### Phase 38: Guarded Decision Workspace

**Goal:** 在前两阶段已验证的 snapshot 与 evidence 语义之上，为既有低风险 `project` 决策提供可比较、可确认、可重放且 fail-closed 的浏览器工作区。

**Requirements:** DEC-01, DEC-02, DEC-03

**Depends on:** Phase 37
**Plans:** 3 documented; 0 executed

**Success criteria:**

1. Decision Workspace 可比较决策问题、目标、硬约束、风险预算、候选方案、不行动基线、成本、机会成本、假设、反面证据、停止条件、缺失信息与限制；不以单一“人生分数”替代解释。
2. 唯一允许的 UI 写入是既有 `project + low` 的 `prepare → exact preview → explicit confirm → commit`；预览准确呈现将创建的事件、不会执行的动作、checksum、sequence、idempotency key 和具体确认文案。
3. 重复 confirm 返回同一事件的 exact replay；preview 过期、sequence/binding/integrity/confirmation/risk/runtime 错误及 provider outcome unknown 全部采用 typed recovery，零自动重试、零 payload 替换、零未授权写入。

### Phase 39: Feedback, Proactive and Runtime Truthfulness

**Goal:** 让用户以只读、可复盘且不夸大因果的方式理解已有决策反馈、主动提醒和运行状态，而不为界面完整性新增写入权限、自动 promotion 或外部动作。

**Requirements:** FDB-01, FDB-02, RUN-01

**Depends on:** Phase 38
**Plans:** 4 documented; 0 executed

**Success criteria:**

1. Action/Outcome 页面可连续浏览 `Recommendation → Decision → Action → Outcome → Effectiveness → Calibration` 的 append-only 历史；所有结果显式保留 `causal_claim=false`、样本量和限制。
2. Proactive 与 Calibration 页面准确展示候选、协调、用户控制历史和校准状态；未暴露 REST 写入能力的操作必须禁用并解释，不能呈现假按钮，不增加自动 promotion 或外部动作。
3. System 页面分别呈现 REST、MCP、Tunnel、Chroma 与各 authority freshness；REST 成功不被包装为所有下游健康，Cockpit 不提供启动、停止或重启服务能力。
4. 页面与相关契约测试证明反馈和主动信息只读取既有 authority，不会写入 Personal/External 事实或改变 Calibration 策略。

### Phase 40: Product Hardening and Live UAT

**Goal:** 对完整 Cockpit 执行响应式、无障碍、降级、隐私和真实浏览器验收，形成可审计的发布/恢复证据，而非仅以组件测试代替产品可用性。

**Requirements:** UX-01, UX-02, QA-01, QA-02

**Depends on:** Phase 39
**Plans:** 3 documented; 0 executed

**Success criteria:**

1. Cockpit 在 320/768/1024/1440 宽度、键盘导航、可见焦点、Esc 抽屉关闭、reduced motion、200% 缩放、长中文和长 ID 条件下可读可用；图表有等价文本或表格信息。
2. REST 全离线、MCP Widget 不可用、Chroma 不可用或单 authority 不可用时，页面准确区分 empty、partial、stale、offline 和 recovery，不把缓存、空白或旧信息伪装为当前结论。
3. `npm run build`、前端 Vitest、UI Projection Python contracts 与 orchestration/replay/privacy 定向测试均通过；测试覆盖 DTO、状态分类、跨 origin 无写入、preview 篡改/过期和重复确认。
4. 完成并记录至少一次真实浏览器 UAT：覆盖同源 read、低风险 prepare/confirm/exact replay、响应式/无障碍、服务降级、证据下钻和隐私检查；失败路径具有明确恢复或回滚记录。

### Phase 41: Extraction Scope Redefinition (Assistant Track, Coverage, Eligibility)

**Goal:** 把知识抽取从"user-only 单轨"重定义为显式双轨（user 轨守用户画像、assistant 轨收知识资产），建立 source × role × pass 覆盖矩阵并统一 inspect/prepare/inventory 的 eligible 口径。

**Requirements:** EXT-01, EXT-02, EXT-03

**Depends on:** v1.4.1 数据层审计修复（F-01~F-14 已落地）；evidence_scope 双列语义（status/lifecycle 修复后）
**Plans:** 0 documented; 0 executed

**Success criteria:**

1. assistant 轨成为有名有姓的抽取路径：独立 prompt、独立 unit_type 集合（solution/decision_rationale/technical_conclusion 等）、evidence 锚 assistant 原文、`evidence_scope='assistant'` 写入、独立 eval 集；ku| 世代既有 assistant 来源 KU 完成归属迁移或显式豁免。
2. 覆盖矩阵落地：`source × role × pass` 的"消息数/已单元化数/未覆盖原因"进入 `pk-ku doctor`，zcode/grok/qoder 等零覆盖源显形报警。
3. eligible 口径唯一化：inspect 与 prepare 对"什么算 eligible 证据"使用同一定义（assistant 是否纳入由轨而非隐式 SQL 差异决定），"inspect 有 delta 而 prepare no_op"的 Gate B 判定恢复可信。

### Phase 42: Conversation Dedup with Stable Session Keys

**Goal:** 把 canonical 会话去重从文件内容 hash 改为会话级稳定键，消除"会话更新 → 新旧 canonical session 双份并存"的结构性重复。

**Requirements:** DED-01, DED-02

**Depends on:** Phase 41（eligible/证据口径稳定后改去重键才安全）
**Plans:** 0 documented; 0 executed

**Success criteria:**

1. 同一会话的内容增长（jsonl 追加）被识别为同一 canonical session 的更新而非新会话：canonical 库中同会话不再多份并存，旧副本有明确的 supersede/替代语义。
2. 全量重建幂等：重跑 sync 不产生重复 session/message，merge 结果跨运行稳定（含 legacy 代表行选择的确定性）。

## Progress

| Phase | Requirements | Plans Complete | Status |
|---|---|---:|---|
| 36 | CCK-01, CCK-02, CCK-03, CCK-04 | 4/4 executed | Closed — 36-01 secure transport, 36-02 safe projection envelope, 36-03 frontend DTO/vocabulary hardening, 36-04 auditable baseline + 36-VERIFICATION.md all closed |
| 37 | STATE-01, STATE-02, STATE-03, EVID-01 | 0/3 executed | Planned — future plans reviewed, not executed |
| 38 | DEC-01, DEC-02, DEC-03 | 0/3 executed | Planned — future plans reviewed, not executed |
| 39 | FDB-01, FDB-02, RUN-01 | 0/4 executed | Planned — future plans reviewed, not executed |
| 40 | UX-01, UX-02, QA-01, QA-02 | 0/3 executed | Planned — future plans reviewed, not executed |
| 41 | EXT-01, EXT-02, EXT-03 | 4/4 waves + closure | **Complete 2026-07-27** — assistant 轨全链闭合,active 40,200 向量,doctor OK（见 41-CLOSURE-CHECKLIST） |
| 42 | DED-01, DED-02 | 0/0 executed | Ready — Phase 41 complete, context 就绪待 plan |

## Requirement Coverage

| Requirement group | Phase | Count |
|---|---:|---:|
| CCK-01..04 | 36 | 4 |
| STATE-01..03, EVID-01 | 37 | 4 |
| DEC-01..03 | 38 | 3 |
| FDB-01..02, RUN-01 | 39 | 3 |
| UX-01..02, QA-01..02 | 40 | 4 |
| **Total v1.4** | — | **18/18** |
| EXT-01..03 | 41 | 3 |
| DED-01..02 | 42 | 2 |
| **Total v1.4.1** | — | **5/5** |

## Backlog

> 未排序停车场（999.x）。来源：2026-07-26 全量修补梳理（4 路并行架构/数据流/
> 评估/规划核查）。执行细则见各 phase 目录；Phase 41 收尾清单见
> [`phases/PDA-41-extraction-scope-redefinition-assistant-track-coverage-eligi/41-CLOSURE-CHECKLIST.md`](./phases/PDA-41-extraction-scope-redefinition-assistant-track-coverage-eligi/41-CLOSURE-CHECKLIST.md)。
> 用 `$gsd-review-backlog` 择机提升为活跃 phase。

### Phase 999.1: 数据管线健壮性修复 (BACKLOG)

**Goal:** 消除审计登记的低概率高影响缺口：canonical 发布崩溃窗口（两次
`os.replace` 之间 dest 缺失，审计 M4）、timestamp 格式混存致字典序比较不可靠
（L2，定 `YYYY-MM-DDTHH:MM:SSZ` 规范 + 存量迁移 + 写入口校验）、
`parent_canonical_id` 永不回填（L3，实现回填或删字段，与 lifecycle 审查同批）。
**Requirements:** TBD
**Plans:** 0 plans

### Phase 999.2: 检索性能优化 (BACKLOG)

**Goal:** canonical_messages 关键词层由多 token AND LIKE 全扫（80,516 行）改
FTS5 虚表 + 同步触发器（保留 LIKE 滑窗片段路给 code-literal 长粘贴）；rag-api
启动预热 embedding 模型与 Chroma 连接，消除 p95 冷启动尾部（实测 2,082ms vs
稳态 25–150ms）。
**Requirements:** TBD
**Plans:** 0 plans

### Phase 999.3: 治理与架构例外收口 (BACKLOG)

**Goal:** 收掉 `architecture.yaml` 中 retrieval(`vector`) 反向 import
knowledge/conversation domain 契约的唯一方向性例外（契约下沉 core 或显式接口
层）；升级 GSD scanner 词表消除 6 个历史 UAT 文件（Phase 14/17/18×2/20/27）
的 open 误报。
**Requirements:** TBD
**Plans:** 0 plans

### Phase 999.4: domains facade 物理删除 (BACKLOG)

**Goal:** 日期门 2026-08-13（PRODUCT-READINESS）。前置已满足：
`application → domains` 真实 import = 0（`pk-ku doctor` 守护）。整包删除
`domains/` + shim registry `expected_count` 下调（走 retirement cohort 人工
批准）。
**Requirements:** TBD
**Plans:** 0 plans

### Phase 999.5: 评测简化与 gold 集扩充（单人可持续协议） (BACKLOG)

**Goal:** 把评测体系从"团队级严谨"降档为"单人可持续"，同时闭合就绪分两
短板之一 Eval/canary=74 与 Phase 17 human gold/judge UAT 残留。三层协议：
L1 机械门（隐私/citation/reconcile）全自动保持不动；L2 canary LLM 打标 +
人工只复核 critical（每次 promote ~15 分钟），judge 校准做一次性 1 小时投
资（一致率 ≥90% 后信任 + 10% 抽查）；L3 gold 集用"LLM 起草 → 人三键核对
（对/错/删）"扩到 100+ 条（复用 `review_packets.py` /
`llm_review_receipt.py` 基建），后续增长靠"使用即标注"（错例随手记 jsonl，
每月转正式 case；v1.4 Cockpit 落地后升级为界面 👎 按钮，衔接 Phase 39 反馈
链路）。同时显式降档：`eval_policy` 阈值调宽（yaml 改策略不改代码）、放弃
统计显著性追求（评测职责=抓回归）、场景覆盖收缩到真实提问/时变/隐私三类、
Phase 17 遗留 UAT 以简化协议关闭并记录。细化见
[`phases/999.5-eval-simplification-gold-expansion/999.5-NOTES.md`](./phases/999.5-eval-simplification-gold-expansion/999.5-NOTES.md)。
**Requirements:** TBD
**Plans:** 0 plans

## Deferred Next Milestone

v1.5 候选为 **Personal Knowledge Wiki Projection**。其 `WIKI-01..04` 依赖 v1.4 已验收的 Projection、Evidence、freshness/stale 与安全降级语义；不属于 Phase 36–40，也不应随本里程碑自动激活。完整的、非激活 GSD 预规划包位于 [`future-milestones/v1.5-personal-knowledge-wiki-projection`](./future-milestones/v1.5-personal-knowledge-wiki-projection/README.md)，必须在 v1.4 真实完成和明确授权后才可切换为活跃里程碑。

---
*Updated 2026-07-22 after v1.4 requirements confirmation*
