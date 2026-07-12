---
phase: 06
name: deep_memory_graph_mining
title: 深层记忆图谱挖掘
status: Completed
created: 2026-06-17
depends_on:
  - .gsd/phases/05_memory_layer_hardening/PLAN.md
  - .gsd/phases/05_5_ponytail_project_optimization/EXECUTION.md
  - integration/analysis/ai_context/memory_depth_readiness.md
autonomous: false
---

# Phase 06: 深层记忆图谱挖掘

## Objective

把 Phase 04/05 的记忆图谱从浅层标签提升为可解释的深层洞察系统：能识别长期模式、时间演化、能力形成路径、关系强度、冲突/反例，并生成可被 AI 使用但不污染长期记忆的深层 profile。

## Entry Gate

Phase 06 只有在以下条件满足后才执行：

- Phase 05 contract tests 通过。
- Phase 05 memory governance 字段已落地。
- Phase 05.5 Ponytail 优化门已完成，且未破坏 Phase 05 验证。
- `memory_depth_readiness.md` 存在。
- readiness 报告中至少有 3 个 `depth_candidate` 主题。
- readiness 报告明确列出证据不足主题，Phase 06 不对这些主题生成强结论。

## Non-goals

- 不引入完整 GraphRAG runtime。
- 不自动写回长期 memory store。
- 不把 LLM 生成内容当事实。
- 不做 dashboard。
- 不替代 Phase 05 的治理和测试。

## Wave 1: Depth Input Loader

### Goal

建立深挖输入层，只消费通过 Phase 05 readiness gate 的候选主题和带证据链的 memory graph。

### Tasks

1. 新增 `integration/scripts/mine_deep_memory_graph.py`。
2. 读取 `memory_depth_readiness.md` 或等价 JSON/Markdown readiness 输出。
3. 读取 SQLite 中的 `memory_items`、`memory_links`、`memory_relations`。
4. 过滤掉 readiness 标记为证据不足的主题。
5. 生成内部候选结构：
   - topic/entity
   - evidence items
   - related entities
   - time window
   - relation weights
   - contradictions

### Verification

- `python integration\scripts\mine_deep_memory_graph.py --dry-run`

### Acceptance Criteria

- dry-run 能列出候选主题和跳过原因。
- 不读取未通过 readiness 的主题作为强洞察输入。

## Wave 2: Pattern and Evolution Mining

### Goal

从 memory graph 中挖出稳定模式和时间演化，而不是只输出静态标签。

### Tasks

1. 计算每个候选主题的：
   - evidence_count
   - time_span_days
   - recurrence_count
   - relation_count
   - relation_strength_avg
   - contradiction_count
2. 按主题生成洞察类型：
   - stable_preference
   - tool_migration
   - capability_path
   - project_cluster
   - decaying_interest
   - contradiction_or_tension
3. 给每条洞察打 `strong/moderate/weak/unsupported`。
4. 将 unsupported 输出到待补证据列表，不进入 profile。

### Verification

- `python integration\scripts\mine_deep_memory_graph.py --output-json`
- 抽查 JSON 中每条 strong/moderate 洞察都有 evidence 和 time window。

### Acceptance Criteria

- 至少生成 5 条候选洞察。
- 每条 strong/moderate 洞察都有证据列表。
- unsupported 不进入最终 profile。

## Wave 3: Deep Profile Builder

### Goal

把深层洞察转成 AI 可消费 profile，同时保留证据和不确定性。

### Tasks

1. 新增 `integration/scripts/build_deep_memory_profile.py`。
2. 输入 Wave 2 的 JSON 结果。
3. 输出：
   - `integration/analysis/ai_context/deep_memory_insights.json`
   - `integration/analysis/ai_context/deep_memory_insights.md`
   - `integration/analysis/ai_context/deep_memory_profile.md`
4. Markdown 输出分区：
   - Long-term patterns
   - Tool and workflow evolution
   - Capability formation paths
   - Project/theme clusters
   - Contradictions and stale memories
   - Do not over-infer
5. 控制 profile 长度，适合注入 agent prompt。

### Verification

- `python integration\scripts\build_deep_memory_profile.py`
- 检查输出文件存在且包含 confidence/evidence/contradiction 区块。

### Acceptance Criteria

- 深层 profile 明确区分强结论、弱结论和不要推断。
- 每个强结论都有 evidence ids 或 source references。
- profile 不超过可注入上下文的合理长度。

## Wave 4: Evaluation and Comparison

### Goal

验证 Phase 06 输出确实比 Phase 04 的浅层 profile 更深，而不是更长。

### Tasks

1. 对比 `person_profile_v2.md` 和 `deep_memory_profile.md`。
2. 建立评估表：
   - shallow label 是否升级为 pattern。
   - 是否增加时间演化。
   - 是否增加关系强度。
   - 是否增加反例/限制。
   - 是否保留证据链。
3. 输出 `integration/analysis/ai_context/deep_profile_evaluation.md`。
4. 将不可靠洞察列入 review list，而不是写入最终 profile。

### Verification

- `python integration\scripts\build_deep_memory_profile.py --evaluate`
- 人工抽查至少 5 条深层洞察。

### Acceptance Criteria

- 评估报告证明深层 profile 不是浅层 profile 的简单扩写。
- 至少 5 条洞察包含 pattern/evolution/contradiction 中的一种。
- 所有不可靠洞察被标记为 review/exclude。

## Wave 5: Documentation and Integration Notes

### Goal

把深层图谱能力写清楚，并明确它与现有 search/profile/MCP 的关系。

### Tasks

1. 更新 `README.md` 和 `integration/README.md`。
2. 说明浅层 profile 与深层 profile 的区别。
3. 说明 Phase 06 不自动写回长期 memory store。
4. 增加复现命令。
5. 更新 `.planning/codebase/ARCHITECTURE.md` 和 `TESTING.md`。

### Verification

- `git diff --check`
- README 中的 Phase 06 命令可运行。

### Acceptance Criteria

- 用户能明确知道什么时候使用 `person_profile_v2.md`，什么时候使用 `deep_memory_profile.md`。
- 文档说明了深层洞察的证据要求和限制。

## Phase Verification

```powershell
python integration\scripts\mine_deep_memory_graph.py --dry-run
python integration\scripts\mine_deep_memory_graph.py --output-json
python integration\scripts\build_deep_memory_profile.py
python integration\scripts\build_deep_memory_profile.py --evaluate
git diff --check
```

## Success Criteria

- 深层洞察有证据链、时间跨度、关系强度和反例检查。
- 输出区分 strong/moderate/weak/unsupported。
- deep profile 比浅层 profile 多出可解释模式，而不是只增加文字。
- 不可靠洞察不进入最终可注入 profile。
- Phase 06 仍保持本地优先，不引入外部托管服务。

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 把浅层统计误认为深层洞察 | profile 污染 | 强制 evidence/time/contradiction 字段 |
| LLM 摘要引入幻觉 | 事实错误 | LLM 只可选做表达层，不做事实层 |
| 证据不足仍输出强结论 | 用户画像失真 | unsupported/review 不进入 profile |
| 图挖掘复杂度过高 | 阶段失控 | 不引入完整 GraphRAG，先做轻量 scoring |
| Phase 05 未完成就执行 | 输入不可信 | Entry Gate 阻断 |

---

## PLANNING COMPLETE
