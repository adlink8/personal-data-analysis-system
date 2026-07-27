# Browser E2E Dependency Review

日期：2026-07-27

## 结论

选择：**拒绝新增浏览器 runner，采用记录化手动浏览器 UAT**。

当前 `package.json` / lockfile 没有 `@playwright/test`、Cypress 或其他浏览器 runner。Phase 40-01/02 的 Vitest、TypeScript、Projection contract 只提供组件和契约回归，不能证明真实同源 `/app/`、viewport、200% zoom、浏览器 focus、隐私 DevTools 或真实写入。

## 为什么不在本计划新增 runner

- 新增 `@playwright/test` 会扩大依赖、lockfile、浏览器安装和 artifact 管理范围。
- 当前没有已批准的 disposable authority、专用测试服务或脱敏 trace/HAR 存储策略。
- 真实 `project + low` 写入必须由用户在 checkpoint 独立确认；自动 runner 不能替代该授权。
- 选择手动路径不改变生产依赖，也不新增常驻 Node 进程、Service Worker 或浏览器业务缓存。

## 手动路径与安全规则

- 浏览器必须打开 REST owner 托管的 production same-origin `/app/`，不把 Vite proxy/mock 结果写成 production UAT。
- 使用 `docs/live-uat.md` 逐项记录 320/768/1024/1440、Tab/focus/Esc、reduced motion、200% zoom、故障恢复和隐私检查。
- 仅记录 redacted fixture 名、状态、来源、时间和恢复结果；不保存 raw personal data、preview、confirmation/HMAC、provider body、凭据、完整本地路径、tunnel URL、HAR、trace 或截图。
- 真实写入优先使用 disposable authority；若必须使用 live authority，必须在该一次写入前获得用户独立授权，并保留 append-only 证据，不删除/重置事件。

## 回退方案

如果后续明确批准新增 runner，应另开变更审查，固定 local-only Chromium、精确版本、锁文件影响、artifact redaction/deletion 和失败恢复策略；本次不隐式安装或修改 package/lockfile。
