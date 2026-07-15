# Roadmap: 个人数据分析项目

## Overview

项目从多源个人数据导入和统一架构开始，逐步建设结构化记忆、关系图、AI 消费接口与 canonical AgentView 会话层，并把历史会话蒸馏为可评估、可发布、可增量更新的知识单元 RAG。

**Milestone v1.1：Knowledge Unit Evaluation & Quality** — Phase 17 代码已完成，人工 gold/judge/UAT 检查点仍开放；Phase 18 正在执行。v1.0 已完成，详见 [MILESTONE-v1.0.md](MILESTONE-v1.0.md)。

## Phases

- [x] **Phase 01: Incremental Import Pipeline** - 幂等增量导入与批次审计
- [x] **Phase 02: Agent Data Ingestion** - Agent 会话、消息和工具事件结构化
- [x] **Phase 03: Integrated Architecture** - 三源统一事件、实体、关系和画像
- [x] **Phase 04: Memory Layer Upgrade** - 多类型结构化记忆与消费层
- [x] **Phase 05: Memory Layer Hardening** - 证据、契约测试和准入门禁
- [x] **Phase 05.5: Ponytail Project Optimization** - 项目瘦身与去复杂化
- [x] **Phase 06: Deep Memory Graph Mining** - 深层记忆关系与图谱
- [x] **Phase 07: Agent Conversation Normalization** - 对话规范化与叙述证据
- [x] **Phase 08: Memory Experiment Consolidation** - **Cancelled**（被 KU 架构取代，见 08-CANCELLED.md）
- [x] **Phase 09: LLM Semantic Candidate Pipeline** - 严格语义候选与证据门禁
- [x] **Phase 10: LLM Memory Relation Graph** - LLM 记忆关系候选与发布合同
- [x] **Phase 11: OpenAI MCP Apps SDK Widget** - MCP、Apps SDK 与组件接入
- [x] **Phase 12: Data Access Interfaces** - CLI、REST、MCP 数据访问契约
- [x] **Phase 13: Codebase Refactoring** - 公共基础层重构
- [x] **Phase 13.5: AgentView Session Integration** - canonical conversation store
- [x] **Phase 14: Knowledge Unit Layer** - evaluation-first RAG；30k 索引 + **KU-08 增量 journal/watermark 闭环**（2026-07-12）
- [x] **Phase 15: Retrieval SSOT & Hybrid Governance** - 15-01 SSOT/layered + 15-02 holdout/telemetry/legacy_pad 决策（2026-07-12）
- [x] **Phase 16: Google Light Structuring** - 16-01 fill + 16-02 lifecycle（stage/gate/promote）+ RO consumer contract（2026-07-12）
- [ ] **Phase 17: Knowledge Unit Comprehensive Evaluation** - 代码 17-01..04 已落地；待人工 gold/judge 校准与 UAT 签收
- [x] **Phase 18: Full Repository Governance Architecture** - 全目录/全文件治理、生命周期、依赖、CI 与空迁移验证闭环（2026-07-13）
- [x] **Phase 19: Physical Source Consolidation** - src layout、console entrypoints、shim/tools/apps/assets/tests/docs 物理收口
- [x] **Phase 20: Physical Data & Runtime Relocation** - 全部批准后 apply 完成；bak/alias 兼容窗口保留

> **Audit note (2026-07-12):** P0 + P1 (15-02 / 16-02) executed and verified. See [Phase 15–16 audit](phases/15-retrieval-ssot-governance/15-16-AUDIT.md).

## Optional Next (post-v1.0 backlog — not scheduled)

