---
phase: 27-proactive-multi-domain-intelligence-and-target-d-acceptance
status: issues_found
depth: deep
files_reviewed: 22
findings:
  critical: 3
  warning: 3
  info: 0
  total: 6
release_status: release_blocked
technical_status: failed
reviewed_at: 2026-07-18
---

# Phase 27 / Target D Deep Code Review

## Verdict

Phase 27 的既有 77 项 proactive/Target D 测试全部通过，但深度审查发现 3 个 Critical 与 3 个 Warning。当前实现不能据此声明 Target D 技术验收完成；Phase 24 的人工质量与 lifecycle 门禁仍保持原状，产品发布继续为 `release_blocked`。

## Critical findings

### CR-01 — Target D sandbox 用硬编码布尔值替代了所声明的端到端证明

**位置：** `src/personal_knowledge/intelligence/proactive/cli.py:110-121,136-148`

`_technical_sandbox()` 只调用 Phase 26 sandbox，然后在内存中执行 `rank_candidates()` / `evaluate_candidates()`。它没有创建 disposable SQLite authority、没有调用八域 `coordinate_goals()`、没有发布 Phase 27 run、没有追加/恢复 control、没有触发 stale append，也没有经过 shared read/explain。尽管如此，`state_change_history`、`ranking_and_noise`、`trust_control_and_restore`、`future_run_after_restore`、`shared_read_explain` 及 control rollback 结果均被直接写成 `True`。同时，live acceptance 对已应用的 Phase 25/26 只检查表是否齐全；没有验证其 manifest/checksum/snapshot/event frontier，Phase 27 已应用但零候选时也可由空 inbox 返回成功。

**影响：** coordination、controls、publication 或上游 authority 即使损坏，`technical_status` 仍可能是 `passed`。这直接违反 TD-01 的“完整 disposable sandbox + partial/corrupt/mixed-version fail closed”退出条件。

**要求：** sandbox 必须实际建立并执行完整 Phase 25→26→27 链，所有 stage result 从执行结果计算；live applied 状态必须验证上游 run/manifest/checksum/snapshot/frontier，不能只按表存在性判定。补充故障注入测试，证明任一阶段失败会令 `technical_status=failed`。

### CR-02 — 形成冲突的 ResourceClaim 证据从未做 snapshot/run/record 校验

**位置：** `src/personal_knowledge/intelligence/proactive/coordination.py:90-110`; `src/personal_knowledge/intelligence/proactive/runs.py:173-190`

协调逻辑使用 `ResourceClaim.source` 证明共享资源与超额容量，但 cross-snapshot/cross-version 检查只比较 `GoalSignal.support`。生成 `CoordinationDraft` 时，`source_refs` 也只包含两个 goal support；`plan_run()` 仅 `_validate_ref()` 这些 `source_refs`，并未校验 `resource_manifest[*].source`。

一次性 fixture 已复现：两个 goal support 都在 `ss1`，两个 resource source 均改为不存在的 `other-snapshot` 记录，`coordinate_goals()` 仍产出 `goal_conflict`，且 draft 的已验证 `source_refs` 不包含这些资源记录。

**影响：** 缺失、陈旧、跨快照甚至伪造的资源声明可以成为“目标冲突”的决定性依据并进入不可变发布，破坏 PRO-01 的证据谱系、隐私与 fail-closed 合同。

**要求：** 将每个决定性 ResourceClaim source 纳入 canonical support manifest，并在协调和事务内发布阶段验证 authority/type/record checksum/source run/snapshot；同一共享资源还应有可验证的资源身份，而不只是相同 type/unit/horizon。

### CR-03 — exact replay 完整性检查遗漏 proactive_candidate_support

**位置：** `src/personal_knowledge/intelligence/proactive/runs.py:321-339`

`_validate_existing()` 校验 run、coordination、candidate 与 evaluation，却完全不读取 `proactive_candidate_support`。一次性 fixture 已复现：发布合法 run 后仅移除 support immutable-delete trigger 并删除全部 support 行，再次 `publish_run(..., write=True)` 返回 `ok=True, existing=True`。

**影响：** 证据链缺失或被篡改的既有 run 会被 exact replay 错误接受；摘要中“support/evaluation atomic publication and tamper checks”的保证不成立。

**要求：** replay 时重建每个候选的完整 support 集合，逐项校验 payload/column/checksum、source record 及 run/snapshot 绑定，并与 `run.candidates[*].support_refs` 精确比较。增加缺行、额外行、payload tamper、record drift 四类回归测试。

## Warning findings

### WR-01 — 未来 restore 会追溯性撤销历史 `as_of` 状态

**位置：** `src/personal_knowledge/intelligence/proactive/controls.py:240-247`

`restored` 收集所有 restore event，不先按 `created_at <= as_of` 过滤。复现中 suppress 发生于 12:00、restore 发生于 13:00；查询 12:30 却返回 `eligible=True`，历史 suppression 被未来补偿事件抹除。

**影响：** 显式 `as_of`、审计历史与“restore 只改变未来 projection”的合同被破坏。

**要求：** 只让投影时点已经生效的 restore 撤销原事件，并补充 restore 前、边界时刻、restore 后三点测试。

### WR-02 — scope specificity 可把 global target 提升到 exact-target 同级

**位置：** `src/personal_knowledge/intelligence/proactive/controls.py:234-237`

specificity 使用 `max(target_rank, scope_rank)`。因此 `global` target 配普通具体 scope 会得到 4，与 exact candidate target 相同；同级 denial 优先后，global suppression 可覆盖 exact candidate allow/limit。一次性 fixture 已复现该结果。

**影响：** 违反 TRUST-01 明确要求的 exact-target > policy/domain/global precedence，用户的精确控制可能被较宽控制错误覆盖。

**要求：** 用 target specificity 作为首要排序维度，scope specificity 仅作为次级维度；覆盖 exact-vs-global、exact-vs-domain、policy-vs-domain 及同级 denial 的矩阵测试。

### WR-03 — 任一 control append 后，现有候选的所有读接口立即失效

**位置：** `src/personal_knowledge/intelligence/proactive/service.py:102-127,220-227`

`_run()` 要求当前全局 control frontier 与候选所属 run 的历史 frontier 完全相等。control 追加后，`controls.status` 先调用 `_candidate()`，因此连刚写入的控制历史也无法读取。复现中合法 suppress append 后，`controls.status` 返回 `control_frontier_changed`。

**影响：** 本地 CLI 允许用户写控制，但写完后 inbox/get/explain/controls-status 全部不可用，直到另行生成新 proactive run；runbook 未说明此强制重算，shared trust-control 接口无法形成可用闭环。

**要求：** 区分“历史 run 自身绑定已验证”和“当前 control overlay”。读取候选时验证其 immutable frontier 内容未被篡改，再在当前 frontier 上投影 controls；至少 `controls.status` 必须能读取并校验当前 append-only stream。增加 append 后 get/status、restore 后 status、旧 run lineage 保留测试。

## Evidence

- 自动化回归：`python -m pytest` 覆盖全部 proactive/Target D 指定测试，**77 passed**。
- 额外一次性 fixture：确认 CR-02、CR-03、WR-01、WR-02、WR-03 均可复现。
- 未运行 live migration，未执行 live write，未修改 Phase 24 checkpoints、KU/lifecycle、serving、pointer 或 watermark。

