# Memory domain

## Responsibility

**Compat package only.** Long-term memory build/lifecycle and evaluation moved
to `application.memory` / `evaluation.memory` in Phase 21. Modules here are
re-export facades.

**Note:** memory / personal_events is **not** the knowledge SSOT. Knowledge SSOT
= KU tables + active vector collection (`pk-ku` / active pointer).

## Canonical locations

| Kind | Package |
|------|---------|
| Build / lifecycle / promotions | `personal_knowledge.application.memory` |
| Eval / compare / analyze / audit | `personal_knowledge.evaluation.memory` |

Do not add new logic under `domains/memory/`.

## Ownership

Owner: memory (compat). Status: re-export only.
Last layout review: 2026-07-16 (Phase 22; facade debt clear).
