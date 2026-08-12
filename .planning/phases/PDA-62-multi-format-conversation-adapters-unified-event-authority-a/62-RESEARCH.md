# Phase 62: Multi-format conversation adapters, unified event authority, and replaceable extraction views - Research

**Researched:** 2026-08-12
**Domain:** Local multi-format agent-session ingestion, event normalization, lineage, and evidence-bound extraction
**Confidence:** HIGH for local architecture and observed formats; MEDIUM for vendor-format stability

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- Cover all 17 families observed in the live inventory with an explicit adapter/fidelity result; do not silently flatten unsupported or partial input.
- Capture allowlisted native artifacts into content-addressed immutable snapshots; use SQLite online backup for live WAL databases and exclude credential/account/token/auth data.
- Keep raw snapshots as byte-level evidence authority and canonical v2 typed events as semantic authority; preserve safe unmodeled data through resolvable native references.
- Reuse and evolve the existing canonical database, `pk-sync`, publication/watermark/rollback, and repository seams. Add v2 event generations; retain old canonical tables as compatibility projections.
- Model typed events and first-class relations. Keep fidelity/unknown/partial states explicit.
- Treat trace as a replaceable derived episode view, not permanent authority. Build turn, trace, episode, compaction, session, topic, and cross-session views under a versioned extraction policy.
- Give compaction summaries highest initial scheduling priority but never higher truth authority than their supporting events.
- Run deterministic privacy/structure/evidence gates before an abstention-capable LLM semantic-value gate.
- Keep quarantined KU isolated and active KU empty. Do not execute the existing 24,487-call message-level queues or any paid provider work without a later explicit cost approval.

### the agent's Discretion

- Exact v2 schema/type names and parser primitive sharing.
- Exact deterministic episode heuristics and redacted fixture sampling.

### Deferred Ideas (OUT OF SCOPE)

- Paid full-corpus extraction or semantic labeling.
- Deleting old raw/canonical/KU/ledger/vector artifacts.
- Removing compatibility tables before all consumers migrate.
</user_constraints>

<architectural_responsibility_map>
## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Native artifact discovery/capture | Adapter boundary | Storage | Source-specific discovery and read-only capture belong outside domain rules; immutable blobs/manifests are storage authority. |
| Native parsing | Adapter boundary | Deterministic core | Parsers translate vendor records to a stable contract without owning publication or truth. |
| Canonical event identity/relations/fidelity | Deterministic core | Storage | These are cross-source semantic invariants and must not vary by UI or LLM behavior. |
| Event generation activation/rollback | Application orchestration | Storage | Existing Python publication/watermark/rollback authority remains exclusive. |
| Derived views and extraction policy | Deterministic application | Evaluation | Views are reproducible projections; policy ranks them without changing evidence. |
| Semantic-value decision | Evaluation/provider seam | Candidate staging | Model output is an abstention-capable judgment, never an authority write. |
| Compatibility messages/repository | Read projection | Application | Existing consumers receive a stable lossy view of the active event generation. |
</architectural_responsibility_map>

<research_summary>
## Summary

The current project stores one canonical row per flattened message and separate tool metadata. This is sufficient for legacy retrieval, but it cannot preserve native reasoning events, compaction ranges, branch/DAG structure, call/result relations, loop boundaries, or source-specific fidelity. The correct migration is not a second permanent conversation SSOT: it is a versioned event generation inside the existing canonical authority, with immutable raw evidence behind it and the old tables rebuilt as compatibility projections.

The 17 live families fall into reusable structural clusters, but not one universal parser. JSONL event streams, UUID DAGs, directory bundles, single JSON transcripts, and SQLite-backed stores require different capture and ordering rules. Sharing scanner/decoder primitives is safe; sharing a family-agnostic “message extractor” is not. Every family needs detection, schema/version probing, native-location preservation, redacted fixtures, and an explicit capability/fidelity report.

AgentsView provides useful patterns but not a reusable authority. Its current upstream documents broad read-only discovery and local SQLite aggregation, exposes parser capabilities and transcript fidelity, and its recall implementation contains strong guarded-evidence ideas: transcript revisions, bounded evidence windows, authorization/content digests, atomic commit guards, revocation when evidence drifts, quiet periods, and resumable progress. These should be adapted to stable event IDs and replaceable views. Its flattened message/ordinal model and session-window extraction should not be copied.

**Primary recommendation:** evolve canonical into a generation-bound typed event store, retain immutable native evidence, treat all extraction units as versioned views, and require evidence-event binding plus deterministic and semantic gates before any future paid extraction.
</research_summary>

