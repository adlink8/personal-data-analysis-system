# Phase 62: Multi-format conversation adapters, unified event authority, and replaceable extraction views - Context

**Gathered:** 2026-08-12
**Status:** Ready for planning

<domain>
## Phase Boundary

Deliver a project-owned, loss-aware conversation ingestion authority for every agent family currently present in the live AgentsView inventory. Each native source is captured through a privacy-allowlisted immutable evidence snapshot, adapted into a typed canonical event model, and projected through replaceable views for compaction, episode/trace, session, topic, and cross-session extraction.

Phase 62 evolves the existing canonical conversation authority in place: it reuses the canonical database, publication/version/watermark/rollback seams, adds v2 event-authority tables, and preserves the existing `canonical_sessions`, `canonical_messages`, and `canonical_tool_events` contracts as compatibility projections until consumers are migrated and parity gates pass. It does not delete raw or old canonical data, activate paid extraction, or treat AgentsView's flattened messages as the new evidence authority.

</domain>

<decisions>
## Implementation Decisions

### Source coverage and adapter ownership

- **D-01:** Phase 62 covers all 17 agent families observed in the live AgentsView inventory: Codex, ZCode, Workbuddy, Grok, ChatGPT, Kimi, Claude, vscode-copilot, MimoCode, Qoder, Copilot, Antigravity, Gemini, Kimi-work, OpenCode, Pi, and Cursor.
- **D-02:** The project owns a versioned adapter registry and one explicit capability contract per family. A family may share parser primitives with structurally similar formats, but must retain its own detection, schema/version gate, fidelity profile, fixtures, and contract results.
- **D-03:** AgentsView remains a read-only discovery, crosswalk, and compatibility input. Its flattened `sessions/messages/tool_calls` schema is not sufficient to reconstruct native typed events and is not the Phase 62 semantic evidence authority. This intentionally supersedes Phase 61 D-14 for the Phase 62 ingestion authority while preserving Phase 61's read-only and freshness constraints.
- **D-04:** Unsupported versions, ambiguous source location, missing native artifacts, or unrecognized event kinds fail closed into a structured adapter report. They must never be silently coerced into an apparently complete text transcript.

### Raw evidence and no-loss boundary

- **D-05:** Preserve each allowlisted native conversation artifact in a content-addressed, immutable project snapshot before adaptation. Mutable SQLite sources use SQLite online backup; active WAL databases must never be copied as loose `.db/.db-wal/.db-shm` files.
- **D-06:** “No loss” means the raw snapshot remains the byte-level evidence authority and every canonical event carries stable provenance back to its source artifact, native locator, and content hash. It does not mean every vendor field must become a first-class common column.
- **D-07:** Native fields that are safe but not yet modeled remain recoverable through an immutable `native_payload_ref` or equivalent source slice reference. The event records which fields were mapped, preserved by reference, redacted, unavailable, or unsupported.
- **D-08:** Snapshot capture is allowlist-based. SQLite adapters may read only declared conversation tables and columns. Adjacent account, credential, token, cookie, secret, or authentication tables are forbidden even if they share the same database.
- **D-09:** Snapshot manifests contain source identity, adapter/version, schema fingerprint, artifact hashes, capture method, byte/count metrics, privacy decisions, and completeness/fidelity results without logging conversation bodies or credentials.

### Unified canonical event authority

- **D-10:** The unified semantic layer is a typed event model, not a flattened message list. It must represent at least session lifecycle, user/assistant/developer/system messages, reasoning, tool call/result, usage, compaction/summary, turn or loop boundaries, subagent/branch relations, file/context events, and unknown native events.
- **D-11:** Stable identities derive from source family, native session/event identity when available, source artifact hash, and an adapter-contract version. Ordering and identity are separate: an event may have ordinal/time fields without using them as its permanent identity.
- **D-12:** Relations are first-class. Parent/child, call/result, branch, sidechain, subagent, compacted-range, retained-from, turn membership, and source-session crosswalks are not encoded only in prose or inferred later from adjacency.
- **D-13:** Each session and event exposes fidelity dimensions such as source availability, structure completeness, ordering confidence, relation completeness, content availability, compaction visibility, and native-ID stability. `unknown`, `partial`, and `unavailable` are valid states and cannot be reported as complete.
- **D-14:** ChatGPT sessions with no recoverable native path and any other source with insufficient artifacts remain represented with honest partial fidelity; AgentsView text may be used as a compatibility observation but cannot be labeled as native reconstruction.

### Reuse and evolution of canonical

