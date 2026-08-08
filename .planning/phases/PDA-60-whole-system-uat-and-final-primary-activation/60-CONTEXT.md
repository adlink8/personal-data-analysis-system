# Phase 60: Whole-system UAT and Final Primary Activation — Context

<domain>
## Phase Boundary

完成 Capability/Tool/Skill/warehouse/Kernel control plane 的全系统评测与用户 UAT，并在 Phase 53 real paired baseline accepted 后重新执行 shadow→canary→primary 和 exact rollback。没有 accepted baseline 或用户授权时保持 legacy。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** 自动测试不能授权真实 Provider、live L3 数据操作或 primary 激活。
- **D-02:** UAT cohort 覆盖 read Tool、Candidate、canonical compensation、derived rebuild、snapshot release、Skill recovery 和 Kernel operation recovery。
- **D-03:** 零容忍项：unauthorized write、authority fingerprint corruption、privacy/credential leak、duplicate side effect、gate bypass、split coordinator。
- **D-04:** Phase 53 必须以独立来源 cohort≥2 和有效 frozen response contract 得到 accepted/proceed 决议。
- **D-05:** final primary 下 Pi SDK Kernel 是唯一生产 AI 协调者；不存在 Local Pi 或第二套 Agent runtime，legacy 仅 standby。
- **D-06:** forced failure 必须自动降级、停止新 claims、恢复 exact pointer/route，保留 Task/Session/Event/operation/activation history；重新升级需再次确认。

### the agent's Discretion

UAT 样本内容、性能阈值的非关键细节和报告排版。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/phases/PDA-53-real-baseline-fault-injection-and-uat/53-VERIFICATION.md`
- `.planning/phases/PDA-53-real-baseline-fault-injection-and-uat/53-ACTIVATION-DECISION.md`
- `.planning/phases/PDA-54-primary-activation-and-exact-rollback/54-ACTIVATION-REPORT.md`
- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `.planning/phases/PDA-55-unified-capability-registry-and-project-tool-surface/55-VALIDATION.md`
- `.planning/phases/PDA-59-kernel-control-plane-and-runtime-observability/59-VALIDATION.md`
</canonical_refs>

<deferred>
## Deferred Ideas

自动外部动作、自动策略 promotion 和多个平级生产 Agent 继续不在范围。
</deferred>
