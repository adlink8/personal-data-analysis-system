---
phase: 20
plan: "02"
status: preview_complete_awaiting_approval
completed: 2026-07-13
---

# 20-02 Summary: Agent / Google / imports preview

## Preview

| Field | Value |
|-------|-------|
| Manifest | `governance/manifests/data/agent-google-imports.json` |
| relocate nodes | 1,161 |
| planned ops | 33 |
| approved | **false** |
| dry-run | **PASS** (`soft_issues=[]`) |
| manifest_sha256 | `9d2000d39a0f36882d3cef366ce3238a5df9f8348febd28adbaaaf4b258303e2` |

## Checkpoint (human)

逐 cohort 审批 manifest checksum 后，将 `approved=true` 并重算 `manifest_sha256`，再允许：

```powershell
python -m personal_knowledge.governance.apply_data_migration --manifest governance/manifests/data/agent-google-imports.json --apply
```

**未执行 apply / rollback drill。**
