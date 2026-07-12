# Knowledge Unit Eval Datasets

Phase 14 Wave 0 的评估数据集。用于 dev tuning、frozen-test A/B、merge 评估和 hard-negative 校验。

## Schema

每个 case 是一行 JSONL：

```json
{
  "id": "dev-001",
  "split": "dev|frozen_test|merge_positive|hard_negative",
  "query": "用户用什么 shell？",
  "gold_evidence_refs": ["cm|..."],
  "allowed_unit_types": ["preference", "personal_fact"],
  "expected_abstain": false,
  "expected_conflict": false,
  "group": "preference|project_decision|capability|time_conflict|deprecated|no_answer|assistant_only|subagent_only|secret_ineligible|cross_source_dup"
}
```

## Splits

| Split | 数量 | 用途 | 修改规则 |
|-------|------|------|----------|
| dev | 20 | 调优 prompt/参数 | 可自由修改 |
| frozen_test | 20 | A/B gate | 确认后不再由 pipeline 修改 |
| merge_positive | 20 | canonical merge recall | 验证应合并的 pair |
| hard_negative | 20 | merge false-positive | 验证不应合并的 pair |

## 场景覆盖

- **preference**：用户偏好（shell、语言、输出格式）
- **project_decision**：项目架构/技术选型决策
- **capability**：用户技能/能力使用
- **time_conflict**：同一 subject 不同时间矛盾结论
- **deprecated**：旧结论已被替代
- **no_answer**：无足够证据，应 abstain
- **assistant_only**：只有 assistant 内容，不能证明用户事实
- **subagent_only**：只有 subagent 内容，不能证明用户事实
- **secret_ineligible**：secret-bearing session，不可检索
- **cross_source_dup**：跨 source 重复，应折叠

## 文件

- `dev_queries.private.jsonl` — dev 查询（本地，不入 Git）
- `frozen_test_queries.private.jsonl` — frozen test 查询（本地，不入 Git）
- `merge_positive_pairs.private.jsonl` — 应合并的 pair（本地）
- `hard_negative_pairs.private.jsonl` — 不应合并的 pair（本地）
- `synthetic_cases.jsonl` — synthetic test cases（入 Git，供 CI 使用）

## 泄漏检查

按 subject/source/time group 检查 dev 与 frozen_test 之间无泄漏。frozen test 一旦确认不再由 pipeline 自动修改。

## 重建方法

```powershell
# 从 canonical store 重建真实 datasets
python integration/scripts/build_knowledge_unit_eval_datasets.py --write
```
