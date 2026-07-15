# Knowledge domain

## Responsibility

Rules, models, and constants for knowledge units. The only non-facade logic
module retained here is **`migrate_add_knowledge_unit_tables.py`** (`SCHEMA_SQL`).

## Canonical locations (Phase 21)

| Kind | Package |
|------|---------|
| Build / refresh / promote / pipeline | `personal_knowledge.application.knowledge` |
| Canary / extraction / RAG eval | `personal_knowledge.evaluation.knowledge` |
| Schema DDL constant | `personal_knowledge.domains.knowledge.migrate_add_knowledge_unit_tables` |

Facades on former build/eval scripts: cleanup **2026-08-13**.

## Ownership

Owner: knowledge. Status: supported. Last layout review: Phase 21 (2026-07-15).
