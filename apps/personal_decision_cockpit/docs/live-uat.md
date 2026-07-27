# Cockpit Live UAT Matrix

本矩阵区分三类证据：`自动化回归`（Vitest/TypeScript/Projection contract）、`真实浏览器观察`（生产同源 `/app/`）和 `人工确认`（写入/隐私/发布门）。组件测试通过不能替代真实浏览器 UAT。

| Requirement / decision | 场景 | 自动化证据 | 真实浏览器 / 人工证据 | 约束与恢复 |
|---|---|---|---|---|
| UX-01 / D-40-01 | 320/768/1024/1440、长中文/ID、200% zoom | AppShell/System/页面语义测试 | 真实 viewport、缩放、无横向裁切 | 只记录 redacted fixture 名，不保存个人正文 |
| UX-01 / D-40-02 | 文本、图标、ARIA、可见 focus、键盘、Esc、reduced motion | AppAccessibility/ConfirmDrawer | Tab/Shift+Tab、焦点恢复、系统 reduced-motion | 取消/Esc 不确认、不写入 |
| UX-02 / D-40-03 | REST offline、MCP unavailable、Chroma unavailable、单 authority partial | Projection fault tests / StatePanel tests | 生产同源观察每个独立降级卡 | 仅 typed recovery、刷新或查看证据；不缓存假成功 |
| UX-02 / D-40-04 | URL、DOM、console、storage、错误信封和 fixtures 隐私边界 | PrivacyBoundary/live contract tests | 浏览器 DevTools 人工检查 | 不记录 raw message、PII、HMAC、preview、provider body、凭据或 tunnel URL |
| QA-01 / D-40-06 | 故障注入后 authority 与 append-only fingerprint 不变 | Python zero-mutation contracts | Disposable fixture 复核 | 不停止用户进程、不 reset live DB/vector/pointer |
| QA-02 / D-40-05 | project+low prepare → exact preview → confirm → exact replay | orchestration/replay contracts | 同源真实浏览器一次写入与同 payload replay | 优先 disposable authority；live 写入需每次单独授权 |
| QA-01 / D-40-07 | 浏览器 runner 依赖与 artifact 审查 | package/dependency review | 记录 local-only、redaction、保留策略 | 未批准新增 runner 时只能手动 UAT |

## 当前阶段边界

- Phase 39 的 contract/component 证据已完成；不宣称 Phase 40 UAT 通过。
- Phase 40 的真实浏览器、响应式、无障碍、隐私和发布结论必须在 `.planning/phases/PDA-40-product-hardening-and-live-uat/40-UAT.md` 记录后才能改变状态。
- 失败只允许前端/配置/typed recovery；不得删除或重置 append-only 事件、lifecycle、Serving Snapshot 或控制历史。
