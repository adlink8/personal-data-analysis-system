---
phase: 20
plan: "03"
status: preview_complete_awaiting_approval
completed: 2026-07-13
---

# 20-03 Summary: var DB / runtime / reports / logs preview

## Preview

| Field | Value |
|-------|-------|
| Manifest | `governance/manifests/data/var.json` |
| relocate nodes | 304 |
| planned ops | 24 |
| approved | **false** |
| dry-run | **PASS** |
| soft_issues | `dirty target exists: var/runtime`（已有 `var/runtime` 占位；apply 前需清理/合并策略） |
| manifest_sha256 | `f1f574d598d1fa46ed9f89b7baee1a4c475a72116a3a9465458902a3201057a4` |

## Checkpoint (human)

审批 checksum + 处理 `var/runtime` 脏目标策略后才能 `--apply`。

**未执行 apply / rollback drill。**