| ID | Idea | Trigger |
|----|------|---------|
| B-01 | Holdout 金标 enrichment（paraphrase / Google `g|`） | 检索质量成为痛点 |
| B-02 | 真实源变化下的付费增量 extract → journal commit | AgentsView checksum 变化 |
| B-03 | 双遍抽取 L2 session 窗 | **完成并入** active 30,774（见 14-08 / 14-09 SUMMARY） |
| B-04 | 测试覆盖补齐 non-main-path high gaps | CI 覆盖率目标 |

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
**Status:** **Cancelled 2026-07-12** — knowledge unit SSOT 已取代 memory 实验融合目标；不执行。  
**Plans:** none (see `08-CANCELLED.md`)

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
**Plans:** 14-01..07 **complete**（KU-08: journal/watermark + sandbox E2E + prod no-op）  
**Live (2026-07-12/13):**  
- active **`knowledge_units_205bff9560b9_20260712142938` (30,774)** — L1 30,012 + L2 merge +762  
- rollback target: `knowledge_units_run_76c6259e_20260712062418`  
- production prepare **no_op** when source checksum unchanged（正确）

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
**Plans:** 15-01 + 15-02  
**Artifacts:** `phases/15-retrieval-ssot-governance/`  
**Not in scope:** 删 raw/Chroma 历史；Google 全量 KU；写 live AgentsView  

### Phase 16: Google Light Structuring
**Goal:** 填充 `normalized_events` + 隐私过滤的聚合轻断言（兴趣主题/服务/频道/域名）。  
**Depends on:** Phase 15  
**Status:** **Complete** 2026-07-12  
**Plans:** 16-01 + 16-02  
**Live:** normalized **1696**；assertions **48**；lifecycle stage/gate/promote；RO list/get  
**Privacy:** service + category/content（Maps；支付/金融/卡；地图/地点/位置/导航 — 含 Search/Gemini 地点主题）  
**Not:** 对话式 KU 抽取；Maps/支付/地点主题进入兴趣断言  

### Phase 17: Knowledge Unit Comprehensive Evaluation
**Goal:** 用统一、版本化、可复跑的评测协议证明知识单元模式相对 Raw 的真实提升，隔离 L1/L2/Hybrid 各层贡献，并让评测结果成为 promote 的强制门禁。  
**Depends on:** Phase 14（L1/L2 collections 与 rollback target）、Phase 15（layer telemetry）、Phase 16（Google/light privacy contract）、Phase 13.5（canonical evidence）  
**Requirements:** [EVAL-01..10]  
**Success Criteria:**  
- Raw/L1/L2-only/L1+L2/Hybrid 在同一 gold 集和评分器下可比较，输出绝对值与相对提升  
- L2 有独立跨轮 gold，能够证明新增覆盖并量化重复、冲突、隐私与时效风险  
- 最终 RAG 回答评测覆盖 correctness、faithfulness、citation 与 abstain  
- candidate gate 在任一关键指标回退或 secret/privacy hit > 0 时阻止 promote  
- 单命令生成 versioned SQLite/JSON 结果以及本地 HTML/PNG 图表  
**Plans:** 17-01..04 code complete；人工 gold/judge/UAT 未关闭  
**Not in scope:** 更换 embedding/model；扩大 L2 抽取；把个人原文发送到外部评测 SaaS  

### Phase 18: Full Repository Governance Architecture
**Goal:** 对整个仓库从根目录到最深叶文件建立可机器验证、可持续演化、隐私安全且可回滚的治理架构。  
**Depends on:** Phase 17 code baseline；Phase 17 人工 UAT 可并行收尾，但 Phase 18 不得伪造其完成状态  
**Requirements:** [GOV-01..12]  
**Success Criteria:**  
- 100% 非 Git-internal 文件具有唯一有效治理策略；未分类/多分类均为 0  
- R3/R4 私有数据和生成物误跟踪为 0；所有生成物具有 producer/run/input/config lineage  
- 稳定模块边界有 README/owner，所有叶文件由 metadata inventory 覆盖  
- 新硬编码机器路径和新 shim 为 0；现有债务有 owner、baseline 与归零计划  
- Python/Node/依赖/secret/artifact/docs/planning/architecture gates 在本地与 CI 一致  
- 任何物理移动、归档或删除均经过 preview、兼容测试、人工批准和 rollback 演练  
**Plans:** 18-01..06 complete；18-06 以用户批准的 empty manifest（0 operations）收尾  
**Not in scope:** 未经批准删除 `_recycle`/raw/private 数据；一次性大搬迁；为所有叶目录机械添加 README  

