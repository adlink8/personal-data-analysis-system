# Phase 23: Composite SSOT Snapshot Integrity - Context

**Gathered:** 2026-07-17
**Status:** Ready for planning
**Source:** Autonomous smart discuss using the accepted Target A-D closure objective

<domain>
## Phase Boundary

Close Target A by making the product's serving state explicit and verifiable. This phase introduces a typed D/S/R/A artifact registry, an immutable serving snapshot that binds structured and vector versions, authoritative evidence views, and version/watermark tracking for Conversation, Turn, Google and KU. It extends existing stage/gate/promote/rollback flows; it does not replace SQLite, Chroma, the current canonical stores, or Phase 17 quality evaluation.

In scope: schema/contracts, read and publish authority, product CLI/doctor exposure, governance gates, migration of the current active state into the new registry, drift/rollback tests and operating documentation.

Out of scope: changing embedding/LLM models, paid extraction, promoting a failing candidate, completing human Gold/Judge work, generating personal recommendations, deleting legacy/raw/history, or writing AgentView live data.

</domain>

<decisions>
## Implementation Decisions

### Typed layer registry
- **D-23-01:** Use four namespaces: D (source/canonical data), S (semantic artifacts such as Turn/KU/profile candidates), R (retrieval/index artifacts), and A (analysis/evaluation/intelligence outputs). Every registered artifact declares stable id, layer, authority role, version, producer, consumers, privacy, lifecycle and evidence parent.
- **D-23-02:** The registry is a tracked declarative contract plus a runtime SQLite registry. Tracked definitions contain no private payload; runtime rows hold versions/checksums/watermarks without raw private text.
- **D-23-03:** Exactly one authoritative artifact is allowed per declared serving role in a snapshot. Unknown artifact types, duplicate authorities, invalid dependencies and missing required metadata fail governance validation.

### Composite serving snapshot
- **D-23-04:** Readers resolve one immutable `serving_snapshot_id`; they do not independently read mutable SQLite status and the text active pointer.
- **D-23-05:** A snapshot binds canonical conversation version, Turn version, Google version, canonical KU build, Chroma collection/checksum, eval gate reference and source watermarks. Activation is one atomic SQLite transaction; the legacy pointer becomes a compatibility projection written after activation and verified against the active snapshot.
- **D-23-06:** Prepare/validate and activate are separate operations. Validation proves collection existence/count/checksum, canonical build linkage, evidence integrity, watermark monotonicity and gate PASS before activation. Any failure leaves the previous snapshot active.
- **D-23-07:** Rollback activates a prior immutable snapshot and regenerates compatibility projections; it never edits historical snapshot contents or deletes collections/rows.

### Evidence authority
- **D-23-08:** Provide a single read-only evidence resolver for KU, Turn, Canonical Message and Google signal refs. It returns stable ids, layer/type, source version, eligibility/privacy metadata and sanitized content only when explicitly allowed.
- **D-23-09:** Search results and fallback telemetry include `serving_snapshot_id` plus relevant layer version. Cross-layer fallback may use only versions named by the resolved snapshot; unavailable or drifted layers are skipped with an explicit reason, not silently mixed.

### Source versions and product operations
- **D-23-10:** Conversation, Turn, Google and KU maintain independent monotonic versions and watermarks. A watermark is advanced only after its artifact is published and, when it is part of serving, included in an activated snapshot.
- **D-23-11:** Extend `pk-sync` with auditable `status`, Turn and Google product paths while preserving dry-run default. Existing `pk-sync conversations` and `pk-ku` commands remain compatible.
- **D-23-12:** Extend `pk-ku doctor` and governance preflight with registry coverage, active snapshot integrity, compatibility-pointer parity, evidence resolver checks and version/watermark drift detection.

### Safety and migration
- **D-23-13:** Bootstrap the current active state without promotion or paid calls. If any required fact cannot be proven, create a non-active draft snapshot and report the missing proof.
- **D-23-14:** No hard delete, no AgentView writes, no automatic candidate promotion, no weakening of privacy/eval gates, and no new production dependency.

