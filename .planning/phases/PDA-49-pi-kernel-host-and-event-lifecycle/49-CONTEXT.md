# Phase 49: Pi Kernel Host and Event Lifecycle — Context

<domain>
## Phase Boundary

建立独立 loopback Pi Kernel Host、版本化事件 envelope、append-only event journal 和受控启停/健康契约。本阶段不接真实 Provider、不注册 authority 写 Tool、不迁移现有 AI 工作流，也不把 Kernel 加入主 supervisor。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** Kernel 位于 `apps/personal_intelligence_kernel`，默认监听 `127.0.0.1:8790`；只暴露 `/health`、`/ready`、`/v1/events` 和 `/v1/events/stream`。
- **D-02:** 事件 schema 固定为 `pi_kernel_event_v1`，必含 event_id、type、source、authority、snapshot、correlation_id、causation_id、idempotency_key、occurred_at、payload_ref 和 privacy_class。
- **D-03:** event_id 与 idempotency identity 由 canonical JSON checksum 确定；同一输入重放返回同一事件，不追加重复记录。
- **D-04:** 事件 journal 独立存于 `var/db/pi_kernel_events.sqlite`，只保存 metadata 和 artifact reference，不保存原始个人正文。
- **D-05:** 未识别 event type、缺失 authority/snapshot、payload inline body、非 loopback bind 或 schema mismatch 全部 fail-closed。
- **D-06:** Phase 49 的启动仅为独立开发/测试命令；加入 `start-agent-stack.ps1` 延至 Phase 52。

### the agent's Discretion

- Node 模块内部文件拆分、SQLite wrapper 和 SSE heartbeat 实现。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — KERNEL-01、KERNEL-02。
- `.planning/phases/PDA-48-pi-package-qualification-and-runtime-containment/48-AI-SPEC.md` — accepted package/resource boundary。
- `.planning/spikes/pi-embedded-personal-kernel/prototype/streaming_control.mjs` — cursor/replay/SSE prototype。
- `src/personal_knowledge/services/api_server.py` — loopback HTTP、safe error 和同源模式。
- `ops/runtime/start-agent-stack.ps1` — 后续 lifecycle/ownership 兼容目标。
</canonical_refs>

<deferred>
## Deferred Ideas

Domain Tools、durable task 和 Session：Phase 50；Provider/Skill：Phase 51；Cockpit/supervisor：Phase 52。
</deferred>
