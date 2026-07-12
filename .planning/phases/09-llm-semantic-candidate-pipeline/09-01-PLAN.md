---
phase: 09
name: llm_semantic_candidate_pipeline
title: LLM 语义候选生成与直通证据链删除
status: Completed
created: 2026-07-01
depends_on:
  - .gsd/phases/08_memory_experiment_consolidation/PLAN.md
  - .gsd/phases/09_llm_semantic_candidate_pipeline/CONTEXT.md
  - integration/scripts/build_graph_relation_candidates.py
  - integration/scripts/build_memory_promotion_candidates.py
  - integration/db/personal_system.sqlite
autonomous: false
---

# Phase 09: LLM 语义候选生成与直通证据链删除

## Objective

扩大 LLM 在记忆系统中的参与范围：让 LLM 参与图谱候选生成、记忆候选提炼和 gate 失败修复；同时删除 `legacy_evidence_candidate` 第二路逻辑，禁止结构化 evidence 直接进入 promotion candidate。

Phase 09 的核心产物是一条新的候选生成机制：

```text
script coarse recall
-> LLM semantic candidate proposal
-> deterministic evidence/schema gate
-> LLM relation or memory judgment
-> weighted promotion gate
```

## Non-goals

- 不删除 `memory_items` / `memory_links` / `memory_relations` 兼容表。
- 不让 LLM 直接写数据库。
- 不把 `memory_items` 作为候选源。
- 不把向量相似度当成关系事实。
- 不在没有 score gate 和 hard-risk gate 的情况下自动 apply。
- 不把 Phase 09 做成大规模全量重跑；先跑 bounded sample 和可复现验证。

## Architecture Correction

Phase 08 后的目标链路仍有两个问题：

```text
conversation_turns -> script/vector candidate -> LLM judge
```

这里 LLM 介入太晚。Phase 09 改为：

```text
conversation_turns
-> script coarse recall packages
-> LLM graph candidate proposal
-> graph_relation_candidates_v2
-> LLM relation judgment
```

Phase 08 的 promotion 候选还有：

```text
memory_items -> memory_links -> unified_events_rich -> legacy_evidence_candidate
```

Phase 09 必须删除这条路径，改为：

```text
unified_events_rich / conversation_summaries / accepted graph edges
-> evidence bundles
-> LLM memory candidate extractor
-> memory_promotion_candidates
```

## Wave 1: LLM Candidate Contracts

### Goal

定义 LLM 参与候选生成的 contract，先固定 prompt/schema/rubric，避免把 LLM 扩权变成不可审计的自由生成。

### Tasks

1. 新增 prompt 目录 `integration/prompts/graph_candidate_proposal/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
2. 新增 prompt 目录 `integration/prompts/memory_candidate_extraction/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
3. 新增 prompt 目录 `integration/prompts/gate_repair_loop/`：
   - `v1_main.md`
   - `v1_schema.md`
   - `eval_rubric.md`
4. Schema 必须约束：
   - LLM 只能引用输入中已有 `source_refs` / `event_id` / `session_id` / `turn_id`。
   - LLM 不能输出没有证据的 claim。
   - LLM 必须可选择 `reject` / `downgrade` / `needs_human_review`。
   - 每次输出必须包含 `prompt_version`、`model`、`temperature`、`llm_status`。

### Acceptance Criteria

- 所有 prompt 都明确“不得编造证据”。
- graph candidate proposal 输出的是候选关系，不是最终关系事实。
- memory candidate extraction 输出的是候选 claim，不是长期 memory item。
- gate repair loop 只能修复、降级或拒绝，不允许绕过 gate。

### Verification

```powershell
git diff --check -- integration\prompts\graph_candidate_proposal integration\prompts\memory_candidate_extraction integration\prompts\gate_repair_loop
```

## Wave 2: LLM-Assisted Graph Candidate Generation

### Goal

把图谱候选生成从“脚本/向量直接产生候选”改为“两段式”：脚本只做 coarse recall，LLM 基于候选包提出语义候选。

### Tasks

1. 新增 `integration/scripts/build_graph_relation_candidates_v2.py`，或在现有脚本中增加明确的 `--llm-propose` v2 路径。
2. 脚本 coarse recall 只生成 candidate packages：
   - vector top-k pairs
   - same-session adjacent turns
   - temporal window pairs
   - same main_topic pairs
   - tool co-occurrence pairs
3. LLM 读取 package 后输出 semantic candidate proposal：
   - `candidate_id`
   - `candidate_type`
   - `proposed_relation_type`
   - `why_candidate`
   - `source_node_id`
   - `target_node_id`
   - `evidence_refs`
   - `source_refs`
   - `risk_flags`
   - `proposal_status`
4. 写入新审计表或扩展现有表：
   - 推荐新增 `graph_relation_candidate_proposals`
   - 只有通过 schema/evidence gate 的 proposal 才写入 `graph_relation_candidates`
