# Phase 52: Cockpit Streaming, Supervision and Observability — Context

<domain>
## Phase Boundary

把 Pi 事件投影、task status、cancel/resume、Kernel readiness 和 supervisor ownership 接入现有 Python same-origin API 与 React Cockpit。浏览器不直连 8790，不接触 raw Session/provider body，不新增 authority 写入。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** 浏览器只访问 8000 same-origin `/api/pi/*`；Python 代理/投影 Kernel，8790 不启用 CORS。
- **D-02:** SSE DTO 固定为 `pi_cockpit_event_v1`，只含 task/session metadata、safe status、progress、tool label、evidence refs 和 recovery action。
- **D-03:** cancel/resume 是同源 POST，带 task version/idempotency；cancel 不等于成功，UI 必须显示 requested/acknowledged/terminal。
- **D-04:** UI 复用现有 AppShell、Token、响应式和 reduced-motion，不引入 `pi-web-ui` 或新设计系统。
- **D-05:** supervisor 把 Kernel 作为 owned child，独立 health/readiness/restart budget；不得杀死 adopted/unknown port owner。
- **D-06:** telemetry 只记录 IDs、duration、status、counts、budget 和 safe code；无 prompt、completion、Tool body、credential 或绝对路径。

### the agent's Discretion

- Task panel 位于 System 页面还是全局 drawer 的具体组件拆分；必须遵守 UI-SPEC。
</decisions>

<canonical_refs>
## Canonical References

- `apps/personal_decision_cockpit/src/components/layout/AppShell.tsx` — layout/navigation。
- `apps/personal_decision_cockpit/src/api/hooks.ts`、`schemas.ts` — React Query/Zod contract。
- `src/personal_knowledge/services/api_server.py` — same-origin/CORS/safe error。
- `src/personal_knowledge/services/ui_projection.py` — sanitized runtime projection。
- `ops/runtime/start-agent-stack.ps1`、`tests/ops/test_agent_stack_script.py` — ownership/readiness。
</canonical_refs>
