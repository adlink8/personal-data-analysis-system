# Requirements: 个人数据分析项目

**Defined:** 2026-07-10  
**Core Value:** 把个人历史转换为隐私安全、证据可回查、能够持续增量学习的外部知识系统。

## Current Milestone Requirements

### Historical platform capabilities

- [x] **IMP-01**: 新导出数据可以通过幂等增量导入流水线进入本地结构化层
- [x] **AGT-01**: Agent 会话、消息和工具事件可以被结构化入库
- [x] **ARCH-01**: Google、GPT、Agent 数据可以形成统一事件、实体、关系和画像
- [x] **MEM-01**: 系统可以构建带来源的 tooling、capability、fact、project、habit 和 preference 记忆
- [x] **MEM-02**: 记忆接口具有契约测试、证据门禁和回滚保障
- [x] **OPT-01**: 项目经过最小化和去复杂化审查，不为一次性场景引入重型抽象
- [x] **GRAPH-01**: 记忆节点可以形成可查询、可追溯的关系图
- [x] **CONV-01**: Agent 对话可以规范化并形成结构化叙述证据
- [x] **SEM-01**: LLM 语义候选必须通过结构化 gate 后才能进入后续记忆流程
- [x] **REL-01**: LLM 关系候选具有 evidence、risk 和 promotion contract
- [x] **APP-01**: 数据和记忆能力可通过 MCP 与 Apps SDK 消费
- [x] **API-01**: CLI、REST、MCP 对外暴露一致的数据访问契约
- [x] **REF-01**: 公共工具、规则和项目路径集中到共享基础模块
- [x] **AV-01**: AgentView 与 legacy 会话形成隐私安全、可回滚的 canonical conversation store

### Phase 14 — Training-style RAG

- [x] **KU-01**: 冻结 eval、raw baseline 和泄漏检查可复现
- [x] **KU-02**: knowledge unit schema、run manifest、staging、promote 和 rollback 可验证
- [x] **KU-03**: 严格抽取在小样本上满足 schema、evidence 与 privacy gate
- [x] **KU-04**: candidate knowledge-unit index 在 frozen test 上显著优于 raw baseline
- [x] **KU-05**: 扩大 inventory（16,743 权威 / 14,584 run ledger）可分批、缓存、重试、断点续跑；extraction gate PASS；失败不会错误 promote
- [x] **KU-06**: subject/type 分桶 canonicalization 已跑通；hard-negative false merge=0；扩大批 27,655 + Plan-04 2,357 合并 current
- [x] **KU-07**: knowledge-first 检索、canary smoke、raw fallback 与 promote/rollback 已验证（扩大索引 pure-KU Recall@5=0.65）
- [ ] **KU-08**: 增量刷新契约测试已绿；生产非空 delta → journal promote → watermark 仍待真实 source 变化后验收

## Deferred Requirements

### Memory experiment consolidation

- **MEMX-01**: 收口 Phase 08 的记忆实验、删除重复机制并形成单一权威管道

## Out of Scope

| Feature | Reason |
|---------|--------|
| 直接查询 AgentView live DB 作为下游事实源 | 无法保证快照一致性和隐私边界 |
| 删除 legacy/raw 数据以节省空间 | 会破坏追溯与回滚 |
| 未经 eval gate 自动替换 active index | 可能造成检索质量或隐私回归 |
| 核心层引入 LangChain/LlamaIndex/LangGraph | 当前轻量实现已覆盖真实需求 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| IMP-01 | Phase 01 | Complete |
| AGT-01 | Phase 02 | Complete |
| ARCH-01 | Phase 03 | Complete |
| MEM-01 | Phase 04 | Complete |
| MEM-02 | Phase 05 | Complete |
| OPT-01 | Phase 05.5 | Complete |
| GRAPH-01 | Phase 06 | Complete |
| CONV-01 | Phase 07 | Complete |
| MEMX-01 | Phase 08 | Deferred |
| SEM-01 | Phase 09 | Complete |
| REL-01 | Phase 10 | Complete |
| APP-01 | Phase 11 | Complete |
| API-01 | Phase 12 | Complete |
| REF-01 | Phase 13 | Complete |
| AV-01 | Phase 13.5 | Complete |
| KU-01–KU-07 | Phase 14 | Complete |
| KU-08 | Phase 14 | Partial — tests green; production non-empty delta pending |

**Coverage:**
- Current requirements: 22 total
- Mapped to phases: 22
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-10 from legacy GSD artifacts*
