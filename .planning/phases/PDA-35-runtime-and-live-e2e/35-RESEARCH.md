---
phase: 35
status: complete
created: 2026-07-19
---

# Phase 35 Research

## Current Runtime Facts

- PowerShell 7、Python、Node、`rag-api`、tunnel-client 0.0.9 均可发现。
- `personal-data-app` tunnel profile 存在，CONTROL_PLANE_API_KEY 已设置。
- REST/MCP/tunnel 当前均未监听；tunnel doctor 因 MCP 未启动而按预期失败。
- orchestration live DB 尚未创建；其余五类 authority DB 存在。

## Baseline Production Audit

Bundled auditor verdict: `PARTIAL`（严重 0、高 5、中 1）。手工复核另发现原脚本会杀死任意占用目标端口的进程，按 SAFE-01 视为严重阻断。

主要差距：硬编码路径/代理/profile、CheckOnly 会安装/复制、缺 DryRun、缺 secret fail-fast、无脱敏配置摘要、非 PowerShell 7 声明、日志/状态不在 ops、无 CLI doctor 真实源验证。

## Selected Shape

建立 foreground service supervisor：参数化配置、纯 preflight/probe、owned PID state、健康复用、有限退避、直接 tunnel doctor、结构化日志/最终 JSON readiness。现有入口转发至 canonical 脚本。
