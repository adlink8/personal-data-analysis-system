# Phase 54: Primary Activation and Exact Rollback — Context

<domain>
## Phase Boundary

依据 Phase 53 accepted decision，执行 shadow → canary → primary，证明所有 AI 工作流由 Pi 驱动，并完成 exact rollback/forward-restore。没有 accepted 决议或用户激活授权时停止。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** runtime mode 只有 legacy/shadow/canary/primary，存于版本化本地配置和 append-only activation ledger；默认 legacy。
- **D-02:** shadow 不产生第二次真实 Provider 副作用；使用 replay/captured input 或明确比较 harness。
- **D-03:** canary cohort、时窗、budget、stop conditions 和 rollback target 在切换前冻结。
- **D-04:** primary 下所有生产 AI entrypoint 必须产生 Pi task/session/event receipt；未迁移调用即 fail readiness。
- **D-05:** rollback 原子恢复 legacy route/config，停止新 Pi claims，保留历史 Session/Event，不回滚或删除 authority 数据。
- **D-06:** primary、rollback 和 forward-restore 都需要用户明确确认；自动 stop 只能降级，不能自动升级。

### the agent's Discretion

- activation ledger 内部表名和 operator CLI 命令细节。
</decisions>

<canonical_refs>
## Canonical References

- Phase 53 activation decision and UAT report — mandatory gate。
- `ops/runtime/start-agent-stack.ps1` — owned process and restart behavior。
- `src/personal_knowledge/intelligence/analysis/providers.py` — legacy fallback adapter。
- Phase 24 lifecycle activation/rollback evidence — append-only reversible precedent。
</canonical_refs>
