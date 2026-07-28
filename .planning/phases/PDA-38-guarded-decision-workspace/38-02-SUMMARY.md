---
phase: 38-guarded-decision-workspace
plan: 02
subsystem: browser-orchestration
tags: [cockpit, react, guarded-write, exact-preview, replay, dec-02]
requires:
  - phase: 38-01
    provides: "只读 Decision Workspace 与 fail-closed 资格门"
provides:
  - "project + low 的 prepare → exact preview → explicit confirm → receipt/replay 浏览器链路"
  - "服务端 Preview 原样透传、volatile actor 与调用方幂等键边界"
  - "Confirm Drawer 的精确事件、限制、checksum、sequence、幂等键和无副作用取消语义"
  - "按服务端合法下一跳推进会话，并区分 receipt 与 exact replay"
affects: [40-browser-uat]
requirements-completed: [DEC-02]
completed: 2026-07-28
---

# Phase 38 Plan 02 执行摘要

## 结果

浏览器写入入口已收口到既有 `project + low` 守护编排：prepare 只生成服务端 Preview，用户必须在 Confirm Drawer 中查看 exact Preview 并使用操作专属确认文案显式确认；确认后只展示服务端返回的 sequence、event_id、event_checksum、state 与 references。取消、Esc、遮罩关闭和 busy 状态不会产生 confirm/execute 请求或重复写入。

## 已核验边界

- Preview 在 confirm/execute 请求中原样透传；客户端不重排、不补字段、不替换 payload。
- actor identity hash 仅保留在当前页面运行期内存，幂等键由调用方生成并在同一显式重试中复用。
- 刷新后的 actor drift 只能 resume/只读审阅，不能伪造继续写入能力。
- 每个合法 transition 独立 prepare、preview、confirm；没有一键完成全部阶段的入口。
- `replayed=true` 明确显示“已返回原事件，未重复写入”，不创建第二张 receipt。

## 验证

- `npm run test -- --run src/test/orchestration.test.ts src/test/ConfirmDrawer.test.tsx src/test/NewSessionFlow.test.tsx src/test/SessionPage.test.tsx src/test/TypedRecoveryPanel.test.tsx`：51/51 通过。
- `npm run test -- --run`：24 个测试文件、255 个测试通过。
- `npm run build`：TypeScript 检查与 Vite 生产构建通过。

真机响应式、键盘、离线/降级和隐私检查仍由 Phase 40 承担。
