---
work_package: assistant-ui-desktop
date: 2026-08-10
decision: proceed-with-revision
spikes: [010, 011]
---

# Assistant UI Desktop Spikes

## Decision

选择 C 的桌面组合方向成立：保留现有 Electron Main/Preload，将 React + assistant-ui 放在 Renderer；默认直接进入当前对话，AgentsView 历史从左侧抽屉打开，Tool/SQLite receipt 与 Candidate review 从右侧抽屉打开，AI 只提示入口、不自动展开。

但 010 只能给出 `PARTIAL`：现有 `sendTurn()` 是单次 request/response，运行中拿不到 `taskId`，也没有 named event subscription，因此不能实现真实 token streaming 或可靠的运行中 cancel。正式阶段应先补充早期 task handle 与 Main→Renderer 的命名事件桥，再声明 Codex 式流式控制完成。

回归检查还发现一个与本 Spike 无关但会影响正式接入的既存问题：Desktop Main 的 `conversation-new` 请求没有合成 Kernel 要求的 `session_id`，所以现有 full UAT 的 new-conversation provider case 失败。本轮没有越界修改生产实现，已在验证记录中保留失败证据。

## Outcome

| Spike | Verdict | What is proven |
|---|---|---|
| [010 Runtime Adapter](./010-runtime-adapter/README.md) | PARTIAL | ExternalStoreRuntime、文本提交、安全消息投影、checksum-bound SQLite receipt 与 fail-closed 响应映射可工作；stream/cancel 契约仍缺口 |
| [011 Selected C Composition](./011-selected-c-composition/README.md) | VALIDATED | 对话首屏、窄 rail、左右抽屉、命令面板、AI 低干扰提示、Tool/Candidate 组合在真实 Chromium 中可用 |

## Prototype

原型位于 [`prototype/`](./prototype/)，只使用 synthetic fixture 和 metadata-only audit event，不接触真实个人正文、生产数据库或外部 Provider。

```powershell
cd .planning\spikes\assistant-ui-desktop\prototype
npm install --ignore-scripts
npm test
npm run build
npm run dev -- --port 4178
```

## Production Boundary

- 不替换现有 Electron Main/Preload；不新增浏览器产品页面。
- 不让 assistant-ui、React 或 Renderer 成为对话与任务权威。
- SQLite 仍通过受控 Tool 调用；Renderer 只看 checksum 绑定的 `statement_display` 和脱敏结果。
- 不启用 assistant-ui 客户端 Tool invocation pipeline。
- 本轮没有向生产 `apps/` 添加依赖，也没有修改现有 DesktopBridge。
- `@assistant-ui/react` 0.15.13 为 MIT；Spike 精确锁定版本与 lockfile，生产采用仍需单独资格决议。

## Evidence

完整验证记录见 [`verification/RESULTS.md`](./verification/RESULTS.md)。

## Primary References

- [assistant-ui External Store Runtime](https://www.assistant-ui.com/docs/runtimes/custom/external-store)
- [assistant-ui Custom Runtimes](https://www.assistant-ui.com/docs/runtimes/custom/overview)
- [assistant-ui Primitives](https://www.assistant-ui.com/docs/primitives)
- [assistant-ui Thread primitive](https://www.assistant-ui.com/docs/primitives/thread)
- [assistant-ui Composer primitive](https://www.assistant-ui.com/docs/primitives/composer)
- [assistant-ui Message primitive](https://www.assistant-ui.com/docs/primitives/message)
- [assistant-ui Tool UI](https://www.assistant-ui.com/docs/tools/tool-ui)
