# Phase 23 Research: Composite SSOT Snapshot Integrity

**Researched:** 2026-07-17
**Scope:** Current repository implementation, live contracts and Target A audit findings

## Research Summary

The project already has the right primitives but lacks one authority that composes them. `knowledge_index_versions` records Chroma versions, `knowledge_source_watermark` records KU source progress, canonical Conversation and Google have publish flows, and the active collection is projected through `knowledge_index_active.txt`. Retrieval currently resolves these independently. The smallest safe design is an immutable SQLite snapshot manifest plus one active-snapshot row, with the text pointer retained only as a compatibility projection.

## Current Facts

1. `promote_knowledge_index.promote()` updates `knowledge_index_versions` and commits before atomically replacing the text pointer. A process interruption can therefore expose two active interpretations.
2. `semantic_search.search_knowledge_units()` reads the text pointer, queries Chroma, and separately reads SQLite version metadata. Fallback layers have telemetry but no common snapshot id.
3. The KU schema already has build ids, canonical build linkage, counts, checksum and status. It can seed a snapshot without duplicating private content.
4. Conversation, Turn and Google pipelines already create stable databases/collections and support dry-run or lifecycle commands, but no common version/watermark registry binds them to serving.
5. Evidence refs are distributed across KU evidence tables, canonical conversation rows and Google assertions. Service surfaces expose pieces, not one typed resolver.
6. Governance path rules require metadata but do not define semantic layer identity or single serving authority.

## Recommended Architecture

### Runtime schema

- `artifact_versions`: immutable runtime versions keyed by `artifact_version_id`; includes registry id, version/checksum, location kind, privacy, lifecycle and sanitized metadata.
- `source_watermarks`: per registry id/source key monotonic watermark with artifact version link. Keep `knowledge_source_watermark` as a compatibility view/projection during migration.
- `serving_snapshots`: immutable manifest JSON/hash plus named artifact version columns needed for indexed validation.
- `serving_snapshot_members`: normalized snapshot-to-artifact bindings by serving role.
- `serving_authority`: singleton row naming the active snapshot, updated in one transaction after all validation.
- `serving_snapshot_events`: append-only prepare/validate/activate/rollback/refuse journal.

Use foreign keys, uniqueness on `(snapshot_id, serving_role)`, checks for layer/lifecycle values, and triggers or application guards that prohibit mutation of active snapshot contents.

### Tracked registry

Store sanitized definitions under governance, following existing YAML policy style. Each entry defines `id`, `layer`, `kind`, `authority_role`, `producer`, `consumers`, `privacy`, `evidence_parent`, `lifecycle`, `version_source` and validation requirements. A deterministic loader validates dependency direction D→S→R/A and uniqueness.

### Publish protocol

`prepare_snapshot` resolves immutable member versions and writes a draft. `validate_snapshot` checks registry coverage, SQLite FK/integrity, Chroma existence/count/checksum, evidence resolution, gate reference and watermark monotonicity. `activate_snapshot` runs one transaction changing only `serving_authority` and appending an event. After commit, it writes the legacy pointer and immediately verifies parity; readers use `serving_authority`, so projection failure does not split authority. `rollback_snapshot` activates a prior validated snapshot by the same mechanism.

### Read protocol

A `ServingSnapshotResolver` opens a read transaction and returns the active snapshot and members once per request. Retrieval uses its KU collection and permitted fallback layer versions. A typed evidence resolver accepts `{artifact_type, ref}` or prefixed refs and returns sanitized evidence plus eligibility and version provenance. CLI/REST/MCP responses add fields without removing current ones.

## Risks and Mitigations

- **Live data migration:** bootstrap as draft, validate read-only, activate only with explicit `--write`; tests use temporary DBs.
- **Chroma unavailable:** status/doctor reports unavailable member and activation fails; existing active authority remains.
- **Compatibility callers:** keep `knowledge_index_active.txt`, current tables and command names; route their writers/readers through the new authority.
- **Cross-database evidence:** use a resolver with explicit adapters and integrity reports, not impossible SQLite FKs across files.
- **Registry overreach:** registry metadata only; do not move payloads or invent a new storage engine.

## Validation Architecture

### Unit tests

- Registry schema/uniqueness/dependency validation.
- Snapshot manifest canonical hashing, immutability, watermark monotonicity and pointer projection.
- Evidence resolver prefixes, eligibility/privacy redaction and missing-ref semantics.

### Integration tests

- Candidate prepare → validate → activate; injected failure before/after activation leaves one authoritative snapshot.
- Rollback restores prior snapshot and pointer parity.
- Search resolves exactly one snapshot and all returned layer versions belong to it.
- Conversation/Turn/Google/KU version advancement is idempotent; watermark cannot precede publication or regress.

### Contract and governance tests

- CLI/REST/MCP retain existing fields and add snapshot/version metadata.
- Registry covers required production artifacts and rejects duplicate authority/unknown ids.
- Doctor exits non-zero on split state, invalid evidence, drift or missing critical member.

### Phase verification

- Targeted tests for all new modules.
- `python -m personal_knowledge.governance.preflight --ci`.
- `python -m pytest -q`.
- Read-only live bootstrap/doctor proof; no active change unless an explicit, separately evidenced write is required.

## RESEARCH COMPLETE
