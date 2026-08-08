# Phase 50: Durable Task, Domain Tool Bridge and Session Isolation — Context

<domain>
## Phase Boundary

在 Phase 49 Host 上建立 durable task ledger、typed Python Domain Gateway、Pi Session trajectory 和 Candidate staging。只接 synthetic/replay Provider；不迁移生产 AI 入口，不激活真实模型。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** task、session、candidate 分别使用 `pi_kernel_tasks.sqlite`、`pi_kernel_sessions.sqlite`、`pi_kernel_candidates.sqlite`，不得与 canonical/authority DB 共库。
- **D-02:** task 状态固定 queued/claimed/running/cancel_requested/succeeded/failed/outcome_unknown；claim 使用原子事务和 lease。
- **D-03:** Node 只能通过 `src/personal_knowledge/services/pi_domain_gateway.py` 的 typed operations 访问 Python；禁止任意 SQL、路径或 Python callable 名称。
- **D-04:** read Tool 与 guarded-write Tool 分 registry；write 必须携带既有 preview/checksum/sequence/confirmation/idempotency contract。
- **D-05:** Candidate 只保存 schema-valid proposal、evidence refs 和 model receipt；没有 promotion、active 或 canonical 状态。
- **D-06:** crash/cancel/replay 不推进 watermark、promotion 或 active pointer；outcome_unknown 禁止自动重试。

### the agent's Discretion

- SQLite migration helper、lease duration和内部 repository class 命名。
</decisions>

<canonical_refs>
## Canonical References

- `src/personal_knowledge/services/orchestration_service.py` — guarded preview/confirm/idempotency。
- `src/personal_knowledge/services/agent_contract.py` — compact safe envelope。
- `.planning/spikes/pi-embedded-personal-kernel/002-node-python-protocol/README.md` — claim/cancel/recovery prototype。
- `.planning/spikes/pi-embedded-personal-kernel/003-skill-artifact-isolation/README.md` — Candidate/Session isolation。
- `.planning/phases/PDA-49-pi-kernel-host-and-event-lifecycle/49-AI-SPEC.md` — Host/event contract。
</canonical_refs>