<standard_stack>
## Standard Stack

### Core

| Library/tool | Version | Purpose | Decision |
|---|---:|---|---|
| Python | Project-supported runtime | Adapter contracts, deterministic transforms, evaluation | Reuse existing application/core/evaluation layers. |
| `sqlite3` | Python stdlib / system SQLite | Online backup, staging generations, relational event authority | Existing proven project seam; no new production dependency. |
| `json` / streaming line iteration | Python stdlib | JSON/JSONL decoding | Bound memory and preserve source locators per record. |
| `hashlib` | Python stdlib | Content addressing, identities, dataset/view digests | Existing checksum convention. |
| `pathlib` | Python stdlib | Explicit validated source paths | Existing Windows-safe path convention. |
| `pytest` | Existing project version | Unit/contract/integration/fault-injection tests | Existing engineering contract. |

### Supporting

| Existing project asset | Purpose | When to use |
|---|---|---|
| `AgentViewAdapter.snapshot` | Read-only WAL-safe SQLite backup | AgentsView capture and as the pattern for all live SQLite sources. |
| serving/artifact version registry | Generation/version/watermark binding | Active v2 event generation and compatibility projection publication. |
| `ConversationRepository` | Existing consumer contract | Compatibility projection parity and staged consumer migration. |
| deterministic/replay provider patterns | Zero-cost model contract tests | Semantic gate implementation before any paid pilot. |

### Alternatives Considered

| Instead of | Could use | Why rejected/deferred |
|---|---|---|
| Existing canonical DB with v2 tables | A separate event database | Creates a second long-lived conversation authority and duplicate publication/rollback state. |
| Typed relational events + raw refs | One JSON blob per session | Weak query/constraint/lineage behavior; encourages reparsing in every consumer. |
| Family-specific adapters with shared primitives | AgentsView flattened messages | Loses native event types and relations already observed in local artifacts. |
| Project-owned model types | OpenTelemetry trace schema | Useful analogy, but coding-agent conversation semantics and evidence fidelity do not map cleanly to span-only authority. |

**Installation:** no new production dependency is required or authorized.
</standard_stack>

<format_matrix>
## Observed Source Format Matrix

| Family | Native shape observed | Critical semantics | Adapter implication |
|---|---|---|---|
| Codex | JSONL event stream | `session_meta`, `turn_context.turn_id`, messages, reasoning, function call/output, `context_compacted` | Preserve top-level event type, turn ID, call/result link, and compaction boundary. |
| Claude | JSONL UUID DAG | `uuid`, `parentUuid`, `isSidechain`, content blocks, stop reason | Topological/parent relations are authoritative; file order alone is insufficient. |
| Qoder | Claude-like JSONL DAG | explicit `isCompactSummary` | Reuse DAG primitives but keep Qoder detector/schema and compaction contract. |
| Pi | JSONL event stream | independent compaction record with `summary`, `firstKeptEntryId`, `tokensBefore` | Compaction is a typed event and range relation, not a user message. |
| Workbuddy | JSONL | message/reasoning/function_call/function_call_result | Preserve reasoning and call/result as separate linked events. |
| Kimi / Kimi-work | JSONL loop protocol | turn prompt, context append, loop/task lifecycle | Model loop/task boundaries are first-class episode hints. |
| Grok | Multi-file session directory | summary, transcript, events, updates, compaction/checkpoint/recap files, subagents, terminal | Snapshot a declared file set and preserve cross-file relationships; summary-only fidelity is partial. |
| ZCode | SQLite virtual locator | native trace/turn IDs; text/reasoning/tool/step/compaction parts | Online backup and allowlisted conversation tables; preserve trace IDs without making trace universal. |
| MimoCode / OpenCode | SQLite virtual locator | conversation rows plus sensitive adjacent account/token tables | Strict table/column allowlists and negative tests against credential tables. |
| Antigravity | SQLite trajectory store | trajectory, step, subtrajectory | Preserve hierarchical trajectory relations and explicit partial transcript fidelity. |
| Gemini | Single JSON | ordered messages and metadata | Whole-file immutable snapshot; map unknown fields by source reference. |
| Copilot / vscode-copilot | JSONL/log traces | turn start/end, assistant message, tool execution start/complete | Pair lifecycle events by native IDs; tolerate missing completes as partial. |
| ChatGPT | AgentsView rows currently lack native path | text may exist without native reconstruction | Compatibility observation only until a native artifact is discovered; fidelity remains partial/unavailable. |
| Cursor | machine-local project/database artifacts | session/thread identity varies by version | Versioned locator/probe; fail closed when only attribution data exists. |
</format_matrix>

