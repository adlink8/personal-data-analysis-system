# Plan 21-04 Summary: Memory + Retrieval Legacy + Finalization

**Completed:** 2026-07-15  
**Status:** done  
**Wave:** 3

## What shipped

1. **16 memory build/lifecycle → `application/memory/`** + facades.
2. **6 memory eval/compare/analyze/audit → `evaluation/memory/`** + facades.
3. **4 retrieval legacy eval/compare → `evaluation/vector/`** with facades left in `retrieval/`.
4. **run_pipeline** STEP_MODULES: zero `domains.*` values (all `application.*`).
5. Hint strings in `tools/supported/build_generation_gap_analysis.py` → `evaluation.vector.*`.

## D-08 triple gate

| Gate | Result |
|------|--------|
| pytest | 13 known baseline fails only (8 governance + 5 memory_decomplexity) — **no new fails** |
| architecture-boundary | **PASS** |
| REST :8000 /health | **200** |
| MCP :8789 /health | **200** |
| domains slim | **42 facades** + `migrate_add_knowledge_unit_tables.py` only |

## Known residual / blockers

- **Full `preflight --ci`:** several non-architecture gates still FAIL (inventory `rolled-back-legacy`, shim-budget 85, docs-coverage, secret-scan, artifact-lineage, storage-retention). These match pre-phase governance baseline debt; architecture-boundary itself PASSes.
- **`source_manifest --cohort all`:** fails on missing `integration/scripts/_tools/_audit_raw_fallback_coverage.py` (stale inventory path — pre-existing, not introduced by Phase 21 moves). Manifest refresh blocked until inventory repaired.

## Phase success criterion

`domains/` contains no build/evaluate/compare/analyze/audit **logic** — only re-export facades (cleanup window 2026-08-13) + schema constant + `__init__.py`.

## Self-Check: PASSED
