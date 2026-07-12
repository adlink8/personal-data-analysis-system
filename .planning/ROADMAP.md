# Roadmap: 个人数据分析项目

## Overview

项目从多源个人数据导入和统一架构开始，逐步建设结构化记忆、关系图、AI 消费接口与 canonical AgentView 会话层；当前阶段是把历史会话蒸馏为可评估、可发布、可增量更新的知识单元 RAG。

## Phases

- [x] **Phase 01: Incremental Import Pipeline** - 幂等增量导入与批次审计
- [x] **Phase 02: Agent Data Ingestion** - Agent 会话、消息和工具事件结构化
- [x] **Phase 03: Integrated Architecture** - 三源统一事件、实体、关系和画像
- [x] **Phase 04: Memory Layer Upgrade** - 多类型结构化记忆与消费层
- [x] **Phase 05: Memory Layer Hardening** - 证据、契约测试和准入门禁
- [x] **Phase 05.5: Ponytail Project Optimization** - 项目瘦身与去复杂化
- [x] **Phase 06: Deep Memory Graph Mining** - 深层记忆关系与图谱
- [x] **Phase 07: Agent Conversation Normalization** - 对话规范化与叙述证据
- [ ] **Phase 08: Memory Experiment Consolidation** - 遗留去复杂化工作，当前延后
- [x] **Phase 09: LLM Semantic Candidate Pipeline** - 严格语义候选与证据门禁
- [x] **Phase 10: LLM Memory Relation Graph** - LLM 记忆关系候选与发布合同
- [x] **Phase 11: OpenAI MCP Apps SDK Widget** - MCP、Apps SDK 与组件接入
- [x] **Phase 12: Data Access Interfaces** - CLI、REST、MCP 数据访问契约
- [x] **Phase 13: Codebase Refactoring** - 公共基础层重构
- [x] **Phase 13.5: AgentView Session Integration** - canonical conversation store
- [ ] **Phase 14: Knowledge Unit Layer** - evaluation-first training-style RAG（扩大生产 30k 索引已上线 + wrap-up 测试 PASS；仅 KU-08 非空增量 E2E 未关）
- [x] **Phase 15: Retrieval SSOT & Hybrid Governance** - 三层 SSOT、分层 fallback（KU→canonical message→turns→Google raw）、证据 100%、layered frozen R@5=1.0（2026-07-12）
- [x] **Phase 16: Google Light Structuring** - normalized_events 1696 + light assertions 49（`g|` 命名空间；非对话 KU）

## Phase Details

### Phase 01: Incremental Import Pipeline
**Goal:** 新数据以幂等、可审计批次进入结构化层。  
**Depends on:** Nothing  
**Requirements:** [IMP-01]  
**Success Criteria:** 导入可重跑；重复文件隔离而非删除；失败可恢复。  
**Plans:** 1 legacy plan

### Phase 02: Agent Data Ingestion
**Goal:** 将 Agent 会话、消息和工具事件结构化入库。  
**Depends on:** Phase 01  
**Requirements:** [AGT-01]  
**Success Criteria:** 会话内容和工具事件可查询并保留来源。  
**Plans:** 1 legacy plan

### Phase 03: Integrated Architecture
**Goal:** 构建 Google、GPT、Agent 的统一事件、实体、关系和画像。  
**Depends on:** Phase 02  
**Requirements:** [ARCH-01]  
**Success Criteria:** 三源数据可统一查询并生成画像。  
**Plans:** 1 legacy plan

### Phase 04: Memory Layer Upgrade
**Goal:** 建立多类型结构化记忆、记忆图和消费接口。  
**Depends on:** Phase 03  
**Requirements:** [MEM-01]  
**Success Criteria:** 记忆具有类型、主体、证据和关系。  
**Plans:** 1 legacy plan + 1 preserved design note

### Phase 05: Memory Layer Hardening
**Goal:** 为记忆层增加证据门禁、契约测试和准入评估。  
**Depends on:** Phase 04  
**Requirements:** [MEM-02]  
**Success Criteria:** 不合格记忆不会进入权威消费层。  
**Plans:** 1 legacy plan

### Phase 05.5: Ponytail Project Optimization
**Goal:** 删除不必要抽象，保持最小可用架构。  
**Depends on:** Phase 05  
**Requirements:** [OPT-01]  
**Success Criteria:** 核心行为不变且复杂度下降。  
**Plans:** 1 legacy plan

### Phase 06: Deep Memory Graph Mining
**Goal:** 从结构化记忆构建可查询的深层关系图。  
**Depends on:** Phase 05.5  
**Requirements:** [GRAPH-01]  
**Success Criteria:** 节点和关系均可回查证据。  
**Plans:** 1 legacy plan

### Phase 07: Agent Conversation Normalization
**Goal:** 规范化 Agent 对话并形成可回流的叙述证据。  
**Depends on:** Phase 06  
**Requirements:** [CONV-01]  
**Success Criteria:** 对话结构、角色和来源不会混淆。  
**Plans:** 1 legacy plan

### Phase 08: Memory Experiment Consolidation
**Goal:** 汇总记忆实验并收口为单一权威管道。  
**Depends on:** Phase 07  
**Requirements:** [MEMX-01]  
**Success Criteria:** 重复机制被删除或明确归档；当前延后，不阻塞 Phase 14。  
**Plans:** Deferred legacy plan

