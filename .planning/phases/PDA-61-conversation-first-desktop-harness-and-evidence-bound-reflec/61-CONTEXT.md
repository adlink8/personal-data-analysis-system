# Phase 61: Conversation-first Desktop Harness and Evidence-bound Reflection Loop - Context

**Gathered:** 2026-08-09
**Status:** Ready for planning
**Source:** Consolidated from the Harness architecture, desktop UX, Agent/Skill/Tool, and reflection-loop discussion

<domain>
## Phase Boundary

Deliver a local desktop Walking Skeleton that opens directly into a Codex-style conversation, routes one user request through the real Pi Agent tool loop and the existing governed Skill/Tool registries, exposes bounded read-only SQLite evidence access, and completes one evidence-bound second-loop path from a deterministic conversation event to a reviewable Candidate and a derived personal-model projection.

This phase proves the new product shape without replacing the existing authorities, broadening production activation, deleting the current Cockpit, or attempting the complete long-term personal intelligence roadmap.

</domain>

<decisions>
## Implementation Decisions

### Product identity

- **D-01:** The product is a personal intelligence Harness, not Hermes and not another coding executor. Its distinctive value is cross-Agent conversation accumulation, evidence-bound reflection, and personal understanding that improves future conversations.
- **D-02:** Pi supplies the generic model/tool execution loop. Project differentiation belongs in context selection, Skill routing, capability governance, evidence, Candidate review, personal-model projection, outcome calibration, and proactive presentation.
- **D-03:** Phase 61 is a vertical Walking Skeleton. It proves one complete conversational and reflection path; it does not claim the full multi-stage second loop is finished.

### Desktop experience

- **D-04:** Use an Electron desktop shell with Web UI technology. The rejected form is a browser-maintained product surface, not Web technology itself.
- **D-05:** Opening the application lands directly in the last conversation. Interaction and visual density should feel close to the current Codex desktop app so switching between Codex, ZCode, and this Harness has low cognitive cost.
- **D-06:** Use the current Codex dark/light color direction and a minimal layout: new conversation, recent conversations, project scopes, and bottom personal/system entry points. Existing browser Cockpit pages are not the visual reference.
- **D-07:** Conversation is the primary interface. Deep capabilities appear on demand as inline cards, drawers, command-palette actions, or confirmation modals rather than permanent top-level pages.
- **D-08:** Tool execution details are collapsed by default. The answer exposes evidence, freshness, limitations, and an expandable receipt instead of raw internal traces.

### Agent, Skill, and Tool composition

- **D-09:** Run one Pi Agent Runtime with three policy profiles: Conversation, Reflection, and Operator. Do not create one autonomous Agent per feature or let Agents recursively converse by default.
- **D-10:** A turn selects zero or one primary Skill, with at most one bounded supporting Skill. Skills do not recursively invoke arbitrary Skills; they exchange typed results and receipts through the runtime.
- **D-11:** Preserve the existing 11 project Skills and 44 governed operations as the capability foundation. A selected Skill receives only its declared tool allowlist, budget, privacy ceiling, and recovery contract.
- **D-12:** The Capability Broker enforces operation profile, scope, arguments, side-effect class, confirmation, idempotency, timeout, and receipt rules before an Adapter executes a Tool.
- **D-13:** The Pi AgentSession must actually carry the iterative model -> tool proposal -> governed execution -> receipt -> continued reasoning loop. A second custom outer Agent loop must not duplicate this responsibility.

### Conversation evidence and SQLite

- **D-14:** AgentView remains the supported aggregation source for Codex, ZCode, and other Agent sessions. The project consumes its unified schema rather than building new source-specific parsers in Phase 61.
- **D-15:** The system must display source freshness honestly. Source -> AgentView and AgentView -> canonical backlog cannot be represented as current or complete.
- **D-16:** AI may query approved underlying SQLite data only through a dedicated read-only Tool in the normal Skill lease -> Capability Broker -> Domain Tool path. SQLite is a Tool resource, not a parallel AI/Desktop data lane. The experience is direct because no separate business REST read model is required for the evidence query, but the model supplies only an approved versioned query descriptor and typed parameters, never SQL or a database path. The Python adapter owns the prepared SELECT/read-only CTE, approved database/view/column scope and row/time/byte bounds; ATTACH, extension loading, write PRAGMA and mutation remain unreachable.
- **D-17:** Every SQLite result carries database/source identity, freshness/version binding, query checksum, truncation state, and a Tool receipt suitable for evidence drilldown. The renderer only displays that validated receipt. Fixed desktop chrome such as recent-thread metadata, service health and freshness badges may use named read-model projections, but those projections cannot accept model-generated SQL, expose a database handle or substitute for `evidence.sqlite_query`.