5. 保留旧 `build_graph_relation_candidates.py` 为 fallback，不直接删除。

### Acceptance Criteria

- 图谱候选生成阶段有 LLM 参与。
- LLM proposal 失败或无 API key 时不会伪装成 live。
- 没有 source refs 的 proposal 不写入 candidates。
- 旧向量 top-k 只作为 recall，不再等同于 graph candidate。
- 输出报告统计：coarse packages、LLM proposed、schema rejected、evidence rejected、written candidates。

### Verification

```powershell
python integration\scripts\build_graph_relation_candidates_v2.py --dry-run --limit 20
python integration\scripts\build_graph_relation_candidates_v2.py --write --limit 100
python -m unittest tests.test_graph_relation_candidates_v2
```

## Wave 3: Delete Legacy Evidence Direct Candidate Path

### Goal

删除 `legacy_evidence_candidate` 第二路逻辑。旧 `memory_items` 不再进入 `memory_promotion_candidates`，只可作为 duplicate/conflict 检查对象。

### Tasks

1. 修改 `integration/scripts/build_memory_promotion_candidates.py`：
   - 删除或禁用 `build_legacy_candidates` 主路径。
   - 移除 `--max-legacy` / `--evidence-per-legacy` 主入口参数，或标为 ignored/deprecated。
   - `source_system='legacy_evidence_candidate'` 不得再出现。
2. 新增 evidence bundle 路径：
   - `integration/scripts/build_memory_evidence_bundles.py`
   - 输入：`unified_events_rich`、`conversation_turns_summary`、accepted graph edges。
   - 输出：`memory_evidence_bundles` 审计表或 JSON preview。
3. 旧 `memory_items` 用途降级为：
   - duplicate check target
   - conflict check target
   - compatibility read surface
   - 不作为 candidate source
4. 更新测试：
   - 断言 promotion candidates 中没有 `legacy_evidence_candidate`。
   - 断言没有任何 candidate 只靠 `memory_id` 成立。
   - 断言 structured evidence 必须先进入 bundle，再经 LLM extraction。

### Acceptance Criteria

- `memory_promotion_candidates` 来源只允许：
   - `graph_relation_candidate`
   - `llm_memory_candidate`
   - `manual_review_import`（如果后续需要）
- `legacy_evidence_candidate` 数量为 0。
- 旧 `memory_items` 仍可查询，但不参与候选生成。
- 长期三表计数不因本 wave 改变。

### Verification

```powershell
python integration\scripts\build_memory_promotion_candidates.py --dry-run
python integration\scripts\build_memory_promotion_candidates.py --write
python -m unittest tests.test_memory_promotion_candidates
python -m unittest tests.test_memory_evidence_bundles
```

## Wave 4: LLM Memory Candidate Extraction

### Goal

让长期记忆候选由 LLM 从 evidence bundle 中重新提炼，而不是从旧 memory item 或单条结构化事件直接生成。

### Tasks

1. 新增 `integration/scripts/extract_memory_candidates_from_bundles.py`。
2. 输入：
   - `memory_evidence_bundles`
   - accepted graph edges
   - relevant conversation summaries
3. LLM 输出：
   - `candidate_claim`
   - `memory_type`
   - `subject`
   - `long_term_value_reason`
   - `one_time_task_risk`
   - `duplicate_check_hint`
   - `conflict_check_hint`
   - `evidence_refs`
   - `source_refs`
   - `confidence`
4. 脚本写入 `memory_promotion_candidates`，`source_system='llm_memory_candidate'`。
5. 无 live LLM 时：
   - 不生成假语义候选。
   - 可以输出 `blocked:no_live_llm` 报告。
   - 不能 fallback 成旧 memory item 直通。

### Acceptance Criteria

- LLM 是 memory candidate claim 的生成者。
- 所有 candidate 都能回源。
- 不允许 claim 无证据。
- 无 API key 时明确 blocked，不用旧规则代替。

### Verification

```powershell
python integration\scripts\extract_memory_candidates_from_bundles.py --dry-run --limit 10
python integration\scripts\extract_memory_candidates_from_bundles.py --write --limit 50
python -m unittest tests.test_memory_candidate_extraction
```

## Wave 5: Gate Repair Loop and Weighted Auto-Approval

### Goal

把 gate 从一次性 reject 扩展为可审计的小型 loop，并加入权重评分制度。高分且无硬风险的候选可自动 approved；中间分进入人工 review；低分 rejected。

### Tasks

1. 修改 `evaluate_memory_promotion_candidates.py`：
   - 输出 structured failure reasons。
   - 输出 `score_components`。
   - 输出 `final_score`。
   - 输出 `auto_approval_eligible`。
2. 新增或扩展 `integration/scripts/repair_memory_promotion_candidates.py`：
   - 读取 gate failure reasons。
   - 调用 `gate_repair_loop` prompt。
   - 允许 LLM 选择 repair/downgrade/reject。
   - 最多 2 轮。
