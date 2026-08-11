# Phase 22-04 — Facade import inventory (`application` → `domains`)

**Date:** 2026-07-16 (post rewrite)  
**Scope:** `src/personal_knowledge/application/**/*.py`  
**Retire window:** 2026-08-13 (full facade directory removal — not done yet)  
**Policy:** real `from|import personal_knowledge.domains` lines under `application/` rewritten to canonical `application.*` / `evaluation.*` modules.

## Summary

| Metric | Before (22-04 inventory) | After rewrite |
|--------|-------------------------:|-------------:|
| Total import lines matching `personal_knowledge.domains` | **16** | **0** |
| Files with ≥1 such import | **10** | **0** |
| Product CLI entry (`ku.py`) domains imports | **0** | **0** |
| Doctor / history / reconcile / promote surface | **0** | **0** |

Re-scan anytime:

```powershell
$env:PYTHONPATH="<repo-root>\src"
python -m personal_knowledge.application.ku doctor --skip-ports
```

## Rewrite mapping applied

| From domains | To |
|--------------|-----|
| `domains.knowledge.knowledge_unit_pipeline` | `application.knowledge.knowledge_unit_pipeline` |
| `domains.knowledge.build_knowledge_units` | `application.knowledge.build_knowledge_units` |
| `domains.knowledge.build_knowledge_units_prod` | `application.knowledge.build_knowledge_units_prod` |
| `domains.knowledge.build_canonical_knowledge_units` | `application.knowledge.build_canonical_knowledge_units` |
| `domains.knowledge.promote_knowledge_index` | `application.knowledge.promote_knowledge_index` |
| `domains.knowledge.migrate_add_knowledge_unit_tables` | `application.knowledge.migrate_add_knowledge_unit_tables` (canonical SCHEMA_SQL home) |
| `domains.knowledge.evaluate_knowledge_unit_extraction` | `evaluation.knowledge.evaluate_knowledge_unit_extraction` |
| `domains.memory.evaluate_memory_promotion_candidates` | `evaluation.memory.evaluate_memory_promotion_candidates` |

## SCHEMA_SQL ownership

- **Canonical:** `application/knowledge/migrate_add_knowledge_unit_tables.py` (full module)
- **Facade:** `domains/knowledge/migrate_add_knowledge_unit_tables.py` re-exports application module

## Files rewritten (real imports + product-facing `python -m` strings in those modules)

| Path under `application/` | Change |
|---------------------------|--------|
| `knowledge/backfill_loop.py` | import → application |
| `knowledge/build_knowledge_units.py` | import → application |
| `knowledge/build_knowledge_units_prod.py` | import → application |
| `knowledge/build_pilot_report.py` | import → evaluation |
| `knowledge/extract_knowledge_units_l2_session.py` | imports + docstring cmds |
| `knowledge/knowledge_unit_pipeline.py` | docstring example only |
| `knowledge/merge_l2_into_canonical.py` | import + docstring cmds |
| `knowledge/refresh_knowledge_units.py` | SCHEMA_SQL ×3 + step command strings |
| `knowledge/rollback_knowledge_checkpoint.py` | import → application |
| `memory/repair_memory_promotion_candidates.py` | import → evaluation |
| `knowledge/backfill_knowledge_unit_evidence.py` | docstring cmd only |
| `knowledge/migrate_add_knowledge_unit_tables.py` | **new** canonical (copied from domains) |

## Remaining non-import `domains` string mentions (not counted by doctor)

Doctor matches only real import lines (`from|import personal_knowledge.domains`). These leftover **help/print strings** are outside the KU rewrite set:

- `conversation/build_conversation_vector_store.py`
- `conversation/visualize_conversation_graph.py`
- `graph/build_triple_store.py`
- `graph/build_graph_relation_candidates.py`
- `knowledge/doctor_ku.py` (docstring describing the scan itself — OK)

## Acceptance

- [x] Inventory: **0** real import lines under `application/` → `domains`
- [x] Doctor facade section reports 0
- [x] SCHEMA_SQL lives in application; domains migrate is re-export facade
- [ ] Full `domains/` package delete — deferred to 2026-08-13