### the agent's Discretion
- Exact module/file split, SQL migration numbering, CLI subcommand spelling and whether the tracked registry uses YAML or JSON, provided existing package conventions and compatibility contracts are preserved.
- Whether compatibility pointer repair is an explicit doctor repair command or part of snapshot activation; all default doctor/status commands remain read-only.

</decisions>

<canonical_refs>
## Canonical References

### Program scope
- `.planning/TARGET-GAP-ANALYSIS-2026-07-17.md` — Target A exit conditions and Target D dependency order.
- `.planning/ARCHITECTURE-LAYERING-DATA-GOVERNANCE-AUDIT-2026-07-17.md` — D/S/R/A definitions and unresolved architecture findings.
- `.planning/REQUIREMENTS.md` — FOUND-01..05 acceptance requirements.

### Current architecture and operating contracts
- `docs/architecture/retrieval-ssot.md` — current dialogue/knowledge/non-dialogue authority and fallback contract.
- `docs/runbooks/product-sync.md` — current product sync and rollback path.
- `docs/runbooks/ku-incremental.md` — stage/gate/promote/watermark hard rules.
- `governance/policies/architecture.yaml` — allowed dependency direction.
- `governance/policies/paths.yaml` — artifact metadata and privacy zones.

### Existing implementation anchors
- `src/personal_knowledge/application/knowledge/promote_knowledge_index.py` — current split DB/pointer promote and rollback behavior to replace behind compatibility.
- `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py` — canonical KU schema migration pattern.
- `src/personal_knowledge/retrieval/semantic_search.py` — shared layered search and version telemetry.
- `src/personal_knowledge/application/sync.py` — `pk-sync` product entry.
- `src/personal_knowledge/application/knowledge/doctor_ku.py` — read-only product health pattern.
- `src/personal_knowledge/core/project_paths.py` — path SSOT.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- Atomic file replacement exists for the legacy active pointer; SQLite write connections already enforce FK integrity.
- `knowledge_index_versions`, `knowledge_source_watermark`, extraction/eval gate artifacts and promote logs already provide most inputs needed to construct a snapshot.
- Canonical conversation normalization, Google stage/gate/promote, KU reconcile, read-only doctor and layered search all have focused tests and can be extended rather than rebuilt.

### Established Patterns
- Product mutations are dry-run first and follow stage → validate/gate → promote → journal → rollback.
- SQLite is the structured authority; Chroma is rebuildable retrieval space.
- CLI, REST and MCP share retrieval backends. New serving metadata belongs in the backend response rather than three separate implementations.
- Private runtime manifests live under `var/`; tracked governance files contain sanitized definitions only.

### Integration Points
- `promote_knowledge_index.promote()` currently commits SQLite status before writing the active pointer, creating the split window this phase closes.
- `semantic_search.search_knowledge_units()` independently reads the pointer and then SQLite version metadata; it must instead resolve a snapshot once.
- Turn vector building and Google lifecycle are separate module paths and lack a shared product version/watermark surface.
- Existing evidence refs (`cm|`, `g|`, KU ids and Turn ids) are present but lack one authoritative resolver/view.

</code_context>

<specifics>
## Specific Ideas

- Preserve the user's preference for evidence-first, local-only, reversible operations.
- The active snapshot id should be visible in CLI/REST/MCP responses so drift reports are actionable.
- Migration must be safe on the live private DB and fully testable against temporary SQLite/Chroma fixtures.

</specifics>

<deferred>
## Deferred Ideas

- Human Gold/Judge/UAT and quality threshold remediation — Phase 24.
- Real lifecycle adoption and current/history product proof — Phase 24.
- Personal state/change models, recommendations and proactive intelligence — Phases 25-27.
- Cleanup of compatibility backups/facades before their retention windows expire.

</deferred>

---
*Phase: 23-composite-ssot-snapshot-integrity*
*Context gathered: 2026-07-17 via autonomous smart discuss*
