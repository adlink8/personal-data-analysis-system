---
spike: 010
name: assistant-ui-runtime-adapter
date: 2026-08-10
verdict: PARTIAL
---

# 010 · assistant-ui Runtime Adapter

## Question

能否让 assistant-ui 复用当前 `window.harness` named DesktopBridge，而不引入 generic fetch/IPC、直接 SQLite、客户端 Tool execution 或第二套消息权威？

## Hypothesis

`useExternalStoreRuntime` 应当适配现有架构，因为项目已经拥有 Conversation/Task 状态和桥接回调；`LocalRuntime` 会让 UI 持有聊天权威，`AssistantTransport` 则要求另一套 streaming protocol，二者都不适合作为当前 v1 接缝。

## Prototype

[`../prototype/src/harness-adapter.tsx`](../prototype/src/harness-adapter.tsx) 实现：

- `HarnessRuntimeProvider` 将 display-safe message 转成 `ThreadMessageLike`。
- Composer 仅接受 text part，并只调用 `sendTurn({conversationId,text,projectScopeId?})`。
- Bridge 对象出现 `fetch/request/invoke/executeSql/querySql/openFile/readFile/writeFile` 即 fail closed。
- Provider 响应出现 raw SQL、path、provider body、thinking、secret、endpoint 等字段即拒绝整份响应。
- SQLite receipt 必须匹配唯一 allowlisted query/version/parameter set/statement display，并在 Renderer 重新计算 SHA-256 checksum。
- assistant-ui `data-tool-receipt` part 只渲染验证后的安全 DTO；没有启用客户端 Tool invocation。
- audit event 仅记录状态、时间、错误码和 task ID，不记录用户正文。

## Results

| Acceptance | Result | Evidence |
|---|---|---|
| assistant-ui 读取外部 store | PASS | 初始消息在真实 Chromium 正常渲染 |
| Composer 只走 named `sendTurn` | PASS | 定向测试验证 exact payload；浏览器真实提交得到回复 |
| 通用 transport / SQL surface 被拒绝 | PASS | 负向测试覆盖 generic bridge、raw SQL、path、provider body |
| Tool receipt checksum 与 allowlist | PASS | 正常 receipt 显示；tampered checksum / statement 被拒绝 |
| malformed envelope fail closed | PASS | 输出固定 incomplete 文案，不带原 payload |
| 真实 token streaming | NOT PROVEN | DesktopBridge 无事件订阅；现有调用只在 Promise resolve 后给出结果 |
| 运行中 cancel | BLOCKED BY CONTRACT | `taskId` 随最终响应返回；pending 期间不能合法调用 `cancelTurn({taskId})` |
| 现有 new-conversation 真实路由 | PRE-EXISTING FAIL | Desktop Main 未为 `conversation-new` 合成 Kernel 必需的 `session_id`；full UAT D1 失败 |

## Required Bridge Revision

正式实现应保持命名桥，而不是暴露 URL 或 generic IPC：

1. `startTurn(payload) -> {taskId, acceptedAt}` 立即返回稳定 task handle。
2. `onTurnEvent(listener) -> unsubscribe` 只传 typed、cursor-bound、display-safe event；Main 负责连接 Kernel SSE。
3. 现有 `cancelTurn({taskId})`、`resumeTurn({taskId})`、`reconcileTurn({taskId})` 保持显式方法。
4. Renderer 不知道 8790/8000 URL，不读取 token/provider body，不直接访问数据库。

## Verdict

`PARTIAL / REVISE`。assistant-ui 的外部状态适配与安全投影可行；在补齐 early task handle 和 named event subscription 前，只能交付诚实的 request/response UI，不能宣称 Codex 式 streaming/cancel。
