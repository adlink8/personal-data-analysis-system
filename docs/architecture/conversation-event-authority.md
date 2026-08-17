<!-- generated-by: gsd-doc-writer -->
# Conversation Event Authority

## Overview

The conversation subsystem preserves heterogeneous native records as immutable
evidence, normalizes them into one loss-aware typed event model, and derives
consumer-specific projections and extraction views without making those derived
forms a second fact authority. The active event generation in
`data/canonical/agent/structured/db/agent_conversations.sqlite` is the
conversation authority. Legacy canonical tables remain a deterministic,
documented-loss projection for existing consumers, while extraction views and
candidate ledgers remain rebuildable products of the active generation.

The current chain is:

```text
native files / read-only AgentsView observations
                    |
                    v
content-addressed immutable artifacts
                    |
                    v
family adapter -> TypedEvent + EventRelation + explicit fidelity
                    |
                    v
staged generation -> validation -> active generation
                    |                    |
                    |                    +-> compatibility projection
                    |                         -> legacy consumers
                    v
seven replaceable views -> versioned priority policy
                    |
                    v
deterministic admission -> semantic admit/reject/abstain
                    |
                    v
candidate estimates (paid extraction remains blocked)

active artifact versions -> validated serving snapshot -> serving activation
                                                       -> snapshot rollback
```

Conversation-generation activation and serving-snapshot activation are distinct
authority transitions. The first selects conversation facts and atomically binds
their compatibility projection. The second selects a coherent set of published
artifacts for retrieval and other serving roles.

## Module and component listing

| Component | Location | Responsibility |
|---|---|---|
| Native inventory and live shadow | `application/conversation/native_inventory.py`, `live_native_shadow.py` | Inventories source locators, captures available files, creates filtered observations for unavailable ChatGPT/Grok locators, and stages one multi-family cohort. |
| Immutable capture | `adapters/conversation_sources/snapshots.py` | Produces content-addressed file or SQLite artifacts under byte, file-count, table, and column policies. |
| Adapter registry | `adapters/conversation_sources/registry.py` | Resolves registered names to explicit owner-family adapters and capability descriptors; `vscode-copilot` is an alias of `copilot`. |
| Event contracts | `core/conversation_events.py` | Defines typed events, relations, provenance, fidelity dimensions, field dispositions, stable event identity, and semantic dataset digests. |
| Event repository | `application/conversation/event_repository.py` | Persists staged generations, adapter runs, artifacts, sessions, events, relations, and the active authority pointer. |
| Generation lifecycle | `application/conversation/event_generations.py` | Validates, activates, rolls back, or deactivates a conversation generation with fail-closed transaction handling. |
| Active visibility | `core/canonical_visibility.py` | Restricts compatibility consumers to `v2|` rows whenever an active event authority exists; databases without the authority schema retain historical behavior. |
| Compatibility projection | `application/conversation/compatibility_projection.py` | Projects message and tool events into legacy canonical tables and records excluded event kinds plus a deterministic projection fingerprint. |
| Replaceable views | `application/conversation/extraction_views.py` | Deterministically rebuilds turn, native-trace, episode, compaction-window, session, topic, and cross-session views. |
| Priority policy | `application/conversation/extraction_policy.py` | Ranks view types, applies evidence/fidelity/budget/dedup rules, and emits candidates or explicit block/abstain reasons. |
| Admission gate | `evaluation/conversation/semantic_admission.py` | Runs non-overridable deterministic checks before an injected, abstention-capable semantic judge. |
| Candidate ledger | `application/knowledge/view_candidate_prepare.py` | Binds estimates to generation/view/policy/prompt/schema/evidence versions and prevents legacy or unapproved runs from executing. |
| Serving snapshots | `application/serving/snapshots.py` | Validates coherent artifact manifests, activates a serving snapshot, records history, projects the legacy pointer, and reactivates an older snapshot for rollback. |