<architecture_patterns>
## Architecture Patterns

### System Architecture

```text
Native agent stores (read-only)
        |
        v
Family discovery + schema/capability probe
        | unsupported/unsafe -> blocked adapter report
        v
Allowlisted immutable artifact snapshot
        |
        v
Family adapter -> typed events + relations + fidelity + native refs
        |
        v
Canonical v2 staging generation in existing conversation DB
        | validate identity / provenance / coverage / privacy / FK
        v
Compatibility projection builder -> old canonical tables
        |
        v
Atomic generation + projection activation -> version/watermark/delta
        | failure -> exact prior-generation rollback
        v
Versioned derived views -> ExtractionPolicy queue
        |
        v
Deterministic gate -> semantic replay/provider gate -> Candidate staging
        |
        +-- no paid provider or KU promotion in Phase 62
```

### Recommended Project Structure

```text
src/personal_knowledge/
├── core/
│   └── conversation_events.py          # typed event/relation/fidelity contract
├── adapters/conversation_sources/
│   ├── contracts.py                    # adapter capability/result seam
│   ├── snapshots.py                    # allowlisted immutable capture
│   ├── registry.py                     # 17-family routing
│   ├── jsonl_*.py                      # stream/DAG families
│   └── store_*.py                      # SQLite/directory/JSON families
├── application/conversation/
│   ├── event_schema.py                 # v2 tables/indexes/migration
│   ├── event_repository.py             # generation-bound reads/writes
│   ├── compatibility_projection.py     # old canonical table projection
│   ├── event_generations.py            # staging/validate/activate/rollback
│   └── extraction_views.py             # deterministic derived views
└── evaluation/conversation/
    ├── adapter_fidelity.py             # per-family coverage/quality report
    └── semantic_admission.py            # deterministic + LLM/replay decision seam
```

### Pattern 1: Raw authority plus semantic projection

Capture immutable raw evidence first. Store stable locators and hashes on every semantic event. When a new field is not modeled, preserve it by a bounded source reference and mark mapping fidelity instead of expanding a universal table or dropping it.

### Pattern 2: Generation-bound canonical evolution

Write a complete staging generation and its compatibility projection, validate both against one snapshot manifest, then change the active generation/version atomically. Never update active events row-by-row while consumers are reading.

### Pattern 3: Guarded evidence selection

Borrow AgentsView recall's strong idea, but bind to stable event IDs rather than ordinal-only windows: the view digest, policy version, active event generation, evidence-event set, and candidate commit guard must still match inside the same transaction. Drift produces stale/rebuild/revoke state, not silent rebinding.

### Pattern 4: Replaceable extraction policy

Adapters emit evidence semantics only. View builders emit reproducible windows/graphs. `ExtractionPolicy` ranks view types, freshness, fidelity, novelty, and cost. Changing priority creates a new policy digest and queue, without changing raw/event identities.

### Anti-Patterns to Avoid

- Treating role/message rows as the universal format.
- Using event ordinal as the only stable evidence identity.
- Storing vendor credential/account tables because they share a SQLite file.
- Putting snapshot capture, 17 parsers, event persistence, view policy, and activation in one module.
- Allowing summaries to cite themselves or LLM output to choose evidence outside its authorized event set.
- Reusing the old message-level prepare queues after the evidence unit and policy contract changes.
</architecture_patterns>

<upstream_lessons>
## AgentsView Lessons to Borrow Selectively

### Borrow

- Explicit parser capability discovery and per-source fidelity rather than pretending all formats expose the same fields.
- Artifact manifests with source/native identity, transcript revision, hashes, and bounded transport/capture behavior.
- Quiet-period/backstop scheduling and resumable progress state for future extraction orchestration.
- Evidence-window authorization/content digests and atomic commit guards against transcript drift.
- Provenance reconciliation/revocation when source evidence changes or disappears; do not delete historical audit records.
- Deterministic IDs and idempotent insert behavior for model-derived entries.

### Do not reuse as authority

- Flattened `messages` as the only evidence substrate.
- Ordinal ranges as permanent evidence identifiers when native event IDs exist.
- A single session transcript window as the fixed extraction unit.
- Upstream recall entries or summaries as project knowledge truth.
- Upstream database writes, credential configuration, or provider scheduling.