### Phase 09: LLM Semantic Candidate Pipeline
**Goal:** 通过结构化 gate 生成 LLM 语义候选。  
**Depends on:** Phase 07  
**Requirements:** [SEM-01]  
**Success Criteria:** 候选具有证据、风险和审核状态。  
**Plans:** 1 legacy plan

### Phase 10: LLM Memory Relation Graph
**Goal:** 构建可审核、可发布的 LLM 记忆关系候选。  
**Depends on:** Phase 09  
**Requirements:** [REL-01]  
**Success Criteria:** 关系不会绕过 evidence 和 promotion gate。  
**Plans:** 1 legacy plan

### Phase 11: OpenAI MCP Apps SDK Widget
**Goal:** 通过 MCP 与 Apps SDK 提供受控的数据和记忆能力。  
**Depends on:** Phase 10  
**Requirements:** [APP-01]  
**Success Criteria:** 工具和组件契约可测试。  
**Plans:** 1 legacy plan

### Phase 12: Data Access Interfaces
**Goal:** 统一 CLI、REST、MCP 的数据访问契约。  
**Depends on:** Phase 11  
**Requirements:** [API-01]  
**Success Criteria:** 三种入口返回一致的核心字段和错误语义。  
**Plans:** 1 legacy plan

### Phase 13: Codebase Refactoring
**Goal:** 收口公共工具、规则和路径，保持现有行为。  
**Depends on:** Phase 12  
**Requirements:** [REF-01]  
**Success Criteria:** 共享定义唯一；契约测试和 pipeline dry-run 通过。  
**Plans:** 1 legacy plan

### Phase 13.5: AgentView Session Integration
**Goal:** 将 AgentView 与 legacy 会话发布为隐私安全的 canonical conversation store。  
**Depends on:** Phase 13  
**Requirements:** [AV-01]  
**Success Criteria:** 无敏感正文泄漏；无双计数；下游可切换并回滚。  
**Plans:** 1 legacy plan

### Phase 14: Knowledge Unit Layer
**Goal:** 把 canonical evidence 蒸馏成 evaluation-first、可版本化发布的知识单元 RAG。  
**Depends on:** Phase 13.5  
**Requirements:** [KU-01, KU-02, KU-03, KU-04, KU-05, KU-06, KU-07, KU-08]  
**Success Criteria:** 全量抽取可恢复；canonicalization 通过 hard-negative gate；candidate 经 A/B 和 canary 后才能 promote；生命周期可增量更新和联合回滚。  
**Plans:** 14-01..06 complete；14-07 partial（契约测试绿，生产 no-op delta）  
**Live (2026-07-12 wrap-up):**  
- inventory 16,743；run `run_76c6259e9ed09d5b` gate **PASS**（succ 13,332 / yield 91.4% / fail 0.41%）  
- active **`knowledge_units_run_76c6259e_20260712062418` (30,012)**；reconcile **PASS**  
- pure-KU / hybrid frozen Recall@5 **0.65**（secret 0）；prior hybrid baseline 0.85  
- wrap-up: full pytest **347 passed**；production smoke **PASS**  
- scripts 已分包（core/knowledge/memory/… + 根 shim）；闲置模块在 `_recycle/`  
- 测试：强引用 **48/88 (54.5%)**；P0 生产链路已补；剩 3 个非主路径 high gap — `test_coverage_gaps.md`  
- 14-07 production prepare still **no_op**（KU-08 开放）

### Phase 15: Retrieval SSOT & Hybrid Governance
**Goal:** 收口采集/知识/跨源三层 SSOT；hybrid 改为 KU→对话补洞→Google/非对话 raw；证据覆盖与分场景质量门。  
**Depends on:** Phase 14（知识索引在线）、Phase 13.5（canonical）  
**Requirements:** [SSOT-01..06]  
**Success Criteria:**  
- 文档+API 一致描述 SSOT 与 fallback_policy  
- layered hybrid 可开关回 legacy；契约测试绿  
- evidence 覆盖 ≥0.85 或 residual 分类账  
- 分场景评测可复跑；hybrid 总体或分场景达到 CONTEXT 门禁  
- Google 明确「未 KU 化」边界（Phase 16 草案）  
**Plans:** 15-01-PLAN.md（W0–W5）  
**Artifacts:** `phases/15-retrieval-ssot-governance/`  
**Not in scope:** 删 raw/Chroma 历史；Google 全量 KU；写 live AgentsView  

### Phase 16: Google Light Structuring
**Goal:** 填充 `normalized_events` + 隐私过滤的聚合轻断言（兴趣主题/服务/频道/域名）。  
**Depends on:** Phase 15  
**Status:** **Complete** 2026-07-12  
**Plans:** 16-01  
**Live:** normalized **1696**；assertions **49**；脚本 `build_google_normalized_events` / `build_google_light_assertions`  
**Not:** 对话式 KU 抽取；Maps/支付进入兴趣断言  

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01-07 | Legacy tracked | Complete | Before 2026-07-10 |
| 08 | 0/1 | Deferred | - |
| 09-13.5 | Legacy tracked | Complete | 2026-07-10 or earlier |
| 14 | 6.5/7 (07 partial) | Near complete — wrap-up PASS | - |
| 15 | 1/1 | **Complete** (W0–W5 gates) | 2026-07-12 |
| 16 | 1/1 | **Complete** | 2026-07-12 |

---
*Roadmap migrated from `.gsd/phases/` on 2026-07-10. Completed checkboxes follow the former authoritative STATE.md; source artifacts remain available for audit.*
