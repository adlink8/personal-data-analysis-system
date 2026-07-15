---
phase: 17
name: knowledge-unit-comprehensive-evaluation
status: planned
milestone: v1.1
depends_on:
  - phases/14-knowledge-unit-layer
  - phases/15-retrieval-ssot-governance
  - phases/13.5-agentsview-session-integration
  - phases/16-google-light-structuring
requirements: [EVAL-01, EVAL-02, EVAL-03, EVAL-04, EVAL-05, EVAL-06, EVAL-07, EVAL-08, EVAL-09, EVAL-10]
---

# Phase 17 Context: Knowledge Unit Comprehensive Evaluation

## Boundary

本阶段不继续扩大知识数量，而是建立证据闭环，回答三个问题：

1. Knowledge Unit 相对 Raw 真实提升多少？
2. L2 相对 L1 增加了什么，是否引入重复、冲突或检索回退？
3. 指标是否足以自动阻止不合格 candidate 被 promote？

<decisions>
## Locked decisions

- **D-01:** 对比模式固定为 `raw / l1 / l2_only / l1_l2 / hybrid`。
- **D-02:** 所有模式使用同一 dataset snapshot、query、top-k、gold 与 scorer；禁止跨报告拼接数字。
- **D-03:** retrieval 与最终 answer 分开评分；Hybrid 必须报告 first-contributing layer，不能把 fallback 成绩归给 KU。
- **D-04:** 本地优先：SQLite + JSONL/JSON + HTML/PNG；原文不进入外部 tracing SaaS。
- **D-05:** 新 candidate 必须先评测后 promote；当前 active 只作为 baseline，不在 eval 中被修改。
- **D-06:** 自动指标优先；LLM judge 仅用于主观维度，必须先与人工样本校准。
</decisions>

## Current evidence and known gaps

- PoC 33-unit KU 曾在旧 frozen 上达到 Recall@5 0.85，对 Raw 0.50 提升 35pp，但不能代表全量索引。
- L1 30,012 在当前 frozen 的 pure-KU Recall@5 为 0.65。
- L1+L2 30,774 为 0.60，MRR@5 也下降 0.05；需要 L2 专属跨轮 gold 才能判断净价值。
- 当前 frozen 仅 20 题；15-02 holdout 8 题中只有 2 题有可计分 gold。
- L2 full report 768 units，但 merge 加载 815；pilot/full lineage 尚未统一解释。
- 现有 compare 脚本硬编码 collections、直接写 Desktop、无 run registry、无 gate。

## Dataset families

| Family | Minimum | Purpose |
|---|---:|---|
| frozen regression | 20 existing + enrichment | 保持既有能力，不允许退化 |
| cross-turn L2 | 30 | 测量 L2 独有的跨轮增益 |
| paraphrase | 20 | 语义泛化而非原文片段匹配 |
| no-answer | 20 | abstain 与误命中 |
| conflict/temporal | 20 | 当前/过期/冲突处理 |
| privacy/secret | 20 | 泄漏必须为 0 |
| Google/non-dialogue | 20 | 验证分路，不归因给 KU |

## Promotion policy

硬门：secret/privacy hit = 0；grounded citation 不低于阈值；no-answer FP 不超过阈值；existing frozen 不允许显著回退；candidate reconcile 必须精确。软门：整体 Recall/MRR、cross-turn 增益、延迟和成本。所有阈值在 17-AI-SPEC.md 中版本化。
