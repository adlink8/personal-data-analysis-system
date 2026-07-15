---
phase: 20
name: physical-data-runtime-relocation
status: planned
depends_on: [19]
requirements: [DATA-01, DATA-02, DATA-03, DATA-04, DATA-05, DATA-06, DATA-07, DATA-08]
---
# Phase 20 Context

目标物理树：`data/{raw,staging,canonical,imports}`、`var/{db,runtime,reports,logs}`、`archive/{quarantine,planning,vendor-reference}`。外部 `%USERPROFILE%/.agentsview/sessions.db` 永不搬，只读。每个R3/R4 cohort必须独立审批；禁止直接Move-Item大目录，必须snapshot/stage-copy/validate/atomic cutover/alias/rollback。

迁移合同以 `20-MIGRATION-SPEC.md` 为强制规范。全节点 disposition 覆盖率必须 100%；`.agents/.codex/.workbuddy/.github/.planning/governance` 与根工具配置因运行时约定保留原位，不属于遗漏。
