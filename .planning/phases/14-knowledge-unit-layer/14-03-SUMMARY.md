---
phase: 14-knowledge-unit-layer
plan: "03"
type: execute
wave: 2
status: complete
requirements: [KU-03, KU-05, KU-06]
completed: 2026-07-10
---

# Phase 14 Plan 03 Summary: Pilot & Canonicalization

**400 条分层 pilot 完成（171 succeeded, 341 units），canonicalization 产生 346 canonical units（5 merged, hard-negative false merge=0），evidence 审核 20/20 (100%) 通过。**

## Accomplishments

### Task 1: 冻结分层 pilot
- 400 条从 2,159 authoritative inventory 按 agent × length × injection 分层采样，覆盖 31 strata
- fake LLM 故障演练：正常/cache replay/429/500/503/timeout/invalid JSON/foreign ref 全覆盖
- 12 tests passed

### Task 2: 人工 checkpoint
- 用户批准 gemini-3.5-flash（AI-SPEC 锁定 gpt-5.6-luna 无 API access）
- preflight report 记录实际 model/sample hash/预算

### Task 3: 真实 pilot + canonicalization
- **400 条 pilot**：171 succeeded + 1900 abstained（含非 pilot 的 1759 条）+ 88 terminal_failed（429 限流）
- **341 knowledge units**：personal_fact 152 / project_decision 82 / preference 55 / habit 29 / tool_usage 15 / capability 10
- **schema 99.95%**，speaker/privacy/evidence critical errors = 0
- **中断恢复验证**：3 次 kill → resume，0 重复调用
- **canonicalization**：351 units → 346 canonical（5 merged, 341 singletons, 0 conflicts）
- **merge gate**：hard negative false merge = 0 ✓；positive recall 待全量后用真实 unit pairs 重建
- 14 canonicalization tests passed

### Task 4: 人工 evidence 审核
- 20 units 随机抽样审核
- evidence support: 20/20 (100%，10 字片段匹配)
- speaker attribution: 0 errors
- privacy: 0 violations
- **production thresholds 预注册**：min_yield=25%, schema≥95%, failure≤10%, concurrency=1, retry=4

## Verification Evidence

| Evidence | Result |
|---|---|
| Pilot tests (sample + fault matrix) | 12 passed |
| Canonicalization tests | 14 passed |
| Full Plan 02-03 suite | 78 passed |
| Pilot sample size | 400 (31 strata) |
| Pilot succeeded | 171/400 (42.75%) |
| Knowledge units | 341 |
| Canonical units | 346 (5 merged) |
| Hard negative false merge | 0 |
| Schema validity | 99.95% |
| Evidence support (20 reviewed) | 100% |
| Speaker/privacy errors | 0 |
| Resume after 3 kills | 0 duplicate calls |

## Production Thresholds (预注册)

| Parameter | Value |
|-----------|-------|
| minimum_yield | 25% |
| schema_valid_rate | ≥95% |
| overall_failure_rate | ≤10% |
| concurrency | 1 |
| retry_max | 4 |
| base_backoff | 2.0s |
| max_backoff | 60.0s |
| rate_limit_interval | 2s/item |

> 阈值在看到全量结果后不得下调。

## Issues

- 88 terminal_failed (429 限流)：Vertex AI 项目配额耗尽，全量 run 需要更大配额或更慢速率
- merge positive recall = 0：eval pairs 用 conversation message ref 而非 unit ID，需在全量抽取后用真实 unit pairs 重建
- lifecycle CHECK constraint crash：LLM 返回非白名单 lifecycle 值，已修复（归一化为 "current"）

## Next Phase Readiness

- Plan 14-04 可执行全量 backfill（2,159 条），但需解决 429 限流
- Production thresholds 已预注册，不可事后调整
- Canonicalization pipeline 在 pilot 数据上通过 hard-negative gate
