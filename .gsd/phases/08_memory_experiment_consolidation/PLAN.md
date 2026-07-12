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

把第一代“scripts规则筛选/构图”的记忆机制和第二代“高密度对话压缩 + 向量召回 + LLM 判边”的记忆机制拆解到同一方法框架下，合并各自有效环节，并删除或废弃无用的过度复杂化内容。

Phase 08 的核心产物不是“哪条记忆赢过哪条记忆”的结果对比，而是一条可审计、可回溯、可瘦身的新 memory pipeline 机制。

## Non-goals

- 不把旧 `memory_items` / `memory_relations` 直接视为最终权威。
- 不把 Phase 07 的 accepted graph edges 直接写成长期记忆。
- 不新增第三套平行 memory store。
- 不删除仍被 pipeline、测试、CLI、MCP 使用的入口。
- 不用纯向量相似度决定长期记忆。
- 不把一次性任务、临时上下文、低证据关系晋级为长期记忆。

## Working Thesis

旧 memory 层和 Phase 07 图谱层都是实验机制：

- 旧机制优势：流程简单、写入路径清楚、`memory_items/memory_links/memory_relations` 已接入现有检索。
- 旧机制问题：语义判断靠 scripts 规则，规则浅、上下文理解弱、容易固化早期假设。
- 新机制优势：先做对话清洗和高密度叙述压缩，再用向量召回缩小候选范围，最后交给 LLM 判断关系。
- 新机制问题：LLM 判边仍可能误判，accepted edge 也只是实验判断，不是长期事实。

因此下一步应该做“机制融合”，不是“旧记忆结果和新图谱结果谁覆盖谁”。

## Method

Phase 08 的机制核心必须从“scripts规则直接筛选/直接构图/直接写长期记忆”切到“deterministic pipeline + prompt-driven semantic judgment + evidence gate + human review”：

- scripts负责 deterministic orchestration：抽样、组装 evidence、调用 LLM、校验 JSON schema、校验 source refs、写审计表。
- LLM 负责 semantic judgment：上下文压缩质量、候选关系是否成立、长期价值、重复/冲突判断、是否适合进入人工 review。
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

## Wave 2: Mechanism Decomposition Matrix

### Goal

把旧规则记忆机制和新 LLM 图谱机制拆成同一组 pipeline 环节，判断每个环节应该保留、替换、合并还是删除。对比对象是“方法机制”，不是“旧 memory item 和新 graph edge 的结果谁更好”。

### Tasks

