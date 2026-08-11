---
spike: 011
name: selected-c-desktop-composition
date: 2026-08-10
verdict: VALIDATED
---

# 011 · Selected C Desktop Composition

## Question

能否直接组合开源 UI 的长处，做出接近 Codex/ZCode 使用习惯、打开即可对话且启动成本低的 Electron Renderer，而不是再维护浏览器 Cockpit？

## Composition

| Surface | Reused idea | Local adaptation |
|---|---|---|
| App shell | OpenCode Desktop | 56px rail + 当前对话，不复制其 Runtime |
| Thread / Message / Composer | assistant-ui primitives | ExternalStoreRuntime 绑定现有 named DesktopBridge |
| Tool status / receipt | Goose | 一行低干扰状态，详情进入右抽屉 |
| Cross-agent history | AgentsView | 左抽屉只读历史投影，不成为执行权威 |
| Candidate review | 项目现有 guarded flow | 右抽屉展示；Spike 按钮不执行写入 |

## Verified Interaction

- 启动后直接显示当前对话和 Composer，左右抽屉默认关闭。
- 历史通过 rail 或顶部按钮从左侧滑出，可搜索 Codex/ZCode fixture。
- Tool/SQLite/Candidate 从右侧滑出，不占用永久页面。
- `Ctrl+K` 打开命令面板，`Escape` 关闭。
- 受控 Tool 完成后只出现 badge + 小提示；用户点击后才打开证据抽屉。
- assistant-ui data part 在消息内渲染紧凑 Tool 行；右抽屉显示 checksum、受控 statement 与脱敏结果。
- `prefers-reduced-motion` 会关闭可见动画。

## Verdict

`VALIDATED`，范围是 selected-C 的 React 组合与交互。它证明“不维护浏览器界面”可以通过 Electron + React 实现，而无需改成 Windows 原生控件；它不证明正式 Electron 打包、真实 AgentsView 数据、真实 Candidate 写入或 streaming bridge 已完成。

## Screenshot

默认对话与受控证据状态见 [`../verification/selected-c-evidence.png`](../verification/selected-c-evidence.png)。
