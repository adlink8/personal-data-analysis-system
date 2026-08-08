# Phase 53: Real Baseline, Fault Injection and UAT — Context

<domain>
## Phase Boundary

冻结同一真实 cohort/模型/预算，比较 Pi 与 legacy，执行跨进程故障、隐私和浏览器 UAT，并形成 shadow/canary/primary 激活决议。任何付费或真实 Provider 调用均需执行时单独明确授权。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** baseline 预注册 cohort、模型、prompt/input checksum、budget、timeout、attempt count 和 metric；两臂除 runtime 外保持一致。
- **D-02:** 每臂每 case 默认一次调用、零静默重试；超预算或样本不足必须诚实 INCONCLUSIVE。
- **D-03:** 质量、成本、延迟、恢复性和 Tool 选择分别报告，不合成单一“更聪明”分数。
- **D-04:** 故障矩阵覆盖 Provider timeout/rate-limit/outcome_unknown、Node kill、Python kill、SSE disconnect、DB busy/corruption fixture、cancel race 和 restart。
- **D-05:** 浏览器 UAT 使用授权、去标识化/最小真实 cohort，验证响应式、键盘、隐私、降级、cancel/resume 和零 authority mutation。
- **D-06:** 激活决议只允许 proceed_shadow/proceed_canary/revise/reject；本阶段不执行 primary 切换。

### the agent's Discretion

- 指标报告图表布局和 fixture case ID 命名。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/spikes/pi-embedded-personal-kernel/005-streaming-control/README.md` — 尚缺真实 baseline/UAT。
- `.planning/phases/PDA-31-personalization-calibration-and-reversible-next-slice/` — 预注册、paired arms 和 INCONCLUSIVE 模式。
- `.planning/phases/PDA-47-p0-hardening-cohort-uat-and-expansion-decision/47-UAT-PROTOCOL.md` — 浏览器 UAT 模式。
- Phase 49–52 VERIFICATION artifacts — runtime candidate evidence。
</canonical_refs>
