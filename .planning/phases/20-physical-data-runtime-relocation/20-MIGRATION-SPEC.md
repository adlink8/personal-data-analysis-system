# Phase 20 R3/R4 Migration Safety Contract

## Complete disposition

Phase19 final reconcile inventory is authoritative and is diffed against the Phase18 baseline. Every non-`.git` node receives exactly one `relocate`, `retain-in-place`, or `protected-external` decision. Explicit coverage includes `Agent`, `Google`, `imports`, `integration/{raw_index,structured,db,runtime,analysis}`, integration root logs/JSON, root logs/HTML/cache, `_recycle`, `.gsd`, `.ai-bridge`, `__pycache__`. `.agents/.codex/.workbuddy/.github/.planning/governance` and reviewed root configs are retained in place because tools require them. `.pytest_cache` moves through pytest `cache_dir=var/cache/pytest`; `__pycache__` is regenerated under policy and excluded from migration.

## Common Windows protocol

Discover/stop writers → lock cohort → resolve workspace paths → reject reparse/case/Unicode collision → check same volume/capacity → stage-copy → type-specific validation → old→backup atomic rename → stage→target atomic rename → atomically switch config/pointer → read-only smoke → retain backup. Partial failure reverses the journal only after verifying current preconditions.

## Type-specific consistency

- SQLite: use online backup API while source is live or stop writer + `wal_checkpoint(TRUNCATE)`; validate `integrity_check`, schema SQL, tables/indexes/triggers/FKs, row counts and deterministic logical checksums. WAL/SHM never copied independently.
- DuckDB: require all writers/readers closed; copy database; reopen read-only and compare schema/count/checksum.
- Chroma: stop writer, snapshot collection/persist generation, compare collection IDs/count/embedding metadata; switch active pointer atomically only after validation; rollback restores pointer and generation identity.
- Ordinary R3/R4 files: default metadata/size hash policy; content digest only with explicit local authorization; preserve timestamps/ACL where required.
- `_recycle` requires separate approval authorizing local streaming byte/chunked-Merkle hashing solely for integrity. The tool never parses or emits content; only the ignored local digest root is compared after stage, cutover and rollback.

Each cohort follows preview auto task → human approval checkpoint → apply auto task → verification auto task → rollback-drill checkpoint. Alias is a config fallback by default, not a junction; removal requires 30-day or one-release telemetry with zero old-path consumers and separate approval.
