# Retrieval infrastructure
## Responsibility
Vector build/search adapters and layered retrieval composition.
## Boundaries
Index implementations sit behind contracts; no ownership of knowledge semantics.
**Phase 21:** collection/retrieval *evaluation* scripts moved to
`evaluation/vector/`. Files here named `evaluate_vector_*` /
`compare_*_generations` are re-export facades (cleanup **2026-08-13**).
## Entry points
Use vector builders and unified search contracts in this package.
Prefer `python -m personal_knowledge.evaluation.vector.evaluate_vector_collections`
for health checks.
## I/O and privacy
Embeddings/indexes are R3 private generated artifacts with generation lineage.
## Tests
Vector, retrieval, fallback and evidence contract tests under `tests/`.
## Ownership
Owner: retrieval. Status: supported. Last layout review: Phase 21 (2026-07-15).

