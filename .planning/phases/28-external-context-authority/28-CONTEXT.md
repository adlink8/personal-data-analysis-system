---
phase: 28
status: ready_for_planning
created: 2026-07-18
requirements: [PDI-01, PDI-02, PDI-03, PDI-04]
---

# Phase 28 Context

## Boundary

Phase 28 creates an independent public External Context Authority. It does not
call an LLM, write Personal KU/State, join the personal serving authority, or
perform automatic external actions.

## Locked Decisions

- Separate database: `var/db/external_context.sqlite`.
- Initial scope: one `project/technology` topic and two allowlisted public
  sources; metadata and bounded structured facts only, no full copyrighted body.
- Authority chain: Source Registry → Observation → Canonical Fact → Lifecycle
  Event → External Snapshot.
- Source quality and fact confidence are separate versioned judgments.
- Lifecycle is append-only; corrections and conflicts create events/new rows,
  never UPDATE/DELETE authoritative history.
- External snapshots are independent from the personal serving authority.
- A DecisionContextBinding stores both Personal and External snapshot IDs/hashes
  and validates both read-only because SQLite cannot enforce cross-DB FKs.

## Deferred

Network fetch, generic crawling, REST/MCP expansion, LLM analysis and real
decision recommendations are not part of 28-01. Phase 28-01 stops at schema,
registry, dry-run migration and metadata-only read CLI.
