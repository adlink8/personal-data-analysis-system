---
phase: PDA-43-l2-scope-redefinition-cross-turn-state-ownership-and-increme
plan: 07
status: partial
---

# 43-07 Summary

新增隔离 SQLite 双 run 集成测试，验证 v1 平行 current、v2 注入后的 `supersedes_id` 候选、非法引用计数和状态 subject candidate 路由；全程不触碰 canonical 数据库。测试文件：`tests/integration/test_l2g01_dedup_gate.py`，3 个场景通过。

真实 Vertex 双 run 实验驱动尚未对生产数据执行：当前 Phase 43 的历史目标集已发生状态迁移，先完成 43-08 历史快照分级并保留 dry-run 治理台账，避免把旧 ID 当作当前 staging 直接处置。