## Immutable capture and provenance

`build_live_native_shadow` starts from the read-only AgentsView inventory. Each
unique available native locator is captured before adaptation. Normal files use
`capture_file`; SQLite sources use `capture_sqlite` with adapter-declared table
and column allowlists. Artifacts carry a content hash, schema digest, capture
method, relative locator, byte size, and privacy dispositions. Capture scratch
space is rooted under the repository's `var/tmp` tree.

Every `TypedEvent` and `AdaptedSession` must resolve to both an immutable
`artifact_id` and a `native_locator`. Construction fails closed when provenance
is missing. Stable event identity is scoped by family, contract version,
artifact, and native identity; when native streams reuse an ID, the immutable
record locator is included as an additional collision domain. Ordinals are for
ordering, not identity.

Field handling is explicit. A native field is marked `mapped`,
`preserved_by_reference`, `redacted`, `unavailable`, or `unsupported`. This keeps
unknown structure visible without pretending that all families expose the same
shape.

## Exact content, summaries, and family fidelity

`TypedEvent.content` is the exact mapped message text when the source exposes
it. `TypedEvent.summary` is a separate bounded synopsis used for navigation,
tool/reasoning descriptions, and semantic-gate payloads. A missing `content`
value may fall back to `summary` only in the legacy compatibility projection for
older event rows. An explicit empty string is retained as an exact source fact
and is never replaced with generated prose.

Fidelity is recorded independently for source availability, structure,
ordering, relations, content, compaction visibility, and native-ID stability.
The aggregate takes the worst observed value per dimension. `partial`,
`unknown`, or `unavailable` therefore cannot disappear behind a family-level
`complete` label. The active cohort reports all 17 registered names as
`partial`; this is coverage of observed inputs, not a claim of identical or
lossless native fidelity.

### ChatGPT and stale-locator Grok observations

When ChatGPT or Grok has an AgentsView session but no usable native file,
capture creates a family- and session-filtered SQLite observation. Only these
tables and columns are retained:

| Table | Allowed columns |
|---|---|
| `sessions` | `id`, `agent`, `started_at`, `ended_at`, `deleted_at`, `file_path` |
| `messages` | `id`, `session_id`, `ordinal`, `role`, `content`, `timestamp`, `is_system`, `is_sidechain` |

Auth/token tables, account columns, thinking/token-usage columns, undeclared
columns, and other-family rows are excluded. The observation is immutable and
adaptable, but it remains a compatibility observation rather than native-file
evidence.

The active ChatGPT projection is based on 104 such sessions and 3,929 messages.
Grok combines 83 available native snapshots with 75 stale-locator observations,
so all 158 observed sessions remain visible while unavailable native provenance
is disclosed rather than silently dropping those sessions.

### Claude and Qoder block decomposition

Claude and Qoder JSONL envelopes may contain multiple native content blocks.
The adapter emits each block separately:

- `text` becomes an exact message event with `content`.
- `thinking` or `reasoning` becomes a `reasoning` event with bounded summary.
- `tool_use` becomes a `tool_call`; `tool_result` becomes a `tool_result`.
- Matching native call IDs produce first-class call/result relations.
- Unsupported or empty non-text blocks become `unknown_native` records with
  partial fidelity and a preserved native locator.

Block-indexed locators and event identities prevent one multi-block envelope
from collapsing into an empty or ambiguous message row. Parent UUID, sidechain,
call/result, and Qoder compaction relationships remain separate relations.

## Generation validation, activation, and visibility

`GenerationLifecycle.validate` checks that the staged generation exists and
passes repository integrity and foreign-key checks. It then verifies the source
manifest and semantic dataset digest, expected adapter-family coverage, event
provenance, and session fidelity JSON. A stale manifest, digest mismatch,
unknown or missing family, unresolved provenance, or invalid fidelity blocks
activation.

Activation builds the compatibility projection before opening the commit
transaction. One transaction then:

