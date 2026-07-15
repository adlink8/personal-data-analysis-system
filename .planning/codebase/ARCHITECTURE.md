# Architecture and Governance Design

**Mapped:** 2026-07-13  
**Intent:** sustainable architecture for the complete repository, including every descendant file, without treating private data or generated artifacts as source code.

## Current system shape

The production flow is a personal-data knowledge system:

```text
AgentView / Google / imports
        │ read-only adapters
        ▼
canonical conversations + normalized events
        ▼
L1/L2 knowledge units ── evidence/lineage
        ▼
memory + graph + vector indexes
        ▼
unified retrieval
        ▼
API / MCP / dashboard / evaluation
```

The domain packages under `integration/scripts/` reflect this direction, but the repository boundary is blurred by private data, generated reports/databases, 86 legacy root shims, old Google scripts, and two planning histories (`.planning` and `.gsd`).

## Target layers and dependency rule

| Layer | Packages/surfaces | May depend on |
|---|---|---|
| Control plane | governance policy, `.planning`, CI | metadata/contracts only |
| Delivery | `services`, app UI/MCP | application, public contracts |
| Application | `pipeline`, use-case commands, promotion coordinator | domains, retrieval, ports |
| Evaluation | `evaluation`, eval contracts/gates/report renderer | public domain/retrieval interfaces; never hidden production mutations |
| Domain | conversation, knowledge, memory, graph | core contracts and explicit ports |
| Infrastructure | vector, repositories, source adapters, model clients | core contracts, external libraries |
| Foundation | `core` paths/config/IDs/contracts | standard library and narrow third-party utilities |
| Data plane | raw, staging, canonical DBs, indexes, reports | no code dependencies; accessed through ports |

Enforced direction:

```text
delivery → application → domain → foundation
                    ↘ infrastructure via ports
evaluation → public application/domain/retrieval contracts
data plane ← adapters/repositories only
```

Forbidden directions include domain-to-service, core-to-domain, production-to-`_tools`, source-to-`_recycle`, and any module reading raw/private paths directly when an adapter exists.

## Bounded contexts

### Ingestion and provenance

Owns source snapshots, canonical source IDs, hashes, eligibility/privacy filtering, and idempotent staging/publish. AgentView must remain read-only. Google/import inputs are immutable. Each downstream row must trace to a source reference and run manifest.

### Conversation

Owns canonical sessions/messages and conversation-derived summaries. It must not know retrieval ranking or UI details.

### Knowledge units

Owns L1/L2 extraction, evidence links, canonical merge, lifecycle, candidate indexes, promotion journal, and rollback. L2 is an extraction strategy inside the same knowledge contract, not a parallel database architecture.

### Memory and graph

Own durable memory candidates/decisions and relations between stable entities. These domains consume knowledge/evidence contracts; they do not scrape raw sessions again.

### Retrieval

Owns the query contract and ranking composition across KU, canonical messages, Google events, and controlled fallback. Index implementations are infrastructure behind named adapters. Search results must include layer, source, score, evidence ID, index generation, and fallback reason.

### Evaluation and promotion

Owns frozen/private suites, ablations, metrics, confidence intervals, answer/judge calibration, visual reports, gates, and comparison history. Promotion is a state transition allowed only from a signed evaluation result; evaluation itself must not silently mutate the active pointer.

## Stable contracts

The architecture should standardize five contracts before further moves:

1. `SourceRecord`: source, source_ref, timestamp, content hash, privacy/eligibility, snapshot/run ID.
2. `EvidenceRef`: immutable link from derived fact to canonical source span/message/event.
3. `KnowledgeUnit`: stable ID, L1/L2 strategy, type, statement, evidence, temporal scope, status, generation.
4. `SearchResult`: query, result ID/type/layer, score/rank, evidence, generation, fallback metadata.
5. `RunManifest`: command/version/config/input hashes/output generation/counts/gates/status/rollback target.

These contracts should be schema-versioned and shared through `core` or a dedicated contracts package. Databases, CLI JSON, MCP/API responses, reports, and tests must validate the same schemas.

## Configuration and path architecture

`core.project_paths` should be the sole default path resolver. Configuration precedence:

```text
explicit CLI argument
→ environment variable / local untracked config
→ repository-relative default
→ clear error (never a user-specific fallback)
```

Required named locations include repository root, private data root, runtime root, report root, AgentView database, Google input root, Chroma endpoint/path, and cloud SDK command. Secrets belong in credential providers/environment variables and must never enter manifests or reports.

## Build, publish, and rollback architecture

All materialized data products follow one lifecycle:

```text
immutable input snapshot
→ run manifest
→ staging generation
→ contract + quality + privacy evaluation
→ candidate pointer
→ canary
→ atomic active-pointer promotion
→ post-promote verification
→ retained rollback generation
```

No builder writes directly into the active generation. Reports and charts are immutable outputs keyed by evaluation run ID. A failed gate leaves active pointers and production databases unchanged.

## Repository governance as a control plane

Project governance is not documentation decoration. It is an executable control plane with four artifacts:

