---
phase: 43-l2-scope-redefinition-cross-turn-state-ownership-and-increme
plan: 06
subsystem: lifecycle-query
tags: [history, current-only, supersede-chain, l2g-03]
requirements-completed: [L2G-03]
completed: 2026-07-28
---

# 43-06 执行摘要

## 结果

`pk-ku history --subject` 现在通过派生字段 `is_current_value` 标注 supersede 链中的当前值，JSON 与表格输出均可读；未新增 SQLite/Chroma schema 字段。`rag-search semantic` 增加 `--current-only` 显式契约，但保持现行行为：active 索引和知识层本来就只放行 `lifecycle=current`。

## D-07 替代实现待用户确认

本计划采用“排除非 current = 极限降权”的最小实现，而不是把历史值重新纳入索引后做分数降权。理由是当前索引构建与检索过滤均为 current-only；若未来需要在语义检索中返回历史值并降权，应另开索引重建、canary、eval 与 promote 变更。本偏离 D-07 字面“降权”要求，Phase 43 收尾时需由用户确认，不静默视为等价。

## 验证

- `tests/unit/test_history_knowledge_units.py`、`tests/contract/test_knowledge_search_contracts.py`、`tests/unit/test_vector_store_filter.py`：通过。
- `rag-search semantic --help` 已显示 `--current-only`。
- 当前值标注、参数透传与空查询 fail-closed 契约已覆盖。
