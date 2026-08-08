---
spike: 001
name: runtime-containment-and-package-baseline
type: standard
validates: "Given Pi 0.83.0 is embedded in Node, when a session starts, then only explicitly allowlisted Domain Tools/resources are reachable."
verdict: PARTIAL
related: [pi-package-qualification]
tags: [pi, security, supply-chain]
---

# Spike 001: Runtime Containment and Package Baseline

## Research

依据 Pi 官方 SDK 文档的 `createAgentSession`, `noTools: "builtin"`, `customTools` 与 `DefaultResourceLoader` API 实现实验：[SDK 文档](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md)、[Extensions 文档](https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md)。包版本精确锁定为 0.83.0，Node 运行时为 24.13.0。

## How to Run

```powershell
cd D:\ADLINK\数据分析\.planning\spikes\pi-embedded-personal-kernel\prototype\agent-runtime
node runtime-containment.mjs
npm ls @earendil-works/pi-coding-agent @earendil-works/pi-ai @earendil-works/pi-storage-sqlite-node --depth=0
```

## Investigation Trail

1. 首次运行因 Windows `import.meta.url` 路径转换错误失败；改用 `fileURLToPath()` 后重跑。
2. 在 cwd、agentDir、`.pi` 和 `.agents/skills` 放置 4 个 decoy fixture；使用 `noExtensions/noSkills/noContextFiles` 与显式工具白名单启动。
3. 连续验证的运行结果均为两个 Domain Tool、零内置 coding tool、零 extension、零 skill、零 prompt、零 context file。
4. `npm audit` 通过 npmjs.org registry 查询到 3 个依赖告警（2 high、1 moderate），其中 `undici` 与 `brace-expansion` 通过 Pi coding-agent 传递进入；可用修复建议会降级到 0.75.3，不能直接接受为 0.83.0 基线。

## Results

运行时隔离行为通过，但供应链资格不能视为完全通过。判定 `PARTIAL`：可继续做隔离 Spike；首个 P0 不能将当前依赖标为 accepted，需升级/补丁验证后重新资格审查。
