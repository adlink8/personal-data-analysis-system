# 22-01 Summary — Lifecycle reconcile

**Status:** complete (2026-07-16)

- 交付 `pk-ku reconcile`，默认 dry-run；写模式要求 `--i-know`。
- 写入只更新 lifecycle / supersedes 关系，不执行 DELETE；行数稳定性有测试覆盖。
- 运行手册已记录安全边界；生产 reconcile 写入仍由操作者审阅后决定。
