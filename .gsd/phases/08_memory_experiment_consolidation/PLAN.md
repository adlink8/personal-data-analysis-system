---
phase: 08
name: memory_experiment_consolidation
title: 记忆实验汇总、融合与去复杂化
status: Planned
created: 2026-06-29
depends_on:
  - .gsd/phases/07_agent_conversation_normalization_mem0_spike/VERIFICATION_2026-06-29.md
  - integration/db/personal_system.sqlite
  - integration/db/conversation_graph.duckdb
autonomous: false
---

# Phase 08: 记忆实验汇总、融合与去复杂化

## Objective

把第一代“scripts规则筛选/构图”的记忆实验和第二代“高密度对话压缩 + LLM 判边”的记忆实验放到同一框架下汇总、对比、融合，并删除或废弃无用的过度复杂化内容。

Phase 08 的核心产物不是更多图谱，而是一个可审计、可晋级、可瘦身的 memory consolidation layer。

## Non-goals

- 不把旧 `memory_items` / `memory_relations` 直接视为最终权威。
- 不把 Phase 07 的 accepted graph edges 直接写成长期记忆。
- 不新增第三套平行 memory store。
- 不删除仍被 pipeline、测试、CLI、MCP 使用的入口。
- 不用纯向量相似度决定长期记忆。
- 不把一次性任务、临时上下文、低证据关系晋级为长期记忆。

## Working Thesis

旧 memory 层和 Phase 07 图谱层都是实验结果：

- 旧层优势：简单、可解释、已接入现有检索。
- 旧层问题：规则浅、上下文理解弱、可能保留早期过度设计。
- 新层优势：基于高密度对话摘要，能让 LLM 判断上下文关系。
- 新层问题：LLM 判边仍可能误判，accepted edge 也只是晋级候选，不是长期事实。

因此下一步应该做“对比和晋级”，不是“谁覆盖谁”。

## Method

Phase 08 的判断核心必须从“scripts规则筛选”切到“提示词驱动的大模型评审”：

- scripts负责 deterministic orchestration：抽样、组装 evidence、调用 LLM、校验 JSON schema、校验 source refs、写审计表。
- LLM 负责 semantic judgment：长期价值、重复关系、冲突关系、是否晋级、是否删除或降级。
- 人工 review 负责最终高风险确认：删除、覆盖、合并、写入长期记忆。

禁止把旧的硬编码规则换个名字继续当成最终判断器。

## Wave 1: Current Memory Experiment Inventory

### Goal

生成一份真实 inventory，列出所有记忆相关表、collection、文件、scripts、报告、入口，并标注 active/deprecated/duplicate/remove-candidate。

### Tasks

1. 新增 `integration/scripts/audit_memory_experiments.py`。
2. 扫描 SQLite:
   - `memory_items`
   - `memory_links`
   - `memory_relations`
   - `conversation_sessions`
   - `conversation_turns_summary`
   - `graph_relation_candidates`
   - `graph_relation_judgments`
   - `graph_relation_review_queue`
3. 扫描 DuckDB:
   - `g_turn`
   - `g_session`
   - `g_topic`
   - `g_tool`
   - `e_relation`
4. 扫描 Chroma:
   - `personal_events`
   - `conversation_turns`
5. 扫描scripts引用，识别谁还读写 memory / graph / vector。
6. 输出：
   - `integration/analysis/ai_context/memory_experiment_inventory.json`
   - `integration/analysis/ai_context/memory_experiment_inventory.md`

### Acceptance Criteria

- 报告列出每个对象的 count、owner script、reader script、write mode、current status。
- 明确标出“规则实验层”和“LLM 实验层”。
- 能识别无 reader / duplicate / deprecated 的 remove candidates。

### Verification

```powershell
python integration\scripts\audit_memory_experiments.py --write
```

## Wave 2: Experiment Comparison Matrix

### Goal

把旧规则记忆和新 LLM 图谱放到同一套指标下比较，不再凭感觉判断哪套更好。比较判断由版本化 prompt 驱动，scripts只做证据装配和结果校验。

### Tasks

