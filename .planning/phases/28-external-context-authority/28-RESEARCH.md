---
phase: 28
status: complete
researched: 2026-07-18
model: gpt-5.6-luna
---

# Phase 28 Research

## Existing patterns to reuse

- `core/project_paths.py` for cwd-independent database paths.
- `core/sqlite.py` for FK-enabled read/write connections and integrity checks.
- Intelligence `schema.py`/`runs.py` modules for canonical JSON, stable IDs,
  checksums, idempotency and privacy-key rejection.
- `application/serving/snapshots.py` for prepare→validate→activate→rollback,
  but implemented in independent external tables/authority.
- Governance artifact registry for typed D/S layers and dependency direction.

## Key risks

1. Reusing personal `serving_authority` would couple different update cadences.
2. SQLite has no cross-database FK; dual snapshot binding needs application-level
   exact hash validation on every create/read.
3. Raw public content can carry copyright, SSRF and prompt-injection risk; LLMs
   may consume canonical facts only, never raw HTML.
4. Source quality is policy output, not fact truth confidence.
5. Small pilot samples cannot prove long-term or causal value.

## Minimal first slice

Independent DB path, tracked two-source allowlist, append-only registry/schema,
explicit `--write` migration, metadata-only source list/get/status and focused
unit/integration/contract tests. Ingest and snapshots follow in later plans.
