# Graph domain

## Responsibility

**Compat package only.** Build/judge/query orchestration lives under
`application.graph`; eval under `evaluation.graph`. Modules here are re-export
facades.

`build_graph_relation_candidates_v2` was **deleted** (dead code).

## Canonical locations

| Kind | Package |
|------|---------|
| Build / judge / query / triple-store | `personal_knowledge.application.graph` |
| Eval judgments | `personal_knowledge.evaluation.graph` |

Do not add new logic under `domains/graph/`.

## Ownership

Owner: graph (compat). Status: re-export only.
Last layout review: 2026-07-16 (Phase 22; facade debt clear).
