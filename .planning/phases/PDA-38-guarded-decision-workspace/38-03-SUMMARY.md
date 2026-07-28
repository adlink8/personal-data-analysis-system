---
phase: 38-guarded-decision-workspace
plan: 03
subsystem: typed-recovery
tags: [cockpit, typed-errors, fail-closed, replay, negative-tests, dec-03]
requires:
  - phase: 38-02
    provides: "逐步 exact Preview/confirm/replay 浏览器工作流"
provides:
  - "脱敏 typed recovery：stale、confirmation、sequence、conflict、integrity、risk、runtime、actor mismatch 与 provider outcome unknown"
  - "跨源、篡改、过期、消费确认、stale sequence、binding/checksum drift、非法 transition、同键异 payload 与 replay 负向回归矩阵"
  - "provider outcome unknown 下无自动重试、无换键、可 resume/inspect/manual review 的 fail-closed 证明"
affects: [40-browser-uat]
requirements-completed: [DEC-03]
completed: 2026-07-28
---

# Phase 38 Plan 03 执行摘要

## 结果

前端只消费 compact error envelope 的 `code`、`category`、`retryable` 与 `recovery_actions`，展示稳定、脱敏的恢复路径。任何错误、过期、篡改、actor drift 或 Provider outcome unknown 都不会自动 fetch、自动 prepare、自动换幂等键或替换 Preview/payload；同一 Preview/同一幂等键的重试必须由用户显式触发并受服务端结果约束。

## 已核验边界

- `provider_outcome_unknown`、integrity、risk、conflict、confirmation、sequence 与 actor mismatch 没有自动 retry/confirm CTA。
- stale/runtime 恢复不在渲染或 effect 中自动发网络请求。
- 错误界面不显示 raw exception、HTTP body、token、HMAC、secret、Provider body、原始证据或完整请求 payload。
- 同 payload replay 返回同一 event/checksum/sequence 且 `replayed=true`；同键异 payload 返回 typed conflict。
- 跨 origin 的 POST/OPTIONS 被拒绝，既有编排、Analysis、Pilot、Calibration 指纹保持不变。
- Provider unknown 只保留恢复会话、检查预留和人工复核路径，不产生第二次 Provider 调用。

## 验证

- `npm run test -- --run src/test/TypedRecoveryPanel.test.tsx src/test/orchestration.test.ts src/test/SessionPage.test.tsx`：36/36 通过。
- `python -m pytest tests/contract/test_orchestration_interfaces.py tests/integration/test_orchestration_replay.py tests/e2e/test_orchestration_acceptance.py -q`：14/14 通过。

Phase 40 仍需在真实浏览器/临时 fixture 上完成可访问性、响应式、降级与 DevTools/DOM/URL/storage/console 隐私复核。