1. 新增 prompt 目录 `integration/prompts/memory_experiment_judge/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
2. 新增 `integration/scripts/compare_memory_experiments.py`。
3. 对比维度：
   - evidence coverage
   - source traceability
   - relation depth
   - noise risk
   - long-term usefulness
   - retrieval usefulness
   - duplicate overlap
   - conflict risk
4. 对齐样本：
   - 从 `memory_items` 抽样。
   - 从 `graph_relation_judgments gate_status='accepted'` 抽样。
   - 从 `graph_relation_review_queue` 抽样。
5. LLM 输出 schema 至少包含：
   - `old_memory_id`
   - `new_candidate_id`
   - `judgment`
   - `long_term_value_score`
   - `duplicate_status`
   - `conflict_status`
   - `recommended_action`
   - `evidence_refs`
   - `reason`
   - `risk_flags`
6. 输出：
   - `memory_experiment_comparison.json`
   - `memory_experiment_comparison.md`

### Acceptance Criteria

- 至少比较 20 条旧 memory item 和全部 accepted graph edges。
- 每条比较结果必须能追溯到原始 evidence。
- 每条 LLM 判断必须包含 `prompt_version`、`model`、`temperature`。
- 明确输出哪些旧 memory 仍有价值，哪些应降级/合并/删除。
- 明确输出哪些 Phase 07 关系适合晋级，哪些只适合留在图谱分析层。

### Verification

```powershell
python integration\scripts\compare_memory_experiments.py --write
```

## Wave 3: Promotion Candidate Layer

### Goal

建立“晋级候选层”，让 Phase 07 的 LLM 图谱结果和旧规则 memory 都可以进入统一评审，但不能自动污染长期 memory store。

### Tasks

1. 新增 SQLite 表 `memory_promotion_candidates`。
2. 字段至少包含：
   - `promotion_id`
   - `source_system`
   - `source_candidate_id`
   - `source_memory_id`
   - `session_id`
   - `turn_id`
   - `relation_type`
   - `proposed_memory_type`
   - `proposed_subject`
   - `proposed_claim`
   - `confidence`
   - `evidence_refs_json`
   - `source_refs_json`
   - `duplicate_of_memory_id`
   - `conflict_with_memory_id`
   - `promotion_status`
   - `review_reason`
   - `created_at`
3. 新增 `integration/scripts/build_memory_promotion_candidates.py`。
4. 输入来源：
   - `graph_relation_judgments where gate_status='accepted'`
   - selected `graph_relation_review_queue`
   - old `memory_items` flagged by comparison as merge/update candidates
5. 使用 `memory_experiment_judge` 的结果生成候选，不用scripts规则直接决定晋级。
6. 默认只写 candidate，不写 `memory_items`。

### Acceptance Criteria

- 所有 candidate 都有 evidence refs。
- 重复/冲突候选不进入 `promotion_ready`。
- 一次性任务默认标记为 `reject_or_review`。
- candidate 可回溯到 `session_id + turn_id + source_refs` 或 `memory_id + event_id`。

### Verification

```powershell
python integration\scripts\build_memory_promotion_candidates.py --dry-run
python integration\scripts\build_memory_promotion_candidates.py --write
```

## Wave 4: Review Gate and Controlled Promotion

### Goal

把晋级动作从“scripts规则直接写”改成“LLM judgment + evidence gate + human approved apply”。

### Tasks

1. 新增 prompt 目录 `integration/prompts/memory_promotion_judge/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
2. 新增 `integration/scripts/evaluate_memory_promotion_candidates.py`。
3. Gate 规则：
   - evidence refs 非空且可解析。
   - proposed claim 不是一次性任务。
   - 与现有 memory 不重复，或明确是更新/合并。
   - 置信度达到阈值。
   - 关系类型可解释。
4. LLM 输出必须给出：
   - `promotion_status`
   - `memory_type`
   - `canonical_claim`
   - `merge_or_replace_target`
   - `risk_flags`
   - `human_review_required`
5. 输出：
   - `memory_promotion_report.json`
   - `memory_promotion_report.md`
6. 新增 `integration/scripts/apply_memory_promotions.py`。
7. `apply` 默认 dry-run，必须显式 `--write --approved-only` 才写入：
   - `memory_items`
   - `memory_links`
   - `memory_relations`
   - 新桥表 `memory_conversation_links`