- **D-15:** Reuse the existing canonical database path, publication registry, checksum/watermark, `pk-sync conversations`, rollback, and downstream repository seams. Do not introduce a permanently separate conversation product authority.
- **D-16:** Add v2 raw-artifact, adapter-run, canonical-event, event-relation, session-capability/fidelity, and view-lineage tables beside the current schema. Keep persistence, adaptation, view construction, policy, and activation in separate cohesive modules/state owners.
- **D-17:** Existing `canonical_sessions`, `canonical_messages`, and `canonical_tool_events` become deterministic compatibility projections of the active v2 event generation. Existing consumers continue through `ConversationRepository` while new consumers use an event-aware repository seam.
- **D-18:** Build v2 in shadow/staging generations, validate it against the same captured source snapshot, then activate the generation and its compatibility projection atomically. A failure after authority activation, including pointer/projection failure, triggers full rollback to the prior generation and pointer.
- **D-19:** The old canonical tables remain readable until all registered consumers pass provider/consumer contract tests. Removal or destructive rewrite is outside Phase 62.

### Replaceable views and extraction priority

- **D-20:** Trace is not the permanent center of the model. A trace means a source-native or policy-derived bounded execution episode: related events sharing an explicit native trace/turn/loop ID or a reproducible grouping rule. It is one replaceable view, not evidence authority.
- **D-21:** Required derived views are `TurnView`, `NativeTraceView`, `EpisodeView`, `CompactionWindowView`, `SessionView`, `TopicView`, and `CrossSessionView`. Views may be lossy, are versioned, carry lineage to event IDs, and are rebuildable without re-running adapters.
- **D-22:** Extraction ordering is owned by a versioned `ExtractionPolicy`, never hard-coded into adapters or event identity. Changing whether trace, session, topic, or another view is preferred must require only a new policy/view build, not source re-ingestion.
- **D-23:** Compaction summaries have highest initial scheduling priority because they are dense navigation signals, followed by event-bounded episodes/traces, whole-session synthesis, and cross-session synthesis. This is queue priority, not truth authority.
- **D-24:** Every candidate derived from a summary or view must retain both `derived_from_view` lineage and stable `evidence_event_refs`. Claims without underlying event support are rejected or marked unresolved; summary prose cannot become truth merely because it was generated upstream.

### Quality and semantic gate

- **D-25:** Adapter quality is measured against native fixtures and live metadata by coverage, event-kind preservation, relation preservation, stable replay, source-slice resolvability, privacy exclusions, and drift detection—not only row counts.
- **D-26:** Extraction uses two gates: deterministic structure/privacy/secret/injection/evidence checks first, then an LLM semantic gate that decides whether the evidence contains durable, useful information. The LLM may abstain and cannot override deterministic rejection.
- **D-27:** The semantic gate evaluates supported claims, novelty, durability, specificity, future usefulness, contradictions, and contamination. It does not absorb every eligible event and must preserve rejected/abstained reason codes without storing sensitive prompt bodies in logs.
- **D-28:** Adapter and view evaluation use a small, manually reviewed, redacted reference set for every family and every material event/relationship type. Cross-session extraction requires contradiction and provenance tests, not only relevance scores.

### Cost, isolation, and activation

- **D-29:** The quarantined legacy knowledge generations remain isolated and the active KU collection remains empty while Phase 62 is built and validated.
- **D-30:** The two existing message-level prepare runs—3,224 user items and 21,263 assistant items, 24,487 calls / 48,974,000 estimated tokens / USD 24.487 total—must not be extracted. Phase 62 may supersede or invalidate their queue semantics without deleting their audit history.
- **D-31:** No `pk-ku extract`, provider generation, paid semantic labeling, or full rebuild is authorized by this phase plan. Planning and deterministic/replay testing must remain zero-paid-call; any later representative LLM pilot requires a separate explicit user cost approval checkpoint.

### the agent's Discretion

- Exact v2 table and Python type names, provided the authority, provenance, fidelity, compatibility, and cohesion decisions above remain true.
- Parser primitive sharing between structurally similar families, provided family-specific contracts and drift gates remain explicit.
- The exact deterministic episode boundary heuristics and default weights after native boundaries and compaction ranges are preserved.
- The size and sampling strategy of redacted fixtures, provided every family and critical negative path is covered.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project authority and engineering contract

- `AGENTS.md` — Product workflow, dialogue/KU SSOT rules, read-only AgentsView constraint, and verification requirements.
- `docs/AGENTS.md` — Full operating manual, authority map, privacy rules, and product commands.
- `docs/architecture/engineering-and-testing-contract.md` — Public seam declaration, Red → Green, module cohesion, contract/integration coverage, and required negative tests.
- `.planning/PROJECT.md` — Product boundaries, Python authority, evidence, rollback, and activation decisions.
- `.planning/phases/PDA-61-conversation-first-desktop-harness-and-evidence-bound-reflec/61-CONTEXT.md` — Upstream conversation/evidence decisions; Phase 62 explicitly revises only D-14's unified-AgentsView ingestion assumption.

### Current conversation ingestion and compatibility seams

