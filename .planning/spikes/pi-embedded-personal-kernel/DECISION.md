---
decision: revise
allowed_values: [proceed, revise, reject]
---

# Pi Embedded Kernel Decision

## Current Decision

`REVISE` — 核心边界实验可行，但供应链资格、真实 Provider/legacy 基线和浏览器 UAT 尚未满足 proceed gate。

## Proceed Gate

- [x] 001 Runtime containment 的工具/资源隔离通过；供应链部分仍需整改
- [x] 002 Node/Python correctness 通过 synthetic kill gate
- [x] 003 Skill 与 Artifact/Session 隔离通过 synthetic gate
- [x] 004 Delta vertical slice 的 authority-safe gate 通过
- [ ] 005 streaming/control 的真实 baseline 与 UAT 完成
- [x] Package Qualification 已给出 conditional/rejected 边界
- [ ] 无 privacy incident、active knowledge pollution 或 unauthorized Tool execution
- [ ] feature flag rollback 验证通过

## Decision Consequences

### If proceed

创建正式 vNext milestone，分配 Phase 编号，生成 AI-SPEC、requirements、roadmap 和 phase artifacts；显式修订 `PROJECT.md` 为“Agent Runtime 仅用于 AI 控制层，确定性数据核心与治理不被接管”。

### If revise

列出限制后的架构、缺失证据和下一轮 Spike；不得提前添加生产依赖或切换 workflow。

### If reject

保留 legacy；Pi 最多作为外部 MCP 客户端或局部 UI Agent，所有实验依赖和 feature flag 默认关闭。

## Evidence and Required Follow-up

- Runtime containment 的实际结果见 `001-runtime-containment/README.md` 与 `verification/runtime-resource-registry.json`。
- npm audit 使用 npmjs.org registry 报告 `undici`/`brace-expansion` 传递风险；当前不将包标记为 accepted。
- `005` 需要真实 legacy/Pi shadow window、成本/质量/可靠性比较和浏览器 UAT。
- `006`/`007` 仅验证 synthetic Provider 与单机 scheduler；真实 rate limit、跨进程 worker 和付费调用必须另行授权。
- 在上述缺口关闭前，不修改 `.planning/ROADMAP.md`、`.planning/PROJECT.md` 或生产依赖。