1. Demotes the previous event authority and selects exactly one active
   generation.
2. Clears only prior `v2|` compatibility rows and writes the new projection.
3. Binds projection version, watermark, and fingerprint to the same generation.

Any commit error rolls back the transaction and leaves the prior authority
state intact. `rollback_to` rebuilds and activates an earlier staged generation
through the same commit path. `deactivate` removes the active v2 pointer,
bindings, and v2 projection while preserving staged generations and all
pre-existing legacy rows.

`canonical_projection_predicate` is the consumer-side visibility rule: with an
active v2 generation, compatibility readers select only IDs beginning `v2|`.
Legacy rows coexist physically for recovery but are not mixed into active reads.

## Compatibility projection and legacy coexistence

Only user, assistant, developer, and system message events become
`canonical_messages`; only tool call/result events become
`canonical_tool_events`. Reasoning, usage, compaction summaries, boundaries,
file context, lifecycle, and unknown-native events are listed as excluded and
are not flattened into user facts. Every source event maps to at most one legacy
row.

Projection IDs include the generation lineage and a deterministic fingerprint
covers the exact session, message, and tool rows. The active projection contains
1,678 sessions, 83,080 messages, and 211,458 tool rows. The database also retains
1,159 pre-v2 sessions and 95,428 pre-v2 messages unchanged for rollback and
historical compatibility.

## Replaceable extraction views and priority policy

Views are derived from the active event graph and carry the generation ID,
builder version, member event IDs, evidence references, fidelity, and a stable
digest. They can be rebuilt or replaced without changing artifact, event, or
relation identity. The seven view types are:

| View | Purpose |
|---|---|
| `turn` | Local conversational turn grouping. |
| `native_trace` | Source-native execution or relation trace. |
| `episode` | Bounded multi-event episode. |
| `compaction_window` | Context around compaction signals, never standalone truth. |
| `session` | Session-level navigation view. |
| `topic` | Evidence-linked topical grouping. |
| `cross_session` | Evidence-linked relationship across sessions. |

The initial policy ranks compaction windows first; turn, native trace, and
episode second; session third; topic fourth; and cross-session fifth. Ranking
lives only in `ExtractionPolicy`. Changing it changes the policy digest and
queue rank, not source or event identity. Missing evidence and fidelity below
`partial` block a view before priority can matter.

The verified full Codex build produced 77,396 turn views, 8,367 native traces,
667,131 episodes, 1,576 compaction windows, 662 session views, 4,619 topic views,
and one cross-session view. These counts overlap by design because views are
alternative evidence windows, not disjoint facts.

Candidate run identity binds the active generation, view-builder version,
policy digest, semantic prompt and schema versions, and exact evidence-event
digest. Old `ir_*` message-level runs are retained in the audit ledger but are
classified `superseded_policy` and non-executable. New `vc_*` runs store only
aggregate estimates and evidence handles and remain
`blocked_pending_user_cost_approval`; no conversation bodies are written to the
candidate ledger.

## Deterministic and semantic admission boundaries

Admission is deterministic-first. The following checks can reject a view
without invoking any judge and cannot be overridden by a later semantic result:

- generation and event handles are outside the allowlist;
- evidence is absent or lineage does not resolve;
- view members and evidence do not agree;
- structural fidelity is `unknown` or `unavailable`;
- content is unavailable or explicitly redacted;
- bounded summaries contain configured secret or prompt-injection markers.

Only a surviving view reaches the semantic judge. The judge receives bounded,
redacted view metadata and `summary` snippets plus authorized event handles; it
does not receive raw `content` or unrestricted native payloads. Its result is
`admit`, `reject`, or first-class `abstain`, with structured reason codes,
claims, assessments, limitations, and evidence handles. Referencing evidence
outside the allowlist or returning a malformed result fails closed.

