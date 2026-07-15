---
phase: 20
status: applied_verified
verified: 2026-07-13
---

# Phase 20 Verification (post full approval apply)

## Apply results

| Cohort | Ops | Status | Journal |
|--------|----:|--------|---------|
| agent-google-imports | 5 | applied | `var/phase20-journals/data-agent-google-imports.journal.jsonl` |
| var | 11 | applied | `var/phase20-journals/data-var.journal.jsonl` |
| archive | 3 | applied | `var/phase20-journals/data-archive.journal.jsonl` |

## Live paths

| Role | Path |
|------|------|
| Unified DB | `var/db/personal_system.sqlite` |
| Agent DBs | `data/canonical/agent/structured/db/` |
| Google DB | `data/canonical/google/structured/db/google_data.sqlite` |
| Google raw | `data/raw/google/` |
| Imports | `data/imports/` |
| Analysis | `var/reports/analysis/` |
| Runtime | `var/runtime/` |
| Logs | `var/logs/` |
| Recycle | `archive/quarantine/_recycle/` |
| Active KU | `knowledge_units_205bff9560b9_20260712142938` @ `var/db/knowledge_index_active.txt` |

## Commands re-run

```powershell
python var/phase20-journals/post_apply_verify.py   # PASS
python -m pytest -q tests/governance/test_phase19_default_paths.py tests/governance/test_physical_data_layout.py tests/governance/test_data_migration_*.py
```

## Residual

- `*.bak-phase20` source backups retained (compatibility window)
- Full physical rollback drill of multi-GB `_recycle` deferred
- Alias removal deferred (30d / one release)
