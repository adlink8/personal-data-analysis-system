---
phase: 17
system_type: rag-evaluation-and-release-gate
framework: existing-python-sqlite-chroma
status: planned
---

# AI-SPEC: Knowledge Unit Evaluation System

## System contract

输入为版本化 dataset snapshot、mode manifest、collection IDs、retrieval config、answer model/judge config；输出为不可变 eval run、逐题 trace、汇总指标、gate decision 与脱敏可视化。

## Evaluation matrix

| Layer | Modes | Primary metrics |
|---|---|---|
| extraction | L1, L2 | schema, grounded precision, duplication, cross-turn necessity, conflict/temporal/privacy |
| retrieval | raw, l1, l2_only, l1_l2, hybrid | R@1/5/10, MRR@5, nDCG@5, scenario scores, latency |
| answer | all retrieval modes where meaningful | correctness, faithfulness, citation precision/recall, abstain |
| operations | candidate vs active | count/checksum reconcile, p95, gate, promote/rollback |

## Scoring rules

- Stable ID/evidence match is primary; normalized semantic labels are secondary; substring-only match单独报告，不进入核心泛化分数。
- `expected_abstain=true` 时任何未经阈值过滤的事实回答计 false positive。
- Hybrid 每题记录 first layer 与各层贡献，分别给出 system score 与 KU-attributed score。
- 提升同时输出绝对 delta、相对百分比和 bootstrap 95% CI；样本不足时明确 `insufficient_evidence`。

## Pre-registered primary claims

只有同时满足下列条件，报告才能写“知识单元模式相对 Raw 已证明提升”；否则必须写“未证明提升”或“证据不足”：

1. Primary retrieval：`L1+L2 vs Raw Recall@5` 绝对提升至少 **+10pp**，paired bootstrap 95% CI 下界 > 0。
2. Ranking：`MRR@5` 非劣于 Raw（95% CI 下界 >= -2pp）。
3. Primary answer：answer correctness 绝对提升至少 **+5pp**，且 faithfulness/citation precision 非劣于 Raw。
4. Privacy/secret hard gate = 0；no-answer FP、citation 与 latency 均满足 gate。

L2 的独立 claim 为 cross-turn Recall@5 相对 L1 至少 +10pp，CI 下界 > 0；若旧 frozen 回退但跨轮显著提升，报告必须同时展示 trade-off，不得只宣称总体提升。

## Statistical protocol v1

- Paired resampling unit：`query_id`；同一 query 的不同 mode 始终成对抽样。
- Bootstrap：seed `1701`，10,000 resamples，percentile 95% CI。
- 多场景指标为诊断项；primary claims 固定为上节三项，避免多重比较挑选正结果。
- Judge calibration：至少 30 cases × 5 paired answers；使用 Spearman rho 与 pass/fail Cohen's kappa，二者至少一项 >=0.7 且无系统性 privacy 分歧才可入 gate。

## Initial gates (v1)

| Gate | Threshold |
|---|---|
| secret/privacy hit | 0 |
| evidence/citation precision | >= 0.95 |
| existing frozen Recall@5 regression | 不低于 active 超过 2pp；若样本不足则不得自动 promote |
| cross-turn L2 Recall@5 | 相对 L1 >= +10pp，且至少 30 个 gold cases |
| no-answer false-positive rate | <= 0.10 |
| grounded L2 human sample precision | >= 0.90，至少 50 units 或全量（取较小） |
| p95 retrieval latency | 不高于 active 25% |
| reconcile | missing=0, orphan=0, checksum match |

阈值必须在首轮 baseline 后冻结为 `eval_policy_version=v1`；调整必须产生新版本，不能覆盖旧结果。

## Judge policy

- 人工金标是校准源。
- LLM judge 只评分 correctness/faithfulness 等主观维度；保存 provider/model/prompt/rubric 版本。
- judge 与人工在校准样本上相关性/一致率未达 0.7 时仅展示，不参与 gate。
- judge 输入按最小证据片段组装，不发送整库或整段历史。

## Observability and privacy

逐题记录 query_id、mode、rank、stable IDs、scores、latency、layer attribution 和 judge result；默认不保存原始 query/evidence 正文到报告。HTML 只展示脱敏摘要和 ID，可在本机受控 drill-down。
