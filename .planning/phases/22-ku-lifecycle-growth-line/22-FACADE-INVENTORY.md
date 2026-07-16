# Phase 22-04 — Facade import inventory (`application` → `domains`)

**Date:** 2026-07-16  
**Scope:** `src/personal_knowledge/application/**/*.py`  
**Retire window:** 2026-08-13 (full facade directory removal — not done in 22-04)  
**Policy this plan:** inventory + doctor section only; **no mass rewrite** of imports (risk high for product path).

## Summary

| Metric | Value |
|--------|------:|
| Total import lines matching `personal_knowledge.domains` | **16** |
| Files with ≥1 such import | **10** |
| Product CLI entry (`ku.py`) domains imports | **0** |
| Doctor / history / reconcile / promote surface | **0** (canonical modules) |

Re-scan anytime:

```powershell
$env:PYTHONPATH="D:\ADLINK\数据分析\src"
python -m personal_knowledge.application.ku doctor --skip-ports
# or JSON: doctor --json --no-facade  # facade block still default-on without --no-facade
```

## Top files (by import line count)

| # | Path under `application/` | Count |
|---|---------------------------|------:|
| 1 | `knowledge/extract_knowledge_units_l2_session.py` | 4 |
| 2 | `knowledge/refresh_knowledge_units.py` | 3 |
| 3 | `knowledge/build_knowledge_units_prod.py` | 2 |
| 4 | `knowledge/backfill_loop.py` | 1 |
| 5 | `knowledge/build_knowledge_units.py` | 1 |
| 6 | `knowledge/build_pilot_report.py` | 1 |
| 7 | `knowledge/knowledge_unit_pipeline.py` | 1 |
| 8 | `knowledge/merge_l2_into_canonical.py` | 1 |
| 9 | `knowledge/rollback_knowledge_checkpoint.py` | 1 |
| 10 | `memory/repair_memory_promotion_candidates.py` | 1 |

## Notes / owners (prep for 2026-08-13)

- **Incremental product path** (`pk-ku` inspect/prepare/extract/canonical/publish/vector/canary/promote/watermark/reconcile/history/doctor) does **not** require new domains imports; remaining hits are legacy extract/prod/pipeline/shim helpers.
- Highest-touch product-adjacent: `refresh_knowledge_units.py` (SCHEMA_SQL lazy import ×3), `build_knowledge_units_prod.py`, `knowledge_unit_pipeline.py` re-export.
- Safe rewrites later: point SCHEMA_SQL / RunManifest / StagingPublisher at application or core modules once domains is a pure re-export shim.
- **Do not** delete `personal_knowledge.domains` package until import count is 0 outside intentional shims.

## Acceptance vs plan 22-04

- [x] Inventory ≤ N with owners (N=16 lines / 10 files; listed above)
- [x] Doctor reports facade section (live count)
- [ ] Zero product-path imports — already true for `ku.py` surface; full application tree cleanup deferred to facade retire date
