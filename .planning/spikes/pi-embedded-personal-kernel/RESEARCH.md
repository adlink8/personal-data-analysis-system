# Research — Pi Embedded Personal Intelligence Kernel

## Sources Checked

- Pi SDK：`https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/sdk.md`
- Extensions：`https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/extensions.md`
- Skills：`https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/skills.md`
- Packages：`https://github.com/earendil-works/pi/blob/main/packages/coding-agent/docs/packages.md`
- 官方 package metadata：`@earendil-works/pi-*` 0.83.0，MIT，Node `>=22.19.0`
- 本地运行时：Node 24.13.0、npm 11.6.2、Python 3.14.2

## Current Official Facts

1. `createAgentSession()` 和 `AgentSessionRuntime` 提供事件流、compaction、steer、follow-up、abort、session replacement 与恢复入口。
2. `noTools: "builtin"` 可关闭 built-in coding tools 并保留 custom/extension tools；`noTools: "all"` 可关闭全部工具。
3. `customTools` 可直接注册自定义 Tool；正式 Spike 应显式提供 Tool allowlist，并检查最终 `session.agent.state.tools`。
4. 默认 `DefaultResourceLoader` 会发现 `.pi/extensions`、`.pi/skills`、`.agents/skills`、全局 agent 目录、settings、credentials 和 context 文件。生产设计不能依赖默认发现。
5. Session replacement 后 `runtime.session` 会变化，调用方必须重新订阅事件并重新绑定 Extensions；这是 resume/stream correctness 的重点故障点。
6. Skill 采用 progressive disclosure，模型并不保证总会主动加载匹配 Skill；必须测试显式 Skill 路由和 selection accuracy。
7. Pi Packages 具有完整系统访问能力；项目 package 在受信任仓库中可能自动安装缺失依赖，git package 还可能执行 `npm install`。person-data 必须禁用运行时自动安装和未审计发现。

## Issue Corrections

- Issue 正文中的 `badlogic/pi-mono` 链接与旧 namespace 已过时；规划以 `earendil-works/pi` 和 `@earendil-works/*` 为准。
- Issue 写作时 v1.5 尚未完成；当前 `.planning/STATE.md` 已记录 v1.5 P0 完成。Spike 仍需尊重 Phase 42/43 partial 与人工治理队列，但不再被 v1.5 阻塞。

## Local Reuse Baseline

| Existing capability | Reuse in Spike | Boundary |
|---|---|---|
| `services/agent_contract.py` compact envelope | Node/Python Tool response contract baseline | 扩展 schema，不把 raw payload 送入 Session |
| `services/orchestration_service.py` | typed error、explicit confirmation、idempotency 参考 | Spike 不调用正式 confirm/write 路径 |
| `application/knowledge/eligibility.py` | deterministic Delta/eligibility 口径 | Delta 判定必须在模型前完成 |
| KU watermark/doctor/reconcile | failure/no-advance fingerprint | Agent 永远无 advance/promote Tool |
| evidence resolver / retrieval | 首批只读 Domain Tools | 返回预算化 evidence refs，不返回无限原文 |
| candidate/evaluation modules | Candidate schema 与 gate 参考 | Pi 只提交 staging candidate，不裁决 promotion |
| Cockpit Projection | SSE/Task UI 的宿主 | 浏览器不保存 provider key 或 raw session authority |

## Approach Comparison

| Approach | Pros | Cons | Decision for Spike |
|---|---|---|---|
| Embedded `pi-coding-agent` SDK | 最快验证完整 Session/Skill/Tool/stream 能力 | 默认 coding/resource 语义较宽 | **Use first, with custom loader and no built-ins** |
| 直接基于 `pi-agent-core` | 内核更纯、依赖面更小 | 需自行补 Session/Skill/Resource 生命周期 | Reserve only if SDK containment fails |
| Pi 作为外部 MCP/sidecar | 隔离清晰、接入容易 | 不满足“主 AI Runtime”目标，取消/恢复链更碎 | Fallback after reject |
| 保留 Python 手写 Tool Loop | 当前风险最低 | 无法解决重复编排与 Skill 复用问题 | Legacy baseline and rollback |

## Research Verdict

官方 SDK 在功能上支持进入实验，但安全性和状态一致性尚未证明。最先验证的不是模型效果，而是资源发现关闭、Tool allowlist、Node/Python cancellation/idempotency 和 Session/SSOT 隔离。

