---
phase: 14
name: knowledge_unit_layer
title: Training-style Knowledge Unit RAG
status: Wave 0-4 完成 / Wave 3,5-6 待执行
created: 2026-07-05
revised: 2026-07-10
depends_on:
  - .gsd/phases/13_5_agentsview_session_integration/PLAN.md
  - .gsd/phases/09_llm_semantic_candidate_pipeline/PLAN.md
  - integration/scripts/build_memory_evidence_bundles.py
  - .ai-bridge/rag-knowledge-unit-issue.md
ai_spec:
  - .gsd/phases/14_knowledge_unit_layer/AI-SPEC.md
autonomous: false
---

# Phase 14：Training-style Knowledge Unit RAG

<objective>
把 canonical conversation/unified event evidence 通过版本化的数据集构建、严格结构验证、语义去重、hard-negative 评估、候选索引和 canary 反馈，转换为可信、可追溯、可回滚的 knowledge-unit retrieval surface。
</objective>

## Non-goals

- 不更新基础模型权重。
- 不直接读取 AgentView live database。
- 不删除 raw events、personal_events、conversation_turns 或 memory_items。
- 不引入 LangChain/LlamaIndex/LangGraph。
- 不让 LLM 输出绕过 evidence/schema/eval gate。
- 不在本阶段做 NovelMind narrative units。

## Target Pipeline

```text
canonical conversations + unified events
  → eligible evidence bundles
  → versioned extraction staging
  → knowledge_units (draft)
  → subject/type/time-aware canonicalization
  → candidate Chroma collection
  → dev tuning + frozen-test A/B
  → atomic active-index promotion
  → unified search + canary + feedback
  → affected-subject incremental rebuild
```

## Locked Decision Coverage

| Decision | Covered by |
|---|---|
| D-01 Phase 13.5 hard dependency | frontmatter + all evidence inputs |
| D-02 evaluation-first | Wave 0 |
| D-03 evidence and speaker support | Waves 1-3 |
| D-04 staging/checkpoint/promote | Waves 1 and 4 |
| D-05 GPT-5.6 Luna configuration | Wave 2 + run manifest |
| D-06 no orchestration framework | AI-SPEC + implementation files |
| D-07 raw fallback | Waves 4-5 |
| D-08 feedback does not alter frozen test | Waves 5-6 |

<tasks>
## Wave 0：Evaluation Contract 与 Raw Baseline

### Task 0.1 — 建立 dev/frozen reference datasets

**Files**

- `integration/evals/knowledge_units/README.md`
- `integration/evals/knowledge_units/dev_queries.private.jsonl`
- `integration/evals/knowledge_units/frozen_test_queries.private.jsonl`
- `integration/evals/knowledge_units/merge_positive_pairs.private.jsonl`
- `integration/evals/knowledge_units/hard_negative_pairs.private.jsonl`
- `tests/test_knowledge_unit_eval_dataset.py`

**Action**

- 建立 20 dev、20 frozen test、20 merge-positive、20 hard-negative cases。
- 覆盖 preference、project decision、capability、time conflict、deprecated、no-answer、assistant-only、subagent-only、secret-ineligible 和跨 source duplicate。
- 每个 case 包含 query、gold evidence refs、allowed unit types、expected abstain/conflict 和 split group。
- 按 subject/source/time group 检查泄漏；frozen test 一旦确认不再由 pipeline 自动修改。
- 私人真实 queries/evidence refs 使用现有 `.gitignore` 的 `*.jsonl` 规则保持本地不入 Git；`README.md` 固化 schema、标签说明和重建方法，测试文件使用 synthetic cases。报告只暴露 dataset hash 和聚合指标。

### Task 0.2 — 记录 raw retrieval baseline

**Files**

- `integration/scripts/evaluate_knowledge_unit_rag.py`
- `integration/analysis/ai_context/knowledge_unit_raw_baseline.json`
- `integration/analysis/ai_context/knowledge_unit_raw_baseline.md`

