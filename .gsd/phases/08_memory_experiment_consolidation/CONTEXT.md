---
phase: 08
name: memory_experiment_consolidation
title: 记忆实验汇总、融合与去复杂化
status: Discussed
created: 2026-06-29
depends_on:
  - .gsd/phases/07_agent_conversation_normalization_mem0_spike/VERIFICATION_2026-06-29.md
---

# Phase 08 Context: 记忆实验汇总、融合与去复杂化

## Core Reframe

旧的 `memory_items` / `memory_relations` 不是最终真理层，而是第一代记忆机制实验：

- 输入：`unified_events`、旧实体/事件/合并层。
- 方法：scripts规则筛选、scripts规则构图。
- 结果：`memory_items=194`、`memory_relations=27`。
- 问题：规则可解释但浅，容易固化早期假设，缺少对高密度对话上下文的理解。

Phase 07 是第二代记忆机制实验：

- 输入：规范化后的 Agent/GPT 对话、turn 级高密度叙述压缩。
- 方法：向量候选召回 + LLM 提示词判边 + evidence gate。
- 结果：`conversation_summaries=164 sessions / 2046 turns`、`graph_relation_candidates=4652`、`graph_relation_judgments=4652`、accepted graph edges `19`。
- 问题：更懂上下文和关系，但仍然是实验判断，不应直接成为长期记忆事实。

Phase 08 不把旧层视为权威层，也不把新层直接推成权威层。Phase 08 的目标不是比较两组产物里的具体记忆谁更好，而是把两套机制拆成输入、切分、压缩、候选、判断、证据门、写入边界等方法环节，合并成一条新的主线 pipeline。

## Method Shift

Phase 08 的核心判断不再回到scripts规则。scripts只负责：

- 收集候选。
- 准备 evidence payload。
- 调用版本化 prompt。
- 校验 schema / evidence_refs / gate_status。
- 写入审计表和报告。

真正的语义判断由提示词约束下的大模型完成，但对象应先是“机制步骤如何合并”：哪些步骤保留 scripts，哪些步骤交给 LLM，哪些步骤需要人工 gate。具体记忆是否晋级是后续 promotion gate 的结果，不是 Phase 08 对比的核心。

这意味着 Phase 08 不是把旧 scripts 规则加一层补丁，也不是把旧 memory item 和新 graph edge 逐条 PK，而是把旧规则机制和新 LLM 图谱机制统一迁移到“deterministic orchestration + LLM semantic judgment + evidence gate + human review”的方法框架里。

## Current Data Separation

当前存在两组主要分隔的数据，它们用于分析机制效果，但不是 Phase 08 的直接比较对象：

| Layer | Storage | Key IDs | Current Role |
| --- | --- | --- | --- |
| First-gen memory experiment | `personal_system.sqlite`: `memory_items`, `memory_links`, `memory_relations` | `memory_id`, `event_id` | 规则筛出的长期记忆候选 |
| Second-gen conversation graph experiment | `conversation_summaries.json`, Chroma `conversation_turns`, SQLite `graph_relation_*`, DuckDB `conversation_graph.duckdb` | `session_id`, `turn_id`, `node_id`, `candidate_id` | LLM 基于压缩对话判断出的关系候选 |

两者目前可以通过 source evidence 人工追溯，但缺少结构化桥表：

- `memory_items.metadata` 中没有 `session_id` / `turn_id` / `source_refs`。
- `graph_relation_*` 中没有 `memory_id`。
- `memory_links.target_type` 当前主要回连 `event`，不是 conversation turn。

## Phase 08 Decision

Phase 08 不继续在 Phase 07 里堆功能。它是新的收敛阶段：

1. 把旧规则机制和新 LLM 图谱机制拆成同一套 pipeline 步骤。
2. 输出机制融合矩阵：每一步保留旧方法、采用新方法、合并方法或删除。
3. 基于融合后的机制建立“候选边界”，而不是直接写 `memory_items`。
4. 设计人工/LLM 双 gate，判断候选何时才值得成为长期记忆。
5. 删除或废弃过度复杂、低收益、重复的旧 scripts/表/流程入口。
6. 最终产出一个更小、更清楚、更可信的 memory pipeline。

## Constraints

- 不自动把 Phase 07 accepted graph edges 写入 `memory_items`。
- 不继续把 `memory_items` 当作不可挑战的权威事实。
- 不再新增平行的“第三套记忆系统”。
- 不用scripts规则替代 LLM 对高密度上下文的判断；scripts只能做 deterministic guardrail。
- 删除必须先分类：active / deprecated / archive / remove candidate。
- 所有删除或禁用必须有可恢复路径或明确替代路径。

## Desired End State

```text
raw data
-> normalized events / conversations
-> compression and candidate extraction
-> mechanism decomposition and fusion matrix
-> promotion candidates
-> review / gate
-> compact long-term memory store
-> retrieval and graph views
```

长期目标不是“表更多”，而是：

- 更少入口。
- 更清晰数据职责。
- 更强证据链。
- 更少scripts规则硬编码。
- 更高质量的可长期复用记忆。