The current upstream README states that AgentsView discovers many agent stores read-only into local SQLite and that Grok can degrade to summary-only mode when its full transcript is absent. That supports using it as discovery/fidelity reference, not as proof that every local row is a full native transcript: [AgentsView repository](https://github.com/kenn-io/agentsview).
</upstream_lessons>

<common_pitfalls>
## Common Pitfalls

### Pitfall 1: False “lossless” claims
**What goes wrong:** every source becomes text plus role, while dropped structure is invisible.
**Avoidance:** raw snapshot authority, field disposition metadata, explicit fidelity dimensions, and round-trip source-ref tests.

### Pitfall 2: WAL-inconsistent or over-broad SQLite capture
**What goes wrong:** copied databases are transactionally inconsistent or include credentials.
**Avoidance:** online backup, declared table/column capability, immutable manifest, and fingerprint-negative tests for forbidden tables.

### Pitfall 3: Compatibility projection becomes the new authority again
**What goes wrong:** new consumers continue reading message rows and reconstructing relationships heuristically.
**Avoidance:** mark projection lineage/generation and provide a separate event-aware repository; only legacy consumers use compatibility views.

### Pitfall 4: Policy leaks into adapters
**What goes wrong:** changing trace/summary priority forces re-ingestion and changes evidence IDs.
**Avoidance:** adapter contracts contain only source semantics; policy/view versions are separate artifacts.

### Pitfall 5: LLM gate becomes a privacy or authority bypass
**What goes wrong:** all text is sent to a provider, or the model admits unsupported claims.
**Avoidance:** deterministic first gate, bounded view payload, evidence allowlist, structured abstention, replay provider tests, and explicit paid checkpoint.

### Pitfall 6: Big-bang canonical replacement
**What goes wrong:** existing KU/retrieval consumers break or old data is irreversibly overwritten.
**Avoidance:** v2 shadow generations, deterministic compatibility projections, consumer contract parity, backup/rollback, and human approval before live activation.
</common_pitfalls>

<open_questions>
## Open Questions

1. **Can native ChatGPT artifacts be recovered locally for the 104 current sessions?**
   - Known: the current AgentsView rows expose no native file path.
   - Plan: implement honest partial compatibility ingestion and a discovery probe; do not block the other 16 families or claim native reconstruction.

2. **Which Cursor store version produced the one current session?**
   - Known: Cursor storage and attribution databases vary by release.
   - Plan: capture a version/schema probe and fail closed unless the session/thread artifact can be distinguished from attribution-only data.

3. **What semantic model/provider will be used for the first real gate pilot?**
   - Known: no paid call is authorized and model quality/cost must be measured on reviewed examples.
   - Plan: implement provider-neutral structured output plus deterministic replay now; stop at a costed human checkpoint for a later pilot.
</open_questions>

<sources>
## Sources

### Primary (HIGH confidence)

- Local live metadata and native artifacts referenced from `C:\Users\li\.agentsview` — observed 17-family inventory and actual format differences; inspected read-only with no message bodies copied into planning artifacts.
- Project canonical, adapter, eligibility, publication, repository, rollback, and test code listed in `62-CONTEXT.md` — current implementation seams and constraints.
- [AgentsView official GitHub repository](https://github.com/kenn-io/agentsview) — supported agent discovery, read-only/local aggregation behavior, source-specific fidelity notes, and upstream implementation reference.
- Local read-only checkout of the same upstream repository — parser capability, artifact manifest, recall scheduling, evidence-window digest, guarded commit, and provenance reconciliation code.

### Secondary (MEDIUM confidence)

- None; vendor format assumptions not confirmed by official specifications remain encoded as versioned probes and fixture observations.
</sources>

<metadata>
## Metadata

**Research scope:** 17 local agent families, immutable capture, typed event modeling, canonical migration, extraction views, semantic admission, compatibility and rollback.

**Confidence breakdown:**
- Local architecture: HIGH — verified against current code and tests.
- Live family inventory: HIGH at 2026-08-12 capture time — read from live AgentsView metadata only.
- Native format contracts: MEDIUM/HIGH — observed local artifacts; vendor versions may drift and must be probed.
- Upstream lessons: HIGH for inspected upstream commit behavior; not accepted as project authority.

**Research date:** 2026-08-12
**Valid until:** 2026-09-11 for architecture; re-probe live schemas at execution time.
</metadata>

---

*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Research completed: 2026-08-12*
*Ready for planning: yes*