1. 新增 prompt 目录 `integration/prompts/memory_mechanism_judge/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
2. 新增 `integration/scripts/analyze_memory_mechanisms.py`。
3. 拆解维度：
   - input selection：从哪些源进入候选。
   - unitization：按 event、message、turn、session 还是 topic 切分。
   - compression：是否需要 LLM 叙述压缩，保留主干/分支/细节的标准是什么。
   - candidate generation：用 scripts 规则、向量召回、图邻近还是混合策略生成候选。
   - semantic judgment：哪些判断必须交给 LLM，哪些只做 deterministic gate。
   - evidence gate：source refs、event_id、session_id、turn_id 如何强制回溯。
   - storage boundary：哪些进入 SQLite、Chroma、DuckDB，哪些只是报告。
   - promotion policy：什么条件下才允许进入长期 `memory_items`。
   - decomplexity：旧 scripts/表/文件哪些环节被新机制替代。
4. 输入材料：
   - 旧机制 scripts：`build_memory_store.py`、`build_capability_memory.py`、`build_context_memory.py`、`build_preference_memory.py`、`build_memory_graph.py`。
   - 新机制 scripts：`build_conversation_summary.py`、`build_conversation_vector_store.py`、`build_graph_relation_candidates.py`、`judge_graph_relations.py`、`evaluate_graph_relation_judgments.py`。
   - 现有 reports：inventory、quality、vector、graph relation eval。
5. LLM 输出 schema 至少包含：
   - `mechanism_step`
   - `old_method`
   - `new_method`
   - `keep_from_old`
   - `keep_from_new`
   - `merged_method`
   - `delete_or_deprecate`
   - `required_tables`
   - `required_prompts`
   - `required_human_review`
   - `reason`
   - `risk_flags`
6. 输出：
   - `memory_mechanism_matrix.json`
   - `memory_mechanism_matrix.md`
   - `memory_pipeline_target_design.md`

### Acceptance Criteria

- 明确旧机制每个环节中“可保留的方法”和“应废弃的方法”。
- 明确新机制每个环节中“可复用的方法”和“仍需 gate 的风险点”。
- 输出一条目标 pipeline，而不是输出记忆结果排序。
- 每条机制判断必须能追溯到 owner script / table / report。
- 每条 LLM 判断必须包含 `prompt_version`、`model`、`temperature`。
- 明确哪些旧 scripts 规则被替换为 prompt judgment，哪些仍作为 deterministic guardrail 保留。

### Verification

```powershell
python integration\scripts\analyze_memory_mechanisms.py --write
```

## Wave 3: Target Pipeline and Candidate Boundary

### Goal

基于 Wave 2 的机制融合结论，建立新的候选边界：候选如何产生、如何压缩、如何召回、如何交给 LLM 判断、何时只能停留在候选层。这里设计的是候选机制，不是直接把旧/新结果搬进长期 memory store。

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
4. 输入来源按机制统一：
   - 旧事件层：`unified_events_rich` / `memory_links` 作为 evidence source，不直接把旧 memory item 当权威。
   - 新对话层：`conversation_summaries` / `conversation_turns` / `graph_relation_candidates` 作为 compressed context 和 relation evidence。
   - 机制矩阵：`memory_mechanism_matrix.json` 决定哪些步骤来自旧机制、哪些步骤来自新机制。
5. 使用 `memory_mechanism_judge` 和后续 promotion judge 的结果生成候选，不用 scripts 规则直接决定晋级。
6. 默认只写 candidate，不写 `memory_items`。

### Acceptance Criteria

- 所有 candidate 都有 evidence refs。
- 重复/冲突候选不进入 `promotion_ready`。
- 一次性任务默认标记为 `reject_or_review`。
- candidate 可回溯到 `session_id + turn_id + source_refs` 或 `event_id`；`memory_id` 只能作为历史实验引用，不能作为唯一证据。

### Verification

```powershell
python integration\scripts\build_memory_promotion_candidates.py --dry-run
python integration\scripts\build_memory_promotion_candidates.py --write
```

## Wave 4: Review Gate and Controlled Promotion

### Goal

把晋级动作从“scripts规则直接写”改成“压缩上下文 + 机制融合候选 + LLM judgment + evidence gate + human approved apply”。

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
python integration\scripts\analyze_memory_mechanisms.py --write
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
- Revision gate: mechanism matrix must produce a concrete target pipeline before promotion candidate scripts are allowed to run.
- Revision gate: promotion reports must reject candidates without evidence refs.
- Escalation gate: deletion, merge, or overwrite actions require explicit human review.
- Abort gate: if Chroma, SQLite, or DuckDB source counts do not match Phase 07 verification baselines, stop before promotion.

## Success Criteria

- 旧规则记忆实验和 Phase 07 LLM 图谱实验被统一盘点。
- 明确旧机制中哪些方法保留、替换、合并或删除。
- 明确新机制中哪些方法进入主线，哪些只作为实验分析层保留。
- 建立 `memory_promotion_candidates`，但不自动污染长期记忆。
- 建立 `memory_conversation_links` 作为旧 memory 与新 conversation graph 的结构化桥。
- 有可执行的去复杂化计划，且不会误删仍在使用的入口。
- 判断逻辑由版本化 prompt + LLM 输出 schema 承担，scripts只做 guardrail 和落库。
- Phase 08 结束时，memory pipeline 比 Phase 07 后更小、更清楚、更可信。

## Execution Order

1. Wave 1：全量 inventory。
2. Wave 2：机制拆解矩阵。
3. Wave 3：目标 pipeline 与候选边界。
4. Wave 4：review gate + dry-run apply。
5. Wave 5：decomplexity plan。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 把 LLM 关系误晋级为长期事实 | 记忆污染 | promotion candidate + review gate + dry-run apply |
| 旧 memory 被误删 | 丢失有用长期信息 | 先标记 remove candidate，不直接删除 |
| 两套机制仍停留在结果对比 | 继续误判方向 | Wave 2 输出 target pipeline，禁止把 memory item vs graph edge 当主目标 |
| 两套 ID 无法对齐 | 无法融合 | 新增 `memory_conversation_links` 桥表，但 `memory_id` 不能替代原始 evidence |
| 去复杂化过度 | 破坏 pipeline | 删除前跑 `run_pipeline.py --dry-run` 和 `test_memory_contracts.py` |
| LLM 输出不可复现 | 晋级不稳定 | 保留 prompt_version/model/evidence_refs |

---

## PLANNING COMPLETE
