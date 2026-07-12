---
phase: 14-knowledge-unit-layer
plan: "02"
type: execute
wave: 1
status: complete
requirements: [KU-01, KU-02, KU-03, KU-05]
completed: 2026-07-10
---

# Phase 14 Plan 02 Summary: Production Backfill Engine

**冻结 inventory 解释了 5,485/3,248/2,159 的差异；可恢复、可缓存、失败封闭的 production extraction engine 通过 38 项测试和 5 条真实小样本验证。**

## Accomplishments

### Task 1: 冻结 production inventory
- 新增 5 张表：`knowledge_inventory`、`knowledge_inventory_items`、`knowledge_run_items`、`knowledge_response_cache`、`knowledge_extraction_gates`
- `build_knowledge_inventory.py`：从 canonical store 生成权威有序 inventory
- **Count 解释**：SQL 粗筛 3,248 → 清洗去重后 2,159（排除 758 短消息 + 253 重复 + 78 仅注入）
- inventory_id 由 source_checksum + dataset_hash 派生，resume 时 drift 检测
- 隐私安全报告（只含 count/hash，无原文）

### Task 2: 可恢复 batch + 分类 retry + 内容寻址 cache
- `build_knowledge_units_prod.py`：production backfill engine
- `--start --inventory <id>` / `--resume <run_id>` 显式入口
- item 状态机：pending → in_flight → succeeded/abstained/retryable/terminal_failed
- 过期 lease 恢复为 retryable
- cache key：model|prompt_hash|schema_hash|input_hash|config_hash
- cache hit 仍重跑 Pydantic/evidence/privacy gate
- 分类 retry：429/500/503/timeout 重试 + jitter + Retry-After；400/401 fail-fast
- run-scoped token provider（401 自动刷新）
- SQLite 单 writer（worker 返回纯响应，主线程提交）
- resume 不调用 begin_staging（不删除已完成结果）

### Task 3: 严格 extraction gate
- `evaluate_knowledge_unit_extraction.py`：fail-closed gate
- 10 项 gate 检查：snapshot/api/nonzero/yield/schema/failure/evidence/speaker/privacy/reproducibility
- 无 min_yield → `awaiting_pilot_threshold`（不是 PASS）
- gate passed 写 `validated`（不是 `current`）
- 全 API 失败时 gate FAIL（关键安全测试）
- 不改 canonical current 或 active pointer

## Verification Evidence

| Evidence | Result |
|---|---|
| Plan 02 tests (backfill + retry_cache + gate) | 38 passed |
| Full Phase 14 suite | 78 passed |
| Repository full suite | 248 passed (2 pre-existing failures unrelated) |
| Inventory authoritative count | 2,159 |
| Small-sample --start --limit 5 | 3 succeeded, 2 abstained, 0 failed, 10 units |
| Gate (no min_yield) | awaiting_pilot_threshold (all critical passed) |
| Resume | 0 items reprocessed (no duplicate calls) |
| Active pointer unchanged | knowledge_units_a89ebe470357 |

## Explicitly Not Completed by Plan 02

- Pilot 300–500 items with stratified sampling（Plan 14-03）
- Production minimum-yield 固化（pilot 后）
- 全量 backfill 2,159 条（pilot 后）
- Canonicalization（Plan 14-04）
- Canary / retrieval / lifecycle（Plan 14-05/06）

## Key Decisions

- Inventory authoritative count = 2,159，不硬编码 5,485
- `validated` 状态与 `current`/`active` 严格隔离
- Model 从 CLI 注入，写 manifest，不可用则 abort
- Cache hit 仍重新验证（不盲信旧解析结果）

## Next Phase Readiness

- Plan 14-03 可在同一合同上安全运行 300–500 分层 pilot
- Engine 支持 --start/--resume/cache/retry，可安全中断续跑
- Gate 失败封闭，任何 critical violation 都不会 PASS