1. **Policy schema** — valid file classes and mandatory fields.
2. **Ordered path manifest** — glob rules for every repository surface.
3. **Local inventory** — expansion of those rules to every last file using metadata-only inspection for private areas.
4. **Validator/report** — CI-safe checks plus a local private-aware report.

Each file is classified as one of:

`source`, `test`, `config`, `documentation`, `prompt/eval asset`, `vendor`, `private_raw`, `private_canonical`, `generated`, `runtime`, `compatibility`, `tool`, `planning`, or `archive/quarantine`.

The manifest is authoritative; directory READMEs explain only human-facing boundaries. This avoids duplicated rules and stale leaf documentation while still governing arbitrary depth.

## Governance gates

### Pull request gates

- manifest coverage and non-overlap;
- tracked/ignored classification agreement;
- architecture import-direction check;
- canonical-entry/shim-forwarding check;
- hard-coded absolute-path check;
- secret and private-data signature scan;
- pytest discovery restricted to `tests/`;
- generated artifact drift/provenance check;
- prompt/schema/eval version-contract check;
- planning status consistency.

### Release/data-promotion gates

- migration/schema compatibility;
- idempotence and staging isolation;
- source/evidence lineage completeness;
- privacy/secret hit zero;
- comprehensive retrieval and answer-quality comparison;
- latency/storage guardrails;
- canary plus rollback drill;
- signed run manifest and active-pointer journal.

### Scheduled maintenance

- orphan/unclassified file report;
- unused compatibility shim report;
- archive/quarantine retention expiry;
- database backup restore drill;
- dependency and vendor provenance review;
- docs-to-code command verification;
- evaluation trend and regression dashboard.

## Compatibility strategy

The 86 root shims are a migration API, not a second implementation tree. Create a compatibility registry containing legacy path/import, canonical module, consumer count, deprecation date, removal gate, and parity test. Migrate in this order:

1. internal pipeline subprocess calls;
2. tests and documentation;
3. local scheduled tasks/MCP configs;
4. external/manual consumers;
5. removal after telemetry and deprecation window.

Until removal, root shims must remain logic-free. Duplicate module names such as `test_knowledge_unit_llm.py` must be kept out of pytest discovery or renamed away from test conventions.

## Data privacy and archive boundaries

- `Google/raw`, `imports`, Agent databases, `integration/db`, private evals, and session stores are restricted data planes.
- Governance tooling may list relative path, size, timestamps, file type, rule match, and locally computed checksum; it must not upload or include content excerpts.
- `_recycle` is quarantine, not backup and not source. It needs an index, origin, quarantine reason, retention deadline, and restore/delete decision.
- `.ai-bridge` is external reference code. Pin source URL/revision/license/checksum and prohibit implicit imports.
- Vendor assets under `integration/lib` need version/license/checksum; minified bodies are excluded from ordinary code/search audits.

## Testing architecture

Tests should be grouped logically even if the physical `tests/` directory remains flat:

- unit: pure domain and metrics;
- contract: schemas, adapters, CLI/API/MCP;
- integration: SQLite/Chroma/staging/promotion;
- evaluation: deterministic frozen suites and judge calibration;
- end-to-end: source snapshot to retrieval/answer report;
- governance: manifest, dependency, path, privacy, generated-output rules.

Use pytest markers and a test manifest so every production module maps to a verification class or documented exemption. Full collection must exclude `_recycle`, external reference trees, runtime output, and duplicate legacy test modules.

## Operational ownership

Every manifest rule and public entry point needs an owner role, not necessarily a person:

- platform: core, configuration, shims, CI;
- data: ingestion, canonical stores, lineage, retention;
- knowledge: extraction, memory, graph, retrieval;
- evaluation: suites, metrics, gates, reports;
- application: MCP/API/dashboard;
- governance: planning consistency, manifest policy, release evidence.

Changes crossing two bounded contexts require a contract test; changes crossing data/promotion boundaries require rollback evidence.

## Phase 18 recommended execution slices

1. **Inventory and policy:** manifest schema, full metadata-only inventory, ownership/classes, zero-unclassified baseline.
2. **Boundary enforcement:** import graph, test discovery, vendor/quarantine isolation, `.planning` SSOT decision.
3. **Paths and artifacts:** centralized path/config migration, data/generated/runtime separation, run-manifest provenance.
4. **Entry-point convergence:** canonical module commands, shim registry and cohort retirement, scheduled-task/MCP migration.
5. **Quality automation:** CI/local governance gates, comprehensive test matrix, secret/private checks.
6. **Operational closeout:** restore/rollback drills, retention policy, docs/runbooks, dashboard and maintenance cadence.

Each slice must be reversible and should move files only after the manifest can prove their old and new classifications.

## Architecture acceptance criteria

- every repository file has exactly one governance rule and owner/lifecycle classification;
- all maintained code respects the dependency direction;
- all source access passes through adapters/repositories and all derived facts preserve evidence lineage;
- mutable/generated/private assets are outside the tracked source plane;
- one planning system is authoritative;
- canonical entry points are documented and tested; compatibility debt is measurable and declining;
- evaluation gates control promotion and produce reproducible JSON plus visual reports;
- a fresh machine can configure paths without editing source;
- CI catches structural drift before merge, while local metadata-only checks cover private files safely.
