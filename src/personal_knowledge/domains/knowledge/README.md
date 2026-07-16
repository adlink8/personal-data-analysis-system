# Knowledge domain

## Responsibility

**Compat package only.** Product ownership of knowledge-unit build, lifecycle,
and schema DDL lives under `application` / `evaluation`. Modules here are
re-export facades (`sys.modules[__name__] = canonical`).

## Canonical locations

| Kind | Package |
|------|---------|
| Build / refresh / promote / pipeline | `personal_knowledge.application.knowledge` |
| Product CLI | `personal_knowledge.application.ku` (`pk-ku`) |
| Canary / extraction / RAG eval | `personal_knowledge.evaluation.knowledge` |
| Schema DDL constant (`SCHEMA_SQL`) | `personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables` |

Do **not** add new logic under `domains/knowledge/`. New code imports
`application.*` / `evaluation.*` only.

## Ownership

Owner: knowledge (compat). Status: re-export only.
Last layout review: 2026-07-16 (Phase 22; facade debt clear; SCHEMA in application).
