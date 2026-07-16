# Conversation domain

## Responsibility

**Compat package only.** Rules historically lived here; build/eval orchestration
moved in Phase 21. Remaining modules are re-export facades to
`application.conversation` / `evaluation.conversation`.

## Boundaries

- No retrieval ranking, UI, or direct production promotion.
- No LLM client primitives (those are in `core/llm.py`).
- Do not add new logic under `domains/conversation/`.

## Canonical locations

| Kind | Package |
|------|---------|
| Build / summary / graph / vector-store | `personal_knowledge.application.conversation` |
| Product sync CLI | `personal_knowledge.application.sync` (`pk-sync`) |
| Eval / compare / eval-set | `personal_knowledge.evaluation.conversation` |
| LLM client + retry | `personal_knowledge.core.llm` |

## Tests

Conversation normalization and contract tests under `tests/`.

## Ownership

Owner: conversation (compat). Status: re-export only.
Last layout review: 2026-07-16 (Phase 22; facade debt clear).
