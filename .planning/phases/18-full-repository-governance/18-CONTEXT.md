---
phase: 18
name: full-repository-governance
status: complete
milestone: v1.1
depends_on:
  - "17-code-baseline"
requirements: [GOV-01, GOV-02, GOV-03, GOV-04, GOV-05, GOV-06, GOV-07, GOV-08, GOV-09, GOV-10, GOV-11, GOV-12]
---

# Phase 18 Context: Full Repository Governance

<decisions>
- **D-18-01:** 治理覆盖根目录到最深叶文件，但通过 ordered policy inheritance + generated metadata inventory 实现，不为每个叶目录手写 README。
- **D-18-02:** `.planning/` 是唯一规划事实源；`.gsd/` 只读历史，不再双写。
- **D-18-03:** 所有路径先逻辑分类，再做物理迁移；物理 move/archive/delete 必须 preview、人工批准和 rollback。
- **D-18-04:** 私有正文不进入治理清单；R3/R4 只记录路径类别、hash、size、mtime、owner、lineage 等 metadata。
- **D-18-05:** 现有 86 个 compatibility shim 与 legacy 债务采用 baseline-only-down，不要求一次删除。
- **D-18-06:** 根 README 只做导航；稳定模块有 README；叶文件由 inventory 保证覆盖。
- **D-18-07:** source/test/private/generated/runtime/vendor/archive 依赖方向由自动门验证。
- **D-18-08:** Phase 17 尚有人工作业，Phase 18 不能把它改写为 complete。
</decisions>

## Baseline

- metadata scan：约 11,106 files、4,589 dirs、最大深度 18、约 5.8GB（排除 `.git` 和常见缓存）。
- `_recycle` 约 9,210 files / 4.25GB；imports 约 551MB；Agent 约 553MB。
- 473 tracked；约 65–67 untracked entries；86 compatibility shims；22 `_tools` 探针/迁移脚本。
- 多个稳定模块没有 README；存在用户名/Desktop/GCP SDK/embedding 固定路径。
- pytest 全绿，但 CI 缺 Node、3.14、依赖锁、安全、inventory 与 planning drift 门。

## Safety boundary

默认只生成清单、规则、报告和 preview。对 `_recycle`、Google/raw、imports、Agent/structured、integration/db/runtime/analysis 等路径不得读取或输出私人正文；删除、归档、移动、生产写入均需独立人工 checkpoint。

## Phase 17 concurrency boundary

18-01..05 仅依赖 Phase 17 已完成的代码/测试 baseline，可与人工 gold、judge calibration、UAT 并行。18-06 若触碰 evaluation/promotion/active paths，必须等待 Phase 17 UAT 签收；其他 docs/config/source cohort 可单独批准。任何检查不得把 Phase 17 标记 complete。