The current candidate inspection path injects `ReplayJudge`, records zero paid
calls, and defaults unmatched cases to abstention. The admission contract is
implemented and tested, but a paid production semantic extraction path is not
enabled by this chain.

## Serving activation and rollback

The serving authority is stored separately in `var/db/personal_system.sqlite`.
A serving snapshot names immutable artifact versions by role, including
canonical conversation, canonical message, turn retrieval, knowledge retrieval,
and evaluation. Validation checks manifest membership, artifact version and
checksum parity, required roles, evaluation gates when required, collection
existence/counts, watermark regression, and optional evidence integrity.

Only a `validated` snapshot can become active. Activation updates the SQLite
serving authority transactionally and then projects the knowledge collection to
`var/db/knowledge_index_active.txt` through an atomic temporary-file replace.
SQLite remains authoritative if pointer projection fails; the failure is
recorded as projection drift and can be repaired from the active snapshot.

`rollback_snapshot` reactivates an earlier validated immutable snapshot and
records a rollback event without deleting snapshot history. When conversation
activation is followed by cross-store publication, publication failure triggers
a compensating conversation rollback to the prior generation (or deactivation
when none existed).

## Current live evidence and data quality

The following metadata-only checks were rerun against the live repository on
2026-08-15. Counts are snapshots and may change after a new capture or
activation.

| Check | Current result |
|---|---|
| Active conversation generation | `live-cohort-39a8813cb95d1d77` |
| Owner adapter runs / registered names | 16 / 17; `vscode-copilot` aliases `copilot` |
| Sessions / typed events / relations | 1,678 / 988,690 / 240,039 |
| Immutable source artifacts | 1,224 |
| SQLite integrity | `quick_check=ok`; foreign-key violations `0` |
| Active v2 compatibility projection | 1,678 sessions; 83,080 messages; 211,458 tool rows |
| Retained pre-v2 compatibility data | 1,159 sessions; 95,428 messages |
| Exact null-or-empty projected messages | 3,655 |
| Empty after Python whitespace stripping | 4,476, including 821 whitespace-only source values |
| Active serving snapshot | `ss_a0cfb34277a809e3d85a8196`; pointer parity clean |
| Active knowledge collection | `knowledge_units_empty_kg_20260812T025401Z_live`; 0 units |
| Turn retrieval | `conversation_turns`; 3,601 vectors |
| Focused authority regression | 99 tests passed across filtered capture, exact content, generation activation/rollback, admission, and serving activation/rollback |

The empty and whitespace-only messages above are retained source facts. They are
quality signals for downstream policy, not rows to silently delete or fill.
Likewise, all family fidelity remains `partial`; adapter coverage means the
source was handled and its limitations recorded, not that every native detail
was recovered.

## Explicit limitations

- The active conversation authority is structurally healthy, but the active
  knowledge generation is intentionally empty. `pk-sync status --json` reports
  drift for `s.knowledge_unit`, and the current coverage matrix reports 43,523
  eligible legacy-projection messages with zero knowledge coverage. Conversation
  authority completion is therefore not knowledge freshness completion.
- No paid semantic extraction was run. Candidate preparation estimates calls,
  tokens, and cost, but executable extraction remains blocked; replay admission
  does not prove production-model quality.
- Compatibility projection is intentionally lossy. Reasoning, usage,
  compaction, boundaries, context, and unknown-native structure remain available
  only through event-aware consumers and derived views.
- ChatGPT and stale-locator Grok observations are privacy-filtered AgentsView
  compatibility evidence, not equivalent to available native artifacts.
- All registered families currently report partial fidelity. Unsupported
  fields, missing native files, and uncertain relationships remain explicit.
- The latest `pk-ku doctor --json` run passed all 10 critical checks, but its
  REST `:8000` and MCP `:8789` health probes saw HTTP 502 while both ports were
  listening. This is a current delivery-health warning, not evidence that the
  SQLite conversation or serving authorities are corrupt.