- `src/personal_knowledge/adapters/agentsview.py` — Existing read-only probe and SQLite online-backup pattern.
- `src/personal_knowledge/application/run_pipeline.py` — Current AgentsView inventory → normalized → canonical orchestration seam.
- `src/personal_knowledge/application/sync.py` — `pk-sync conversations`, version publication, watermark, and post-commit delta integration.
- `src/personal_knowledge/application/conversation/build_agentsview_normalized.py` — Current privacy allowlist, redaction, flattened normalization, and staging publication behavior.
- `src/personal_knowledge/application/conversation/build_canonical_agent_conversations.py` — Current canonical schema, crosswalk, compatibility tables, and atomic replacement behavior.
- `src/personal_knowledge/core/conversation_repository.py` — Existing legacy/canonical consumer contract to preserve through compatibility projections.
- `src/personal_knowledge/application/knowledge/eligibility.py` — Current message-level deterministic eligibility and compact-summary exclusion that Phase 62 replaces downstream, not in the raw event authority.
- `src/personal_knowledge/core/conversation_turn_units.py` — Current lossy turn-summary vector unit model and its stale artifact dependency.

### Validation and rollback patterns

- `tests/integration/test_agentsview_source_adapter.py` — Read-only source and snapshot adapter tests.
- `tests/integration/test_agentsview_normalization.py` — Privacy and normalization tests.
- `tests/contract/test_agentsview_downstream_contracts.py` — Current provider/consumer compatibility seam.
- `tests/integration/test_agent_conversation_rollback.py` — Canonical rollback behavior.
- `tests/integration/test_external_snapshot_lifecycle.py` — Immutable snapshot lifecycle pattern.
- `.planning/quick/260812-dug-canonical-canonical-llm/260812-dug-SUMMARY.md` — Completed old-KU quarantine and empty-generation activation evidence.
- `.planning/quick/260812-dug-canonical-canonical-llm/260812-dug-VERIFICATION.md` — Independent live-state verification and zero-paid-call evidence.

### Native source reference

- `C:\Users\li\.agentsview\sessions.db` — Live read-only discovery/crosswalk database; never write and always capture mutable SQLite through online backup.
- `C:\Users\li\.agentsview` source locators and referenced native artifacts — Actual family-specific format evidence; inspect read-only and redact fixture bodies.
- `https://github.com/kenn-io/agentsview` — Upstream parser and summary-chain reference only; useful for discovery and comparison, not copied as the project authority.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- `AgentViewAdapter.snapshot`: already demonstrates fail-closed probing and SQLite online backup for a live WAL source.
- Canonical staging and publication: current builders already write staging databases and replace published artifacts; Phase 62 should extract a generation/rollback transaction seam rather than add more state to the monolithic builders.
- `pk-sync conversations`: remains the user-facing command and publication/delta producer.
- Serving version registry and watermark helpers: reuse for v2 generation and compatibility-projection version binding.
- `ConversationRepository`: preserve as the legacy consumer seam while adding an event-aware provider beside it.

### Established Patterns

- Python deterministic core owns evidence, facts, watermarks, publication, active pointers, and rollback.
- Source adapters are read-only and fail closed on schema drift.
- Privacy filters log rule names/counts and hashes, never secret matches or conversation bodies.
- Public contract changes require provider, consumer, and real-adapter tests with deterministic fixtures.
- A module must split when it acquires another authority owner, state machine, or independent change reason.

### Integration Points

- `pk-sync conversations` orchestrates capture, adapter execution, v2 staging, compatibility projection, validation, and atomic activation.
- The active canonical generation publishes through the existing artifact/version registry and emits the existing metadata-only conversation delta only after commit.
- Existing KU inspect/prepare must read only the active compatibility projection until a later event/view-aware candidate seam is activated.
- New view and policy outputs feed candidate preparation only after lineage and semantic-gate contracts are implemented; they do not call a paid provider in Phase 62.

</code_context>

<specifics>
## Specific Ideas

- Treat upstream compaction summaries as high-value maps into evidence, not as automatically true personal facts.
- Preserve source-native boundaries when they exist: Codex `turn_id`, ZCode trace/turn IDs, Claude/Qoder DAG links, Pi compaction ranges, Grok compaction/checkpoint/recap artifacts, and explicit tool call/result identities.
- When the user later changes extraction priority away from trace, only `ExtractionPolicy` and derived views change; raw snapshots and canonical events remain stable.
- The final comparison report should answer, per family and session, what was available natively, what was captured, what became typed events, what remained by reference, what was redacted, and what is still partial.

</specifics>

<deferred>
## Deferred Ideas

- Paid full-corpus LLM extraction, production semantic labeling, or promotion of a new knowledge collection.
- Deleting old canonical tables, old source snapshots, quarantined KU generations, ledgers, or Chroma collections.
- Making one fixed view—trace, turn, session, or summary—the permanent extraction authority.
- Automatically trusting upstream or project-generated summaries as facts without event-level evidence verification.
- Migrating or writing any live agent database, including AgentsView.

</deferred>

---

*Phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views*
*Context gathered: 2026-08-12*