### Phase 19: Physical Source Consolidation
**Goal:** 将 tracked 源码、入口、工具、应用、资源、测试和文档迁入目标物理树，消除 `integration/scripts` 根脚本散落。  
**Depends on:** Phase 18 governance gates  
**Requirements:** [PHY-01..08]  
**Success Criteria:** `integration/scripts/*.py=0`；正式命令由 console scripts 提供；旧消费者与 shim 完成 cohort cutover；全量测试/preflight/rollback PASS。  
**Plans:** 19-01..05 complete（历史 replay debt 见 19-VERIFICATION；future rollback SSOT 已闭环）  

### Phase 20: Physical Data & Runtime Relocation
**Goal:** 将项目内私有数据、数据库、运行时、报告、日志和归档迁入 data/var/archive 目标树。  
**Depends on:** Phase 19  
**Requirements:** [DATA-01..08]  
**Status:** **Apply complete 2026-07-13**（用户全部批准）；DATA-08 bak/alias 清理仍开放  
**Success Criteria:** 私有 cohort 经 snapshot/stage/atomic cutover；内容与 active pointer 等价。  
**Plans:** 20-01 foundation；20-02..04 apply manifests；journals in `var/phase20-journals/`  
**Live roots:** `data/` · `var/db` · `var/runtime` · `var/reports` · `archive/quarantine/_recycle`  



## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 01-07 | Legacy tracked | Complete | Before 2026-07-10 |
| 08 | — | **Cancelled** (superseded by KU) | 2026-07-12 |
| 09-13.5 | Legacy tracked | Complete | 2026-07-10 or earlier |
| 14 | 7/7 | **Complete** (KU-08 closed) | 2026-07-12 |
| 15 | 2/2 | **Complete** (01 + 02 + live holdout) | 2026-07-12 |
| 16 | 2/2 | **Complete** (01 + 02 lifecycle) | 2026-07-12 |
| **v1.0** | — | **Milestone complete** | 2026-07-12 |
| 17 | 4/4 code | **Executing** (human checkpoints open) | — |
| 18 | 6/6 | **Complete** | 2026-07-13 |
| 19 | 5/5 | **Complete** | 2026-07-13 |
| 20 | apply complete | **Complete** (alias/bak removal deferred) | 2026-07-13 |
| **v1.1** | Phase 17 human checkpoints open; Phase 18–20 data layout live | **Executing** | — |

### Phase 21: Architectural Alignment - Domains Slimming

**Goal:** 把 domains/ 下 63 个 build/eval 脚本按架构策略归位到 application/ 和 evaluation/,删除死代码,消除跨域中心节点耦合。domains/ 最终只剩纯 domain 规则/模型/常量。
**Depends on:** Phase 19(physical source consolidation — src layout 就位);承接近期 retrieval facade 拆分(阶段一)的同样手法
**Success Criteria:** 全量 pytest 通过(允许已知 baseline fail);architecture-boundary PASS;REST :8000 + MCP :8789 健康端点 200;domains/ 无 build_/evaluate_ 逻辑(只剩规则/模型/常量 + re-export facade)。
**Status:** Complete (2026-07-15) — 4/4 plans executed
**Plans:** 4/4

Plans:
- [x] 21-01: Conversation domain migration + LLM primitive split
- [x] 21-02: Graph domain migration + delete v2 dead code
- [x] 21-03: Knowledge domain migration
- [x] 21-04: Memory domain + retrieval legacy + D-08 finalization

---
*Roadmap migrated from `.gsd/phases/` on 2026-07-10. Updated 2026-07-13 for Phase 20 data/var/archive cutover.*
