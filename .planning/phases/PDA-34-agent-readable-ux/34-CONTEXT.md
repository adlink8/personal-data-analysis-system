---
phase: 34
slug: agent-readable-ux
status: locked
created: 2026-07-19
mode: autonomous-smart-discuss
---

# Phase 34 Context

## Goal

让模型和用户快速理解每个 Agent 结果、限制、证据引用和下一步，同时保持私密正文、能力令牌与大型 authority payload 不进入默认上下文。

## Locked Decisions

| ID | Decision |
|---|---|
| D-01 | 所有 v1.3 Agent 工具共享 `agent_compact_envelope_v1`，不再由每个传输层自行发明摘要。 |
| D-02 | 成功响应固定包含 `summary`、`ids`、`limitations`、`next_actions`、`evidence_links`、`data`、`truncated` 和 `budget`。 |
| D-03 | 失败响应固定包含 `code`、安全 message、`retryable`、`recovery_actions`、`limitations`，不包含 traceback。 |
| D-04 | 默认模型可见 JSON 上限 16 KiB；list 默认不内嵌 authority 正文，get/explain 超预算则只保留紧凑投影。 |
| D-05 | Evidence link 只包含 authority、record type、stable id、checksum 与 drill-down operation。 |
| D-06 | provider body、credentials、confirmation capability、原始私密证据正文永不进入 compact envelope。 |
| D-07 | 错误 taxonomy 覆盖 not-found、conflict、stale、confirmation、sequence、risk、integrity、runtime。 |
| D-08 | 恢复动作来自 allowlist，不能建议绕过确认、扩大风险域、重试 unknown provider outcome 或自动 promotion。 |
| D-09 | `provider_outcome_unknown` 明确 `retryable=false`，恢复动作仅为 inspect/resume/manual review。 |
| D-10 | ChatGPT HTTP MCP、stdio MCP 与 REST 共享同一 Python contract；Node 只做有界展示和固定路由。 |
| D-11 | 固定 Agent eval 覆盖工具选择、not-found 下钻、stale resume、confirmation 重新预览和 unknown-outcome 人工审查。 |
| D-12 | 保留所有 Phase 32/33 旧工具名和底层 authority 数据契约，compact envelope 为 Agent transport 的 additive projection。 |

## Out of Scope

- 新 widget/dashboard。
- 暴露完整 provider 请求/响应。
- 自动执行 recovery action。
- 修改 Phase 28–33 authority schema。

## Acceptance

- UX-01/02 全覆盖。
- 默认 envelope 小于等于 16 KiB，敏感字段为零。
- Python/Node 固定 eval 全通过；legacy transport contract 无回归。