### Acceptance Criteria

- 没有 approved candidate 时不会写入长期记忆。
- `--dry-run` 能显示将新增/更新/合并/删除什么。
- `--write` 只处理 `promotion_status='approved'`。
- `human_review_required=true` 的候选禁止自动 apply。
- 写入后能通过 `memory_conversation_links` 从 memory 追溯回 conversation turn。

### Verification

```powershell
python integration\scripts/evaluate_memory_promotion_candidates.py --write
python integration\scripts/apply_memory_promotions.py --dry-run --approved-only
```

## Wave 5: Decomplexity and Deletion Plan

### Goal

删除或废弃无用的过度复杂化内容，减少长期维护负担。

### Tasks

1. 新增 `integration/analysis/ai_context/memory_decomplexity_plan.md`。
2. 分类所有 memory / graph / vector scripts：
   - keep
   - keep but rename
   - deprecated
   - archive only
   - remove candidate
3. 优先检查：
   - 旧 pseudo graph 路径。
   - 不再使用的 mem0 candidate 路径。
   - 重复的 graph visualization / report path。
   - 旧规则筛选scripts中可被 promotion flow 替代的部分。
4. 删除必须分两步：
   - 本阶段先生成 deletion plan。
   - 真删除放到后续小 phase 或明确任务中。

### Acceptance Criteria

- 每个 remove candidate 都有替代路径和风险说明。
- 不删除仍被 `run_pipeline.py`、tests、README、CLI 使用的scripts。
- 输出最小化建议：优先关入口/标 deprecated，再删除。

### Verification

```powershell
python integration\scripts\run_pipeline.py --dry-run
python tests\test_memory_contracts.py
git diff --check
```

## Phase Verification

```powershell
python integration\scripts\audit_memory_experiments.py --write
python integration\scripts\compare_memory_experiments.py --write
python integration\scripts\build_memory_promotion_candidates.py --dry-run
python integration\scripts\build_memory_promotion_candidates.py --write
python integration\scripts\evaluate_memory_promotion_candidates.py --write
python integration\scripts\apply_memory_promotions.py --dry-run --approved-only
python integration\scripts\run_pipeline.py --dry-run
python tests\test_memory_contracts.py
git diff --check
```

## GSD Planning Gates

- Pre-flight gate: Phase 07 verification must be PASS and current databases must be readable.
- Revision gate: comparison and promotion reports must reject candidates without evidence refs.
- Escalation gate: deletion, merge, or overwrite actions require explicit human review.
- Abort gate: if Chroma, SQLite, or DuckDB source counts do not match Phase 07 verification baselines, stop before promotion.

## Success Criteria

- 旧规则记忆实验和 Phase 07 LLM 图谱实验被统一盘点。
- 明确哪些旧 memory 值得保留、合并、降级或删除。
- 明确哪些 LLM 图谱关系值得晋级长期记忆。
- 建立 `memory_promotion_candidates`，但不自动污染长期记忆。
- 建立 `memory_conversation_links` 作为旧 memory 与新 conversation graph 的结构化桥。
- 有可执行的去复杂化计划，且不会误删仍在使用的入口。
- 判断逻辑由版本化 prompt + LLM 输出 schema 承担，scripts只做 guardrail 和落库。
- Phase 08 结束时，memory pipeline 比 Phase 07 后更小、更清楚、更可信。

## Execution Order

1. Wave 1：全量 inventory。
2. Wave 2：实验对比矩阵。
3. Wave 3：晋级候选层。
4. Wave 4：review gate + dry-run apply。
5. Wave 5：decomplexity plan。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 把 LLM 关系误晋级为长期事实 | 记忆污染 | promotion candidate + review gate + dry-run apply |
| 旧 memory 被误删 | 丢失有用长期信息 | 先标记 remove candidate，不直接删除 |
| 两套 ID 无法对齐 | 无法融合 | 新增 `memory_conversation_links` 桥表 |
| 去复杂化过度 | 破坏 pipeline | 删除前跑 `run_pipeline.py --dry-run` 和 `test_memory_contracts.py` |
| LLM 输出不可复现 | 晋级不稳定 | 保留 prompt_version/model/evidence_refs |

---

## PLANNING COMPLETE
