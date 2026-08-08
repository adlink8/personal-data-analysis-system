---
spike: PIK-FRONTIER
name: pi-frontier-controls
type: standard
validates: "Given the Pi kernel boundaries, when provider failure, concurrent load, retention expiry and SDK drift occur, then the system remains fail-closed, privacy-safe, bounded and rollbackable."
verdict: PARTIAL
related: [pi-embedded-personal-kernel, pi-package-qualification]
tags: [pi, frontier, controls, privacy, reliability]
---

# Pi Frontier Controls

本工作包承载 006–009 的扩展实验。所有代码、依赖和测试存储仅允许位于本目录；不读取真实个人正文，不修改正式 watermark、active pointer、Canonical/KU 或生产服务。

## Execution Status

006/007 为 synthetic `PARTIAL`，008/009 为 isolated `VALIDATED`。真实 Provider、跨进程 worker 和升级安装仍需单独授权与验证。

## Spikes

| # | Name | Validates | Verdict |
|---|---|---|---|
| 006 | provider-auth-and-budget-fail-closed | Provider 失败、凭据边界与预算门 | PARTIAL |
| 007 | concurrent-task-backpressure | 多 Delta 并发、合并、背压与配额 | PARTIAL |
| 008 | session-retention-and-privacy-expiry | 隐私留存、过期与 authority 隔离 | VALIDATED |
| 009 | sdk-upgrade-and-requalification | 版本漂移、协议变化与回滚 | VALIDATED |

## Shared Evidence Rules

- 只使用 synthetic fixture、opaque ID、checksum 与统计摘要。
- 每项至少覆盖 happy path、失败路径和重复/重启边界。
- 任何未声明的网络、文件、进程或凭据访问视为失败。
- 运行命令、调查轨迹、结果和限制写入各 Spike README。
