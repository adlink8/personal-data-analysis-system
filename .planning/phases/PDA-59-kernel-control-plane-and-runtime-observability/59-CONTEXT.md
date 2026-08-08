# Phase 59: Kernel Control Plane and Runtime Observability — Context

<domain>
## Phase Boundary

收口 Pi SDK Kernel 的统一控制面：把 Task、Session、Skill、Domain Tool、Provider 和 Python authority transaction 的状态、取消、恢复、对账与无正文诊断投影到同源 API 和 Cockpit。系统只保留一个 Pi SDK Kernel，不接入本机 Pi Agent 或第二套 RPC operator runtime。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** Pi SDK Kernel 是唯一 AI 协调内核；不得启动、探测或依赖本机 `pi` CLI、Local Pi RPC 或第二个 Agent daemon。
- **D-02:** 统一 operation envelope 绑定 task/session、operation kind、correlation/causation、authority class、state、budget、receipt 和 recovery action。
- **D-03:** cancel/resume/reconcile 只能调用 Kernel 和 Python authority 已有的类型化入口；不得从 UI 直连 Provider、Tool、数据库或进程。
- **D-04:** `outcome_unknown` 必须先对账 Provider/Data receipt 与 authority fingerprint，不能盲目重试副作用。
- **D-05:** Cockpit/telemetry 区分 kernel_task、kernel_session、kernel_skill、domain_tool、provider、authority_transaction 和 recovery。
- **D-06:** 所有投影仅含元数据、稳定 ID、安全原因、预算和 receipt refs；不得包含 prompt、response body、credential、个人正文或本机路径。

### the agent's Discretion

控制面内部 reducer 组织方式，以及 Cockpit 现有 System/Pi 页面中的最小展示位置。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `apps/personal_intelligence_kernel/src/server.mjs`
- `apps/personal_intelligence_kernel/src/events/schema.mjs`
- `apps/personal_intelligence_kernel/src/skills/engine.mjs`
- `src/personal_knowledge/services/pi_runtime_projection.py`
- `apps/personal_decision_cockpit/src/pages/system/SystemPage.tsx`
</canonical_refs>

<deferred>
## Deferred Ideas

本机 Pi Agent、Local Pi RPC、双 Agent handoff、自动外部动作和第二个生产协调器均不在范围。
</deferred>