**Action**

- 在 `personal_events + conversation_turns` 上计算 Recall@5、MRR@5、no-answer false positive、deprecated/secret hit、p50/p95 latency。
- baseline manifest 记录 dataset hash、Chroma collection counts、embedding model、git SHA 和 canonical conversation build ID。
- Chroma 不可用或计数与上游不一致时 pre-flight abort，不能用旧报告代替。

**Gate — Pre-flight**

- dataset schema/refs 100% 有效且 split 泄漏为 0。
- raw collections 健康且 count reconciliation 通过。
- 没有 baseline 就不得进入 Wave 1。

## Wave 1：Versioned Schema、Run Manifest 与 Staging

### Task 1.1 — 新增知识单元 schema

**Files**

- `integration/scripts/migrate_add_knowledge_unit_tables.py`
- `requirements.txt`
- `tests/test_knowledge_unit_contracts.py`

**Action**

- 新增 `knowledge_build_runs`、`knowledge_units`、`knowledge_unit_evidence`、`canonical_knowledge_units`、`canonical_unit_members`、`knowledge_index_versions`。
- unit/canonical 记录 `run_id/schema_version/prompt_version/model/input_hash/status/version/supersedes_id`。
- evidence 表设置 `UNIQUE(unit_id, evidence_ref)` 和外键；所有 status/type 使用 CHECK constraint。
- 显式声明并固定 `pydantic>=2,<3`，不依赖 MCP 等包的传递依赖。
- ID 使用 generation hash + version，不再用 `hash(question+subject)` 配合 `INSERT OR IGNORE`。
- 迁移脚本幂等，默认 dry-run/inspect；不修改 memory_items。

### Task 1.2 — 建立 run manifest 和 staging publish helper

**Files**

- `integration/scripts/knowledge_unit_pipeline.py`
- `tests/test_knowledge_unit_checkpoint.py`

**Action**

- manifest 记录 input dataset hash、source counts/time range、prompt/schema/model/embedding/config/git SHA。
- 新 run 先写 staging；只有 gate 通过才 promote status。
- 失败 run 不清空旧 current rows；修复现有 candidate extractor “先删除旧候选再调用 LLM”的同类风险。
- 提供 checkpoint rollback 和 exact table/index reconciliation helper。

## Wave 2：Evidence → Strict Knowledge Unit Extraction

### Task 2.1 — 版本化 prompt 与 Pydantic schema

**Files**

- `integration/prompts/knowledge_unit_extractor/v1_main.md`
- `integration/prompts/knowledge_unit_extractor/v1_schema.md`
- `integration/prompts/knowledge_unit_extractor/eval_rubric.md`
- `integration/scripts/build_knowledge_units.py`
- `tests/test_knowledge_unit_extraction.py`

**Action**

- 输入仅来自 evidence-eligible bundles；每个 bundle 明确 allowed refs、speaker roles 和 lifecycle state。
- 使用 AI-SPEC 中的 Pydantic contract，`extra=forbid`；解析成功后再验证每个 evidence ref 属于当前 bundle 且 DB 可回查。
- preference/habit/personal fact 若无 user-authored evidence，必须 reject/abstain。
- 默认 model config 为 `gpt-5.6-luna`、temperature 0；模型不可用时写 blocked report，不静默 fallback。
- 原始 LLM response 按 input/prompt/model hash 缓存，产物只先进入 staging。

### Task 2.2 — Extraction quality gate

**Files**

- `integration/scripts/evaluate_knowledge_unit_extraction.py`

**Gate — Abort/Revision**

- JSON/Pydantic schema 有效率 ≥95%。
- invalid/foreign evidence ref = 0。
- 抽查至少 20 units，evidence support ≥90%。
- user-fact speaker misattribution = 0。
- secret/deleted/excluded evidence = 0。
- 总失败率 >10% 时 abort，不写 current。

## Wave 3：Canonicalization 与 Hard-negative Gate

### Task 3.1 — 候选聚类与 merge proposal

