---
phase: 20
plan: "04"
status: preview_complete_awaiting_approval
completed: 2026-07-13
---

# 20-04 Summary: archive / _recycle / .gsd / .ai-bridge preview

## Preview

| Field | Value |
|-------|-------|
| Manifest | `governance/manifests/data/archive.json` |
| relocate nodes | 13,737 |
| planned ops | 44 |
| approved | **false** |
| dry-run | **PASS** (`soft_issues=[]`) |
| manifest_sha256 | `517e411a69cab890a45815cda90e048b6446c0fe9d070b09ff45e568ef784d76` |

## `_recycle` note

R4 正文 digest 需单独人工授权哈希参数后，在 apply 第一步写入 **gitignored** 本地 journal；工具不解析/不打印正文。

**未执行 apply / rollback drill。**
