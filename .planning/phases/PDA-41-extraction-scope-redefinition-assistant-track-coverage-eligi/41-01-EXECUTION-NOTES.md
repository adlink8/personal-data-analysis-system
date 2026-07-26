# 41-01 执行笔记：eligible 口径唯一化

**执行时间：** 2026-07-26（UTC）

## verification 结果

1. `pytest tests/unit/test_knowledge_eligibility.py tests/unit/test_knowledge_unit_extraction.py tests/unit/test_knowledge_unit_gate.py tests/unit/test_knowledge_unit_prod_evidence.py tests/unit/test_inventory_registry_migration.py -q` → 全过（exit 0）
2. 迁移脚本：dry-run（影响 41,605 行；按 ref 分布 assistant 30,439 / user 3,627 / unresolved 936）→ `--write`（回填 40,526 行 + 1,079 行 'unknown'，备份 var/backups/personal_system_20260726T041952Z.sqlite）→ 再跑 `no_op`。`GROUP BY role`：assistant 36,286 / user 4,240 / unknown 1,079，无 NULL。
3. `pk-ku inspect`（真实库首次切换）：**source_changed=False, no_op, new_refs=0**——未出现 R6 预期的 delta 突增。原因：inspect 的 checksum 短路优先于 refs 比对，当前 source checksum 与 committed watermark 一致，直接 no_op。口径切换本身不改变 source checksum；**delta 突增将在下一次真实内容同步后出现，届时属口径修正（R6）不是数据事故，不触发 Gate B STOP**。
4. `pk-ku doctor --skip-ports` → exit 0。
5. `python -m pytest tests/unit -x -q --tb=short` → 518 passed，exit 0。
6. 受影响集成测试回归：`tests/integration/test_knowledge_incremental_refresh.py` + `test_knowledge_prepare_floor.py` → 11 passed。

## 偏差记录

- **既有测试夹具适配**：`knowledge_inventory_items` 加 `role` 列后，8 处 positional INSERT 夹具（test_knowledge_unit_gate/vector_store/retry_cache/pilot/canonical_knowledge_units、integration test_knowledge_incremental_refresh）必须补第 13 个值（'user'）；integration fixture 的 canonical 表补 agent/started_at/source 列（eligibility SQL 需要）。属 schema 变更的必然适配；旧 import 路径本身零修改保持可用。
- prepare 的 `order_keys`（started_at）与 `ref_roles` 一并从 eligible 集合派生（同一兜底分支），plan 只点名 ref_roles；行为与旧 SQL 结果一致。
- `_current_eligible_ref_hashes` 返回的 meta 改为 eligibility stats（含 inventory_id/source_checksum/dataset_hash/ref_roles/ref_started_at/cleaned_len），保持 `exclude_inventory_id` 语义不变。
- `pk-ku prepare --dry-run` 需 `--model` 未在真实库执行；验收由 prepare 路径测试 + `test_inventory_write_to_db`（新 schema 含 role 列）+ 真实库 PRAGMA 探测（列已存在）覆盖。
