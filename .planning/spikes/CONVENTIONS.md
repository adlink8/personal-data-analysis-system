# Spike Conventions

## Stack

- Python 3.11+ 继续承载 person-data Domain、SSOT、SQLite/Chroma、evaluation 与 lifecycle。
- Node.js 使用本机兼容的 24.x；Pi 官方最低要求为 Node 22.19.0。
- Pi 首轮仅验证 `@earendil-works/pi-coding-agent`、`@earendil-works/pi-ai`、`@earendil-works/pi-storage-sqlite-node` 0.83.0 精确版本。
- Web 继续复用现有 React/Vite Cockpit；Spike 优先使用最小 SSE 页面，不引入新的前端框架。

## Structure

- Prototype 只写入 `.planning/spikes/pi-embedded-personal-kernel/prototype/`。
- 测试和故障注入只写入对应 `verification/` 目录或临时数据库。
- Pi Session、Agent Task Ledger、Candidate Artifact 使用三个独立测试存储；不得复用当前 authority 数据库。

## Patterns

- 默认拒绝：未声明 Tool、Skill、Package、网络目标、文件路径或写操作一律拒绝。
- 先确定性检查 Delta，再创建 AgentSession。
- 所有跨进程请求携带 `task_id`、`idempotency_key`、`schema_version`、deadline 与 cancellation token。
- Candidate 只通过 Python Domain API 写入 staging authority；Pi 不能直接写数据库。
- 每个实验保留 metadata-only 事件日志与统计摘要，不保存原始个人正文、secret 或 provider body。

## Tools and Libraries

- 官方 Pi 包必须精确锁定，不使用 `latest`、宽松 semver 或运行时自动更新。
- 首轮禁止社区 Package、动态 Extension、自动发现全局 Skills、MCP host config discovery 和 coding built-ins。
- 只有 Package Qualification 得出 `accepted` 后，依赖才能进入后续正式里程碑候选。

## Verification

- 每个 Spike 先以 synthetic fixture 验证边界，再把真实 Provider、真实 cohort、浏览器 UAT 和跨进程/跨机验证明确标为未覆盖，不用 stub 结果替代。
- 报告只保存 opaque ID、checksum、状态计数、错误码和 authority fingerprint；Session、Candidate、Task Ledger 使用独立测试存储。
- 任何 version/integrity/API/event/dependency drift 都使资格失效并路由回 legacy；重新资格审查前不修改 Roadmap/Project 或生产依赖。