**Files**

- `integration/prompts/knowledge_unit_merger/v1_main.md`
- `integration/prompts/knowledge_unit_merger/v1_schema.md`
- `integration/scripts/build_canonical_knowledge_units.py`
- `tests/test_canonical_knowledge_units.py`

**Action**

- 先按 subject、unit_type、speaker eligibility 和时间兼容性分桶，再做 embedding candidate search。
- question+answer 共同参与相似度；禁止跨 subject 贪婪聚类。
- 0.70–0.85 相似候选作为 hard-negative review pool；0.85 只是 proposal 阈值，不是自动 merge 结论。
- merge 后 confidence 取 members 最小值；conflict 写 draft/review，不自动 current。
- 保留 member links、merge reason、supersedes/version lineage。

### Task 3.2 — Merge evaluation

**Gate — Revision**

- 20 hard negatives 中 false merge = 0。
- 20 positive pairs merge recall ≥80%。
- 跨 subject、角色不合格或时效冲突自动合并 = 0。
- 不再要求 canonical row count 必须小于 unit count；无自然重复时相等是合法结果。

## Wave 4：Candidate Index、Frozen-test A/B 与 Atomic Promote

### Task 4.1 — 构建版本化 candidate collection

**Files**

- `integration/scripts/build_knowledge_unit_vector_store.py`
- `tests/test_knowledge_unit_vector_store.py`

**Action**

- collection 命名包含 build ID；向量化文本为 question+answer，metadata 保存 canonical ID/type/subject/status/version。
- 只索引 `status=current` 且 evidence gate passed 的 canonical units。
- exact reconcile：collection IDs 必须等于 eligible canonical IDs，missing/orphan/duplicate 均为 0。
- 不覆盖 active pointer。

### Task 4.2 — Frozen-test A/B 和 promote

**Files**

- `integration/scripts/evaluate_knowledge_unit_rag.py`
- `integration/scripts/promote_knowledge_index.py`
- `integration/scripts/rollback_knowledge_checkpoint.py`
- `tests/test_knowledge_index_promotion.py`

**Gate — Launch**

- frozen test Recall@5、MRR@5 均不低于 raw baseline。
- grounded/relevant Top-1 ≥85%。
- deprecated/secret hit = 0。
- no-answer/hard-negative false positive ≤10%。
- 至少一个核心质量指标相对 raw baseline 提升 ≥10 个百分点；否则保留 raw 默认。
- promote 使用原子 active pointer。
- rollback 必须联合恢复 canonical/current DB checkpoint、active collection pointer 和对应 build manifest；恢复后 exact reconcile 的 missing/orphan/duplicate 均为 0。
- 联合 rollback smoke test 必须通过，不能只验证 pointer 字符串发生变化。

## Wave 5：Retrieval Interface、Canary 与 Feedback

### Task 5.1 — 扩展统一检索接口

**Files**

- `integration/scripts/search_vectors.py`
- `integration/scripts/unified_search.py`
- `integration/scripts/api_server.py`
- `integration/scripts/mcp_server.py`
- `tests/test_knowledge_search_contracts.py`

**Action**

- 新增 `search_knowledge_units(query, top_k, filters, include_evidence)`。
- active knowledge index 优先，raw collections 作为显式 fallback；响应说明 route、index version 和 evidence refs。
- evidence 无法回查时不生成“可信答案”，返回 fallback/abstain 状态。

### Task 5.2 — 本地 run/feedback tables 和 canary

**Files**

- `integration/scripts/migrate_add_rag_feedback_tables.py`
- `integration/scripts/evaluate_knowledge_canary.py`
- `tests/test_rag_feedback_privacy.py`

**Action**

- 新增 `rag_runs/rag_retrieval_items/rag_feedback`，只记录必要的 query hash、IDs、scores、route、latency、versions 和 label。
- 默认不保存原始 query；不得保存 secret session 内容。
- canary 至少 30 个真实 query，人工 label `helpful|wrong|stale|missing`。

