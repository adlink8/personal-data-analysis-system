# Conversation domain

## Responsibility

Rules, models, and constants for conversation structure (canonical
sessions/messages). After Phase 21, **build/eval orchestration no longer lives here**.

## Boundaries

- No retrieval ranking, UI, or direct production promotion.
- No LLM client primitives (those are in `core/llm.py`).

## Canonical locations (Phase 21)

| Kind | Package |
|------|---------|
| Build / summary / graph / vector-store | `personal_knowledge.application.conversation` |
| Eval / compare / eval-set | `personal_knowledge.evaluation.conversation` |
| LLM client + retry | `personal_knowledge.core.llm` |

Files in this package named `build_*.py` / `evaluate_*.py` / etc. are
**re-export facades** (cleanup window through **2026-08-13**). Prefer importing
the application/evaluation path in new code.

## Tests

Conversation normalization and contract tests under `tests/`.

## Ownership

Owner: conversation. Status: supported. Last layout review: Phase 21 (2026-07-15).
