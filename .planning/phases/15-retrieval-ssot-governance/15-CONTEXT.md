---
phase: 15
name: retrieval_ssot_governance
status: planned
created: 2026-07-12
depends_on:
  - phases/14-knowledge-unit-layer
  - phases/13.5-agentsview-session-integration
---

# Phase 15 上下文：检索 SSOT 与分层 Fallback 治理

<domain>
## Phase Boundary

在 **不删除** 旧 raw / Chroma 历史 collection、**不写** AgentsView live DB 的前提下，收口「数据在哪 / 检索走哪 / 什么是真相」的治理：

1. 写死三层 SSOT（采集 / 知识 / 跨源事件）
2. 改造 hybrid：对话补洞不再假装 `personal_events` 等于全量对话
3. 证据链回填与分场景评测
4. Google **不**套用对话 KU 抽取；仅登记缺口与可选轻量后续

**本阶段不做：** 全量 Google→KU 生产抽取；Chroma 历史 collection 物理删除；Phase 08 memory 实验大合并。

</domain>

<decisions>
## Locked Decisions（2026-07-12 对话 + 实测锁定）

### D-01：三层 SSOT

| 层 | SSOT | 用途 |
|---|---|---|
| 对话采集 | AgentsView `sessions.db`（只读）→ canonical `agent_conversations.sqlite` | 原文、工具、密钥、message 级证据 |
| 个人知识 | `canonical_knowledge_units` + active KU Chroma | 偏好/决策/可答断言；career-os |
| 跨源旧事件 | `unified_events` / `personal_events`（过渡） | Google 等非对话；遗留语义兜底 |

- `memory_items` 保持实验层，**不得**与 KU 并列消费 SSOT。
- AgentsView `insights` 为可选旁路，**不得**覆盖 KU。

### D-02：raw fallback 策略

- **保留「补洞」能力**；不默认 KU-only。
- **不**把 `personal_events` 当作对话全文库（实测 Agent 仅 ~5.8k 事件级 vs View ~58k 消息级）。
- 目标路由：

```text
search_knowledge_units:
  1) active KU collection          # knowledge-first
  2) dialogue_fallback             # canonical message 语义/FTS 或 conversation_turns
  3) non_dialogue_raw              # personal_events 过滤 source=Google（+ 显式遗留）
```

- 在 dialogue_fallback 达标前，允许 **过渡期** 仍查全量 `personal_events`，但必须 metrics 分场景报告。

### D-03：对话补洞优先 View/canonical，不直连 live 写

- 运行时只读：`agent_conversations` 或已发布 snapshot；可选 FTS 探针可只读 View。
- 禁止写入 `C:\Users\li\.agentsview\sessions.db`。
- evidence_ref 继续 `cm|…`，与 Phase 14 一致。

### D-04：Google 不进本阶段 KU 生产

- Google 仍为阶段一：`activities` + FTS + unified + personal_events。
- `normalized_events` 当前 0 行 — 仅记录为 **Phase 16 候选**，本阶段最多产出 RESEARCH/接口草案。
- 禁止把对话 extractor prompt 原样套到 Search/YouTube 活动。

### D-05：质量门（继承 gap 分析）

| 门 | 目标 | 来源 |
|---|---|---|
| hybrid frozen R@5 | ≥ 0.85 | G2 |
| pure KU frozen R@5 | ≥ 0.75 | G3 |
| draft evidence 覆盖 | ≥ 0.85 | G1 |
| secret hit | 0 | 既有 |
| 分场景报表 | profile / code-literal / google 分列 | 新 |

### D-06：不做的事（明确 Out of Scope）

- 删除 `personal_events` 或 novel_* collection
- 硬删 Chroma 历史 `knowledge_units_*` 候选（对照结束后另开 ops）
- 批量重跑全量 KU extraction（除非 evidence backfill 脚本只补表不重抽）
- Career-os 批同步写库（仍 LLM 中介）

</domain>

<problem>
## 问题陈述

Phase 14 知识层已上线（30k KU），但消费路径仍把「旧统合事件向量」当作对话 raw 等价物，导致：

1. 对话补洞不全（粒度错误）
2. Google 与对话混在同一 fallback，语义职责不清
3. evidence 仅 51% 覆盖，career-os/审计弱
4. hybrid 0.75 未达 0.85，且 KPI 未分场景

</problem>

<success>
## 成功画面

- 文档与代码对 SSOT 描述一致；MCP/CLI/REST 行为可解释
- hybrid 分场景评测可复跑；dialogue 题主要靠 KU+对话层
- evidence 覆盖达到门禁或有明确 residual 分类账
- Google 边界写清：旧链路可用，新 KU 未做且不假装已做

</success>