3. 评分建议：
   - evidence completeness: 0.25
   - traceability: 0.20
   - cross-session recurrence: 0.20
   - long-term usefulness: 0.15
   - non-one-time confidence: 0.10
   - consistency with existing memory: 0.10
   - risk penalties: subtractive
4. 硬风险一票否决：
   - missing source refs
   - missing evidence refs
   - one-time task
   - conflict with existing memory
   - schema invalid
   - unresolved risk flags
5. 阈值：
   - `score >= 0.85` and no hard risks: `approved`
   - `0.60 <= score < 0.85`: `review_required`
   - `< 0.60`: `rejected`

### Acceptance Criteria

- Gate failure reasons 可反馈给 LLM repair loop。
- Repair loop 不能编造证据。
- 自动 approved 必须有 score breakdown。
- 当前无 live LLM 时不能自动 approved。
- `apply_memory_promotions.py --dry-run --approved-only` 能展示 eligible actions。

### Verification

```powershell
python integration\scripts\evaluate_memory_promotion_candidates.py --write
python integration\scripts\repair_memory_promotion_candidates.py --dry-run --limit 10
python integration\scripts\apply_memory_promotions.py --dry-run --approved-only
python -m unittest tests.test_memory_promotion_review
python -m unittest tests.test_memory_gate_repair_loop
```

## Wave 6: Integration and Regression

### Goal

确保 LLM 扩权后系统仍然可审计、可回滚，不污染长期记忆，也不破坏现有检索入口。

### Tasks

1. 更新 README / integration README 中的 pipeline 说明。
2. 更新 `.planning/codebase/ARCHITECTURE.md`：
   - 标出 LLM 参与点。
   - 标出脚本 deterministic guardrail。
   - 删除“structured evidence 直接入候选”的图示。
3. 更新 `memory_decomplexity_plan.md`：
   - `legacy_evidence_candidate` 改为 remove/deleted path。
   - `build_memory_promotion_candidates.py` legacy path 改为 removed。
4. 增加 regression tests。

### Acceptance Criteria

- 文档架构图明确区分：
   - script coarse recall
   - LLM candidate proposal
   - LLM judgment
   - deterministic evidence gate
   - weighted promotion gate
- `rg "legacy_evidence_candidate"` 只允许出现在历史说明、迁移说明或测试断言中，不允许出现在 active generation path。
- `run_pipeline.py --dry-run` 不破坏。
- `test_memory_contracts.py` 仍通过。

### Verification

```powershell
python integration\scripts\run_pipeline.py --dry-run
python tests\test_memory_contracts.py
python -m unittest tests.test_graph_relation_candidates_v2 tests.test_memory_promotion_candidates tests.test_memory_candidate_extraction tests.test_memory_gate_repair_loop
git diff --check
```

## Phase Verification

```powershell
python integration\scripts\build_graph_relation_candidates_v2.py --dry-run --limit 20
python integration\scripts\build_graph_relation_candidates_v2.py --write --limit 100
python integration\scripts\build_memory_evidence_bundles.py --write --limit 100
python integration\scripts\extract_memory_candidates_from_bundles.py --dry-run --limit 10
python integration\scripts\evaluate_memory_promotion_candidates.py --write
python integration\scripts\repair_memory_promotion_candidates.py --dry-run --limit 10
python integration\scripts\apply_memory_promotions.py --dry-run --approved-only
python integration\scripts\run_pipeline.py --dry-run
python tests\test_memory_contracts.py
python -m unittest tests.test_graph_relation_candidates_v2 tests.test_memory_evidence_bundles tests.test_memory_candidate_extraction tests.test_memory_gate_repair_loop
git diff --check
```

## Success Criteria

- LLM 参与图谱候选生成，而不是只参与判边。
- `legacy_evidence_candidate` 被移出 active generation path。
- 结构化 evidence 不能直接进入 promotion candidate，必须先进入 bundle，再由 LLM 提炼。
- Gate fail 可以反馈给 LLM repair loop。
- 权重评分制度明确，自动 approved 有硬风险一票否决。
- 长期 memory 表不被无审计写入污染。

## Risks

| Risk | Impact | Mitigation |
| --- | --- | --- |
| LLM 候选生成成本过高 | 全量运行慢或费用高 | bounded sample、batch limit、resume、缓存 LLM outputs |
| LLM 编造证据 | 记忆污染 | schema + evidence gate，只允许引用输入 refs |
| 删除 legacy path 影响回归 | promotion candidates 变少 | 先引入 evidence bundle + LLM extraction，再断言来源变化 |
| 自动 approved 误写 | 长期记忆污染 | hard-risk 一票否决，默认 dry-run，score breakdown |
| 无 API key 时伪装结果 | 错误信任 fallback | 无 live LLM 时 blocked，不用旧规则替代 |

---

## PLANNING COMPLETE
