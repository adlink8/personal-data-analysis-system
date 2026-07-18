---
phase: 35
slug: runtime-and-live-e2e
status: locked
created: 2026-07-19
mode: autonomous-smart-discuss
skills: [production-script-hardening]
---

# Phase 35 Context

## Goal

用一个安全、可诊断的本地命令启动 REST、ChatGPT MCP 与 Secure MCP Tunnel，固定 descriptor contract，并完成真实本地/隧道/已登录 ChatGPT Agent 验收。

## Locked Decisions

| ID | Decision |
|---|---|
| D-01 | canonical runtime 实现放在 `ops/runtime/`，现有中文/脚本入口只保留薄兼容 wrapper。 |
| D-02 | foreground supervisor 只管理自己启动并记录的 PID；健康端口被其他健康实例占用时复用，不健康占用时失败，绝不杀任意端口 owner。 |
| D-03 | `Check`/`DryRun` 零写入；`Run` 才创建 ops logs/state 并非破坏性应用 orchestration schema。 |
| D-04 | 环境路径、端口、profile、proxy、重试均为 typed 参数；不硬编码用户目录。 |
| D-05 | CONTROL_PLANE_API_KEY 仅从环境继承，缺失时真实 tunnel 启动 fail fast；不打印值。 |
| D-06 | orchestration HMAC secret 每次 stack 启动在父进程生成并仅注入 REST 子进程，不落盘。 |
| D-07 | localhost health 全部 `-NoProxy`，依赖按 REST→MCP→tunnel 顺序达到业务 ready 后再启动。 |
| D-08 | 自动恢复最多三次，指数退避；unknown provider outcome 不由 runtime 重试。 |
| D-09 | tunnel 启动前必须直接运行 CLI `doctor --profile ... --explain`，并记录脱敏结果。 |
| D-10 | descriptor snapshot 只记录 tool 名、schema、annotations 和 output boundary 的 canonical hash，不记录动态 UI/路径私密值。 |
| D-11 | live UAT 前后计算 Personal/External/Analysis/Pilot/Calibration fingerprints 与 orchestration event counts。 |
| D-12 | 已登录 ChatGPT 验收至少执行一条 read→explain，以及 prepare→confirm exact replay；不要求新 provider 付费调用。 |
| D-13 | connector/tool refresh 只做用户已授权的现有 connector 更新，不创建公开发布或改变账号权限。 |
| D-14 | 只有本地、tunnel、descriptor 和真实 Agent 四层证据全部通过才关闭 v1.3。 |

## Out of Scope

- Windows Task Scheduler 常驻安装；本里程碑交付前台、可停止、拥有 PID 的 supervisor。
- 自动安装依赖、修改 tunnel profile、写入账号凭据。
- 新 provider 付费调用或公共应用发布。
