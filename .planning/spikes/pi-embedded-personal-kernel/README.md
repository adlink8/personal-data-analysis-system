---
spike: PIK
name: pi-embedded-personal-kernel
type: standard
validates: "Given the existing deterministic person-data authorities, when Pi SDK is embedded as the AI runtime, then it remains tool-confined, event-driven, evidence-bound, idempotent, recoverable and rollback-safe."
verdict: PARTIAL
related: [pi-package-qualification]
tags: [pi, agent-runtime, event-driven, personal-intelligence]
---

# Pi Embedded Personal Intelligence Kernel Spike

## What This Validates

验证 Pi SDK 是否适合作为 person-data 的主 AI Runtime，同时让确定性 Python 底座继续独占事实、证据、任务、水位、评测和正式生命周期。

## Planning Status

- Issue：GitHub `adlink8/personal-data-analysis-system#2`
- 当前状态：001–005 已执行；001、005 为 PARTIAL，002–004 已验证
- 当前里程碑：v1.5 已完成；本 Spike 不改变 Roadmap 游标
- 决策输出：`proceed | revise | reject`

## Documents

- `RESEARCH.md`：官方 SDK 与当前仓库事实基线。
- `PLAN.md`：001–005 的可执行任务。
- `VERIFICATION-MATRIX.md`：验收、故障注入与证据矩阵。
- `FINDINGS.md`：执行时逐项记录证据。
- `DECISION.md`：最终架构决议模板。
- `prototype/README.md`：实验代码边界。
- `verification/README.md`：验证产物与隐私规则。

## Stop Conditions

以下任一项成立即停止并给出 `reject` 或重大 `revise`：

- 无法可靠关闭 coding built-ins 或 ambient resource discovery；
- Agent 可绕过 Python Domain API 接触 authority、watermark 或 promotion；
- cancel/resume/idempotency 无法跨 Node/Python 保持一致；
- Session、Candidate 与正式 SSOT 无法隔离；
- 同一 Delta 重放产生重复 Candidate；
- 成本或质量显著劣于 legacy，且无明确可修正原因。

## Execution Summary

本轮实验命令与结果记录在 `001-*` 至 `005-*` 子目录、`verification/` 和 `FINDINGS.md`。Package Qualification 因 npm audit 的高危依赖告警给出 `conditional`，因此当前架构决议为 `revise`，不创建正式 vNext milestone。
