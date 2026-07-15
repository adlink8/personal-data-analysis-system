---
phase: 19
name: physical-source-consolidation
status: planned
depends_on: [18]
requirements: [PHY-01, PHY-02, PHY-03, PHY-04, PHY-05, PHY-06, PHY-07, PHY-08]
---
# Phase 19 Context

目标是实际改变 tracked source 的物理位置，不再以逻辑 zone 代替搬迁。目标根：`src/personal_knowledge/`、`apps/`、`assets/`、`tools/`、`tests/`、`docs/`、`governance/`。

锁定：`integration/scripts/*.py` 最终为 0；正式命令由 pyproject console scripts 提供；旧 shim 不删除，先移入 `tools/compat/v1_1/`；每 cohort 有 manifest/inverse、consumer=0、parity、full tests。不得触碰 Agent/Google/imports/db/runtime/analysis/_recycle，数据物理迁移属于 Phase20。

所有写操作必须遵守 `19-MIGRATION-SPEC.md`。Phase17 评测代码/fixtures/tests 路径随源码迁移同步更新，自动验证重跑，但 Phase17 human checkpoints 保持 open。
