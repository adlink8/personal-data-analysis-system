---
spike: PIK-PKG
name: pi-package-qualification
type: standard
validates: "Given candidate Pi dependencies, when source, integrity, compatibility and capability access are audited, then only explicitly accepted packages can enter the Kernel prototype."
verdict: CONDITIONAL
related: [pi-embedded-personal-kernel]
tags: [pi, packages, supply-chain, security]
---

# Pi Package Qualification

本工作包是 Runtime Containment Spike 001 的强制子门。清单中的包都是“待审候选”，不是安装授权。首个 Kernel 垂直切片只允许官方 P0 包；社区包必须逐包单独审计和 canary。

## Execution Status

官方 P0 包已在隔离目录以 0.83.0 精确版本安装并通过工具隔离实验；npmjs.org audit 报告当前依赖树存在 2 个 high、1 个 moderate advisory，因此整体为 `conditional`，不是生产接受。

## Documents

- `MANIFEST.md`：范围、输入和产物。
- `INVENTORY.md`：候选版本与初始分类。
- `PLAN.md`：逐包资格审查步骤。
- `COMPATIBILITY.md`：版本与 event/schema 兼容矩阵。
- `SECURITY-REVIEW.md`：权限和供应链检查表。
- `DECISION.md`：accepted/conditional/rejected 记录。
- `verification/README.md`：允许留存的证据。