The two read paths are deliberately distinct:

```text
AI turn -> Pi Agent loop -> Skill lease -> Capability Broker
        -> evidence.sqlite_query Tool -> Python read-only adapter -> approved SQLite

Desktop fixed view -> named DesktopBridge method -> fixed read-model provider
                   -> metadata-only projection (no arbitrary query surface)
```

### Evidence-bound second loop

- **D-18:** The second loop begins only from deterministic events such as a completed AgentView/canonical sync, conversation close, decision/outcome change, or schedule. The model does not wake itself arbitrarily.
- **D-19:** Persist separate layers: immutable Evidence, reproducible Observation, reviewable Candidate, governed Canonical knowledge, derived Projection, append-only Outcome, and Calibration. Generated prose and Agent consensus are not facts.
- **D-20:** The Walking Skeleton implements one path: a new conversation delta becomes an evidence-linked reflection Candidate; the user can accept, edit, or ignore it; accepted content contributes to a versioned personal-model projection.
- **D-21:** Personal understanding is a time-aware projection, not a fixed profile document. Each inference must preserve scope, valid time, confidence, supporting evidence, contradicting evidence, and supersession.
- **D-22:** Candidate promotion never inherits permission from Agent agreement. Canonical, promotion, rollback, and other high-risk operations retain explicit governance and confirmation.

### Proactive behavior and feedback

- **D-23:** Phase 61 may surface only deterministic-trigger cards. Proactive items are independent events projected into the conversation without rewriting manual message ordering.
- **D-24:** Proactive presentation uses tiered surfaces: quiet badge, inline card, drawer, and modal only when confirmation is required. It supports granular controls, quiet hours, evidence-cluster deduplication, and dismissal feedback.
- **D-25:** The initial loop records acceptance, edits, ignores, and dismissals for later calibration, but Phase 61 does not autonomously learn broader permissions or silently change personal values.

### Safety and operations

- **D-26:** Existing Python authority remains exclusive for facts, transactions, evidence, watermarks, evaluation, promotion, active pointers, rollback, and formal lifecycle changes.
- **D-27:** The desktop shell may supervise local processes and consume loopback services, but replacing browser UI does not require eliminating internal loopback IPC or ports.
- **D-28:** Existing Task, Session, Event, Candidate, cancel, resume, outcome-unknown, reconcile, SSE, and receipt capabilities should be reused instead of creating parallel state stores.
- **D-29:** No personal body, credential, unrestricted SQL, arbitrary filesystem/process/network capability, or authority mutation may leak through UI logs, telemetry, or model-visible receipts.

### the agent's Discretion

- Exact Electron packaging and preload implementation, provided renderer isolation and least-privilege IPC are enforced.
- Exact names and schema details for the new read-only SQLite Tool and personal-model projection, provided the locked evidence and governance decisions above remain true.
- Internal module layout and test doubles at seams.
- The exact existing read-only Skill used for the first conversational vertical slice.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Capability and Skill authority

- `governance/manifests/ai/pi-skills.json` — Existing 11 governed project Skills and their allowed tools.
- `governance/manifests/capabilities/project-capabilities.json` — Existing 44 active operations, authority classes, side-effect classes, profiles, confirmation, and receipt contracts.
- `apps/personal_intelligence_kernel/src/kernel-host.mjs` — Current Kernel task execution and the known gap between Pi session registration and the actual iterative agent loop. This file already has user changes; preserve and reconcile them.
- `apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs` — Contained Pi AgentSession construction and Tool registration policy.
- `apps/personal_intelligence_kernel/src/server.mjs` — Current local Kernel task/event/control interface.
- `apps/personal_intelligence_kernel/src/tools/domain-bridge.mjs` — Kernel-to-Python Domain Tool Adapter.

