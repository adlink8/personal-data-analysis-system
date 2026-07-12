---
phase: 14
name: knowledge_unit_layer
status: Planned
created: 2026-07-05
revised: 2026-07-10
depends_on:
  - .gsd/phases/13_5_agentsview_session_integration/PLAN.md
---

# Phase 14 上下文：Training-style Knowledge Unit RAG

<domain>
## Phase Boundary

把稳定的 raw/canonical conversation evidence 转换为可验证、可去重、可版本化的 knowledge units，建立候选索引、离线 A/B、canary 和持续反馈闭环。

这里的“RAG = 二次训练”是功能类比：数据集治理、样本构造、验证集、checkpoint、评估和持续更新都模仿训练流程，但默认不更新基础模型权重。

</domain>

<decisions>
## Implementation Decisions

### D-01：Phase 13.5 是硬依赖

- Phase 14 不直接读取 live `sessions.db`。
- 会话证据只能从 Phase 13.5 发布的 canonical conversation store 进入 evidence bundle。
- secret/excluded/deleted 内容和 `evidence_eligible=0` 内容不得进入抽取、索引或评测集。

### D-02：先定义目标函数和 frozen test，再构建知识库

- 开始 schema/LLM 抽取前，先建立 raw baseline、20 条 dev queries 和 20 条 frozen test queries。
- dev 用于调 prompt/threshold/top_k；frozen test 只用于最终 gate。
- query/gold evidence 按 subject/time/source group 隔离，避免同一证据泄漏到 dev/test。

### D-03：知识单元不是无来源摘要

- 每个 unit 必须有可回查 evidence refs。
- preference/habit/personal fact 必须至少有一条 user-authored evidence；assistant/subagent/tool 内容不能单独建立个人事实。
- conflicting/current/deprecated 状态必须显式建模，不能靠“最新文本覆盖旧文本”。

### D-04：全部生成先进入 staging

- LLM 原始输出经过 Pydantic/schema/evidence/eligibility gate 后，只写 draft/staging。
- canonical merge、candidate index 和 active index 都必须使用版本化 build/run ID。
- 只有离线 gate 通过才原子 promote；失败时保留上一个有效 checkpoint。

### D-05：模型配置使用 GPT-5.6 Luna，但不能硬编码或静默替换

- 默认计划目标为 `gpt-5.6-luna`，temperature 0，用于批量 extraction/merge/judge。
- model ID 通过 CLI/config 注入，所有产物记录实际 model、prompt、schema 和 input hash。
- 若 Luna 未授权或调用失败，阶段进入 blocked/abort report；不得悄悄换模型后复用同一 baseline。

### D-06：不新增 RAG orchestration framework

- 复用当前显式 Python + SQLite + Chroma + OpenAI-compatible client。
- Pydantic v2 只用于结构化输出验证。
- 不引入 LlamaIndex、LangChain 或 LangGraph；当前主链是线性数据管道，新增框架收益不足以覆盖迁移成本。

### D-07：raw evidence 与现有 collections 保留

- `personal_events` 和 `conversation_turns` 作为 raw fallback，不删除。
- candidate `knowledge_units` collection 未通过 gate 前不能成为默认检索面。
- active collection 切换必须可回滚，并做 exact reconcile 清理 orphan IDs。

### D-08：反馈回流到 dev/hard-negative，不污染 frozen test

- 线上只记录必要的 query hash、returned IDs、scores、fallback、latency、model/index version 和用户 label。
- `wrong/stale/missing` 进入 dev/hard-negative backlog。
- frozen test 永久不由线上反馈自动改写。

### the agent's Discretion

- Pydantic model 的文件拆分方式。
- batch size、并发数和 retry backoff，但 SQLite 写入必须单 writer。
- candidate collection 的版本命名格式。

</decisions>

<canonical_refs>
## Canonical References

- `.ai-bridge/rag-knowledge-unit-issue.md` — 知识单元理论来源。
- `.gsd/phases/13_5_agentsview_session_integration/CONTEXT.md` — 会话数据、隐私和 speaker provenance 合同。
- `.gsd/phases/13_5_agentsview_session_integration/PLAN.md` — canonical conversation store 交付物。
- `integration/scripts/build_memory_evidence_bundles.py` — evidence bundle 边界。
- `integration/scripts/extract_memory_candidates_from_bundles.py` — 现有 LLM candidate 模式及 checkpoint 缺口。
- `integration/scripts/unified_search.py` — 检索公共后端。
- `integration/scripts/evaluate_vector_retrieval.py` — 现有 Recall/MRR 基线模式。

</canonical_refs>

<deferred>
## Deferred Ideas

- 不训练/微调基础模型权重；RAFT 类 post-training 另立实验阶段。
- 不在本阶段引入完整 GraphRAG。
- 不做 NovelMind narrative knowledge units。
- 不删除 raw evidence 或 legacy collections。

</deferred>

---

*Phase: 14-knowledge-unit-layer*
*Context revised: 2026-07-10*
