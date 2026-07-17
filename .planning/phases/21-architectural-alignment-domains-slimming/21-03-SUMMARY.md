# Plan 21-03 Summary: Knowledge Domain Migration

**Completed:** 2026-07-15  
**Status:** done  
**Wave:** 2 (DAG)

## What shipped

1. **17 build/orchestration modules → `application/knowledge/`** (incl. `test_knowledge_unit_llm` smoke helper).
2. **3 evaluate modules → `evaluation/knowledge/`**.
3. **`migrate_add_knowledge_unit_tables.py` STAYS** in `domains/knowledge/` (pure `SCHEMA_SQL` constant).
4. Facades on all moved domains paths (sys.modules alias).
5. **Test fix:** `tests/integration/test_knowledge_unit_checkpoint.py` bare imports → package imports (legacy `integration/scripts` path no longer has sources).

## Gate

- pytest FAILED set = 13 baseline
- architecture-boundary PASS
- schema constant importable; promote/refresh facades work

## Notes

- `_SCRIPTS_DIR = parents[1]` now resolves to `application/`; used only for sys.path bootstrap (no sibling file IO found).
- `promote_knowledge_index` → evaluation import is now legal at application layer.

## Self-Check: PASSED