### Conversation and evidence authority

- `src/personal_knowledge/adapters/agentsview.py` — Read-only AgentView adapter and schema/privacy gates.
- `src/personal_knowledge/application/run_pipeline.py` — Current AgentView inventory -> normalized -> canonical pipeline.
- `src/personal_knowledge/core/conversation_repository.py` — Conversation SSOT repository interface and implementation.
- `src/personal_knowledge/application/conversation/summary.py` — Existing Pi-backed conversation summary path.
- `src/personal_knowledge/intelligence/analysis/` — Evidence-bound analysis and Candidate patterns.
- `src/personal_knowledge/intelligence/calibration/` — Existing conservative calibration patterns.
- `src/personal_knowledge/intelligence/proactive/service.py` — Existing proactive Candidate, uncertainty, reason, and digest behavior.

### Existing UX exploration

- `.planning/sketches/MANIFEST.md` — Sketch inventory and selected variants. Use only Codex-style conversation-first findings; browser Cockpit pages are not a visual reference.
- `.planning/sketches/001-conversation-shell/` — Selected dual-pane conversation shell direction.
- `.planning/sketches/002-sqlite-query/` — Selected inline read-only SQLite result-card direction.
- `.planning/sketches/003-personal-model/` — Selected time-evolving personal model direction.
- `.planning/sketches/004-daily-brief/` — Selected conversational daily brief direction.
- `.planning/sketches/005-review-inbox/` — Selected source-batch Candidate review direction.
- `.planning/sketches/006-explore-research/` — Selected unified evidence search direction.

</canonical_refs>

<specifics>
## Specific Ideas

- First real user path: open desktop -> last conversation -> ask a historical/project question -> router selects an existing read-only Skill -> Pi invokes governed Tools -> answer includes evidence and expandable receipts.
- First second-loop path: canonical conversation delta event -> evidence extraction -> reflection Candidate -> inline review card -> accept/edit/ignore -> versioned projection update -> next conversation can retrieve the accepted projection with its evidence.
- The desktop UI should make Skill and Tool use visible enough to trust but not require the user to understand the capability registry.
- Ordinary conversation uses a small read-only base capability set. Operator and maintenance Skills remain hidden from default chat and use explicit high-risk confirmations.

</specifics>

<deferred>
## Deferred Ideas

- Full replacement or deletion of the existing React Decision Cockpit.
- Full multi-dimensional personal-model ontology and automatic cross-domain promotion.
- Weekly/monthly deep synthesis, learned proactive timing, and mature outcome-based routing calibration.
- Broad autonomous maintenance, external actions, arbitrary Agent spawning, or permission self-expansion.
- Removal of internal loopback ports or consolidation of all current processes into one executable.
- Primary Pi activation while Phase 53/60 evidence and user authorization remain unresolved.
- Re-parsing every Codex/ZCode/vendor source directly instead of relying on AgentView.

</deferred>

<success_criteria>
## Success Criteria

- The packaged/local desktop shell opens directly into a functional conversation without requiring the user to open a browser.
- One real prompt completes through Pi's iterative governed Tool loop using an existing read-only Skill and returns evidence plus receipts.
- A bounded read-only SQLite Tool can answer an approved evidence query and rejects mutation, ATTACH, unsafe PRAGMA, unapproved scope, and excessive results without changing database fingerprints.
- One deterministic conversation-delta event produces a reviewable, deduplicated, evidence-linked Candidate.
- Accept/edit/ignore is recorded; an accepted Candidate updates a versioned derived personal-model projection without treating generated text as raw fact.
- The next conversation can use the projection while showing its confidence, time scope, evidence, conflict, and freshness.
- Existing authority, activation, privacy, and rollback invariants remain unchanged; the current user modification in `kernel-host.mjs` is preserved.

</success_criteria>

---

*Phase: 61-conversation-first-desktop-harness-and-evidence-bound-reflection-loop*
*Context gathered: 2026-08-09 via consolidated dialogue decisions*
