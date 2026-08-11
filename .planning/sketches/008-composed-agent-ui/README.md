---
sketch: 008
name: composed-agent-ui
question: "如何直接组合 OpenCode、assistant-ui、Goose 与 AgentsView 的 UI 长处，同时保持 Codex 式低启动成本？"
winner: "C"
tags: [desktop, conversation, components, opencode, assistant-ui, goose, agentsview]
---

# Sketch 008: Composed Agent UI

## Design Question

四套开源 UI 的长处应该如何组合，才能避免重新设计通用 Agent 界面，同时不把各自的 Runtime、后端和复杂导航一起带进项目？

## How to View

在浏览器打开 `.planning/sketches/008-composed-agent-ui/index.html`。

## Variants

- **A: 对话优先组合** — OpenCode 框架、assistant-ui 对话、Goose Tool 行、AgentsView 紧凑历史栏合成一个首屏。
- **B: 历史研究工作台** — AgentsView 会话检索成为主侧栏，当前对话与 Tool/证据检查器并列。
- **C: Codex 专注模式（已选择）** — 默认只保留对话和 Composer，历史、Tool 与候选审核按 AI 触发或用户命令滑出。

## What to Look For

比较打开后的启动成本、历史会话是否容易找、Tool 状态是否可信但不过度抢眼，以及 Candidate/SQLite receipt 是否仍明确属于受控 Tool 流程。

## Selected Direction

选择 Variant C。默认首屏只保留对话、Composer 和窄导航 rail；AgentsView 历史从左侧按需滑出，Goose 风格 Tool/SQLite receipt 从右侧按需滑出，命令面板提供键盘入口。AI 可以在确有受控 Tool 结果或待审核 Candidate 时提示入口，但不得自动打开高干扰面板。

## Upstream Component Mapping

| Surface | Reference strength | Local adaptation |
|---|---|---|
| Window shell / panels | OpenCode Desktop + UI | 保留现有 Electron Main/Preload，只借布局和折叠行为 |
| Thread / Message / Composer | assistant-ui | 通过 HarnessRuntimeAdapter 映射现有 named DesktopBridge |
| Tool status / approval | Goose Desktop | 只展示现有 Skill lease、Tool receipt 与 Candidate review |
| Session history / search | AgentsView | 读取项目 canonical conversation projection，不成为执行权威 |