**Gate — Canary**

- helpful ≥80%。
- critical wrong/stale = 0。
- fallback rate ≤30%。
- warm p95 latency ≤ raw baseline 2 倍。
- 失败则 rollback active pointer，raw 仍为默认。

## Wave 6：Incremental Refresh 与 Lifecycle Closure

### Task 6.1 — 受影响 subject 增量重建

**Files**

- `integration/scripts/refresh_knowledge_units.py`
- `integration/scripts/reconcile_knowledge_index.py`
- `tests/test_knowledge_incremental_refresh.py`

**Action**

- 使用 Phase 13.5 canonical conversation build delta 和 unified event watermark 定位受影响 bundles/subjects。
- 新证据只重建受影响 subject；周期 full reconcile 兜底。
- deleted/excluded/deprecated 传播到 unit、canonical 和 active index；一次 refresh 内移除索引残留。
- wrong/stale/missing 只进入 dev/hard-negative backlog，不修改 frozen test。

### Task 6.2 — Memory lifecycle compatibility

**Files**

- `integration/scripts/migrate_memory_lifecycle.py`
- `integration/scripts/sync_memory_lifecycle.py`
- `tests/test_memory_lifecycle_sync.py`

**Action**

- 为 memory_items 增加 status/version/last_seen/canonical_unit_id，但默认只 dry-run link proposal。
- 写入前展示影响清单并要求显式 `--write`；只标记 deprecated，不物理删除。

**Gate — Continuous**

- 同输入二次运行 DB/index diff = 0。
- 新事件只改变受影响 subjects。
- deprecated/deleted/excluded 在一次 refresh 后索引残留 = 0。
- rollback 到上一个 build 后 frozen smoke set 仍通过。

</tasks>

<verification>
## Phase Verification

```powershell
python -m pytest -q tests\test_knowledge_unit_eval_dataset.py tests\test_knowledge_unit_contracts.py
python integration\scripts\evaluate_knowledge_unit_rag.py --dataset raw-baseline
python integration\scripts\build_knowledge_units.py --dry-run --limit 50 --model gpt-5.6-luna
python -m pytest -q tests\test_knowledge_unit_checkpoint.py tests\test_knowledge_unit_extraction.py tests\test_canonical_knowledge_units.py
python integration\scripts\build_canonical_knowledge_units.py --dry-run
python integration\scripts\build_knowledge_unit_vector_store.py --dry-run
python -m pytest -q tests\test_knowledge_unit_vector_store.py
python integration\scripts\evaluate_knowledge_unit_rag.py --dataset frozen-test --candidate latest
python -m pytest -q tests\test_knowledge_index_promotion.py tests\test_knowledge_search_contracts.py
python integration\scripts\rollback_knowledge_checkpoint.py --to previous --dry-run
python integration\scripts\evaluate_knowledge_canary.py --report-only
python -m pytest -q tests\test_rag_feedback_privacy.py tests\test_knowledge_incremental_refresh.py tests\test_memory_lifecycle_sync.py
python integration\scripts\run_pipeline.py --dry-run
```
</verification>

<success_criteria>
## Success Criteria

- Phase 13.5 canonical evidence 与隐私/speaker eligibility contract 被完整继承。
- dev/frozen/hard-negative datasets 存在、可回查、无 split leakage。
- 所有 LLM 输出经过 Pydantic、evidence 和 speaker gate；无证据不得 current。
- staging/checkpoint/promotion/rollback 均有自动测试，失败 build 不破坏旧 active index。
- canonical merge 在 hard negatives 上 false merge=0。
- frozen-test retrieval 不低于 raw baseline，并至少一个核心指标提升 ≥10 个百分点。
- canary 通过 helpful/critical-error/latency/fallback gates 后才切默认检索面。
- incremental refresh、deprecated/delete 传播和 exact index reconcile 通过。
- raw collections 和 legacy memory 保留，fallback 经验证。
</success_criteria>

## PLANNING COMPLETE
