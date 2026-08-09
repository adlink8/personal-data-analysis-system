# Phase 61: Conversation-first Desktop Harness and Evidence-bound Reflection Loop - Research

**Researched:** 2026-08-09
**Domain:** Electron local desktop shell, Pi AgentSession tool loop, governed evidence/reflection
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

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
- **D-16:** AI may query approved underlying SQLite data through a dedicated read-only Tool. The experience is direct, but implementation remains governed: SELECT/read-only CTE only, approved database/view/column scope, bounded rows/time/bytes, no ATTACH, extension loading, write PRAGMA, or mutation.
- **D-17:** Every SQLite result carries database/source identity, freshness/version binding, query checksum, truncation state, and a receipt suitable for evidence drilldown.

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

### Deferred Ideas (OUT OF SCOPE)

- Full replacement or deletion of the existing React Decision Cockpit.
- Full multi-dimensional personal-model ontology and automatic cross-domain promotion.
- Weekly/monthly deep synthesis, learned proactive timing, and mature outcome-based routing calibration.
- Broad autonomous maintenance, external actions, arbitrary Agent spawning, or permission self-expansion.
- Removal of internal loopback ports or consolidation of all current processes into one executable.
- Primary Pi activation while Phase 53/60 evidence and user authorization remain unresolved.
- Re-parsing every Codex/ZCode/vendor source directly instead of relying on AgentView.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|---|---|---|
| HARNESS-01 | Electron opens the last conversation with local navigation. | New isolated Electron shell; UI contract and least-privilege process design below. [CITED: 61-UI-SPEC.md] |
| HARNESS-02 | One governed Skill runs in the real iterative Pi loop. | Replace current one-shot/fixed-step host path with `AgentSession.prompt()` plus subscribed event projection. [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs] |
| HARNESS-03 | Bounded approved SQLite read Tool rejects unsafe access. | New Python-authority `evidence.sqlite_query` tool with grammar, scope, SQLite RO connection, hard bounds, and receipt. [CITED: src/personal_knowledge/adapters/agentsview.py] |
| HARNESS-04 | AgentView and two-hop freshness remain truthful. | Build a typed freshness projection from AgentView probe/snapshot plus canonical sync watermark/backlog. [CITED: src/personal_knowledge/adapters/agentsview.py] |
| HARNESS-05 | Delta deterministically creates deduplicated evidence-linked Candidate. | Consume a durable kernel event with a deterministic idempotency/dedup key, then stage through the existing Candidate/Event/receipt pattern. [CITED: apps/personal_intelligence_kernel/src/candidates/store.mjs] |
| HARNESS-06 | UI accepts, edits, or ignores through governance. | Reuse guarded Python write route/confirmation, append-only feedback, and receipt projection; do not give renderer or Pi authority. [CITED: src/personal_knowledge/services/http/handlers/orchestration.py] |
| HARNESS-07 | Accepted Candidate produces versioned derived personal projection. | Reuse `normalize_candidates()` / `project_current_state()` evidence, time, confidence, conflict, and lifecycle invariants. [CITED: src/personal_knowledge/intelligence/state_projection.py] |
| HARNESS-08 | Automated and desktop UAT prove safety and recovery. | Node/Python contract tests plus a manual Electron UAT script; negative tests/fingerprints are specified below. [CITED: pytest.ini] |
</phase_requirements>

## Project Constraints (from AGENTS.md)

- New Python imports use `application.*`, `evaluation.*`, or `core.llm`; do not create new `domains.*` imports. [CITED: docs/AGENTS.md]
- AgentView's live `%USERPROFILE%\.agentsview\sessions.db` is read-only and must never be moved or written. Knowledge SSOT remains KU plus active pointer; memory and `personal_events` are not replacements. [CITED: docs/AGENTS.md]
- Never commit `data/**`, `var/**`, SQLite files, private bodies, or secrets; run targeted pytest/import/health verification after code changes. [CITED: docs/AGENTS.md]
- Preserve the user's uncommitted `apps/personal_intelligence_kernel/src/kernel-host.mjs` change: provider mode no longer defaults to `replay`. [CITED: git diff -- apps/personal_intelligence_kernel/src/kernel-host.mjs]
- Keep primary Pi activation, KU promotion, active pointer changes, and rollback gates unchanged; Phase 60 remains `legacy`/not authorized for primary or canary. [CITED: .planning/STATE.md]

## Summary

Phase 61 should add a small independent Electron application and a narrow Conversation Runtime facade, not migrate or visually reuse the existing browser Cockpit. The renderer owns only conversation presentation and UI state; Electron main owns process supervision plus a fixed IPC allowlist; the already-loopback Kernel and Python authority retain execution, evidence, Candidate, confirmation, and receipt ownership. This satisfies the local desktop requirement while preserving the present multi-process topology. [CITED: 61-CONTEXT.md] [CITED: apps/personal_intelligence_kernel/src/server.mjs] [CITED: src/personal_knowledge/services/pi_domain_gateway.py]

The decisive code gap is real: `createContainedSession()` creates a Pi `AgentSession` with all ambient discovery disabled and only custom capability tools, but gives it a provider-free synthetic runtime. `KernelHost.executeSkillTask()` instead optionally calls `providerAdapter.generate()` once and then executes a predeclared `SkillEngine` sequence; it never calls `session.prompt()`. The desktop vertical slice must replace that execution branch with a per-turn lease-scoped real model runtime, subscribe to `AgentSession` events, call `session.prompt()`, await idle, and convert only final answer plus sanitized Tool receipts into the existing task/session/event records. [CITED: apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs] [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs] [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts]

**Primary recommendation:** Create `apps/personal_intelligence_desktop/` as a local-only Electron shell and add a narrowly typed `conversation.turn` Kernel route that drives the existing contained Pi `AgentSession`; add `evidence.sqlite_query` and reflection/projection adapters on the Python authority side, with explicit manifests and no direct database/authority access from Electron or Pi. [CITED: 61-CONTEXT.md]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Conversation layout, drawers, receipt/candidate cards, keyboard/a11y | Browser / Client | Electron preload | Renderer presents only sanitized view models and invokes named bridge methods. [CITED: 61-UI-SPEC.md] |
| Window lifecycle, local asset loading, process supervision, IPC sender validation | Electron main | Frontend server (loopback) | Native privileges must remain outside the renderer. [CITED: https://www.electronjs.org/docs/latest/tutorial/security] |
| Iterative model → governed Tool → receipt → final answer | Kernel runtime | API / Backend | Pi `AgentSession` owns the tool loop; Capability Broker/Domain Bridge owns enforcement. [CITED: apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs] |
| Capability descriptors, manifest lease, validation, receipts, confirmation | API / Backend | Kernel runtime | Python gateway checks fixed operation inputs and capability header; Kernel carries task bindings. [CITED: src/personal_knowledge/services/pi_domain_gateway.py] |
| Approved SQL parsing/execution, evidence identity, freshness, Candidate acceptance/projection | API / Backend | Database / Storage | Python remains the exclusive authority; SQLite only receives approved read-only connections. [CITED: 61-CONTEXT.md] [CITED: src/personal_knowledge/adapters/agentsview.py] |
| Task/session/event/Candidate durability and SSE | Kernel runtime | Database / Storage | Existing ledgers/journal/metadata stores already model idempotency, cancellation and receipts. [CITED: apps/personal_intelligence_kernel/src/tasks/ledger.mjs] [CITED: apps/personal_intelligence_kernel/src/events/journal.mjs] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---:|---|---|
| `@earendil-works/pi-coding-agent` | 0.83.0 (installed) | Existing locked Pi Session/tool-loop SDK | The current Kernel already pins and imports this package; its `AgentSession.prompt`, subscription, active-tool and abort APIs support the required iterative turn. [CITED: apps/personal_intelligence_kernel/package.json] [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts] |
| Electron | 43.3.0 (npm 2026-08-04) | Local `BrowserWindow`, preload bridge and packaged shell | Locked desktop choice; Electron's official guidance supports context isolation, sandboxing and narrow `contextBridge` APIs. **[ASSUMED: slopcheck could only query PyPI, not npm; human verification required before install.]** [CITED: https://www.electronjs.org/docs/latest/tutorial/security] [VERIFIED: npm registry] |
| Node.js | 24.13.0 (local) | Kernel and Electron main/preload runtime | Current Kernel declares Node `>=22.19.0`; installed Node meets that constraint. [CITED: apps/personal_intelligence_kernel/package.json] [VERIFIED: local environment] |
| Python | 3.14.2 (local) | Existing authority, SQLite policy, projections and pytest | The project already exposes its authority through Python services and is configured for Python `>=3.11`. [CITED: pyproject.toml] [VERIFIED: local environment] |

### Supporting

| Library / component | Version | Purpose | When to Use |
|---|---:|---|---|
| Existing React/Vite Cockpit dependencies | existing app only | Reference only for established TS/test conventions | Do not import Cockpit UI or make it the Phase 61 visual base; keep desktop renderer dependency-free or use its existing local tooling only if the plan proves isolation. [CITED: apps/personal_decision_cockpit/package.json] [CITED: 61-CONTEXT.md] |
| Python `sqlite3` standard library | stdlib | Read-only approved evidence query connection | Use behind the Python Domain Tool only; direct renderer/Node database opening is forbidden. [CITED: src/personal_knowledge/adapters/agentsview.py] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|---|---|---|
| Electron local renderer | Existing browser Cockpit | Rejected by locked D-04..D-08: browser Cockpit remains intact but is neither replaced nor the visual reference. [CITED: 61-CONTEXT.md] |
| Pi `AgentSession.prompt()` loop | Outer provider call plus custom `SkillEngine` iteration | Rejected by D-13: it duplicates Pi loop responsibility and cannot prove the real Agent tool loop. [CITED: 61-CONTEXT.md] |
| New desktop/session/Candidate stores | Existing Kernel task/session/event/Candidate stores | Rejected by D-28; extend typed authority contracts rather than create parallel truth. [CITED: 61-CONTEXT.md] |

**Installation:**
```bash
cd apps/personal_intelligence_desktop
npm install --save-dev electron@43.3.0
```

Do not install an app packager or a UI/component framework in the Walking Skeleton. A local runnable Electron app meets the phase's “packaged/local” criterion; installer/distribution automation is a follow-up once the privacy and UAT contract is stable. [ASSUMED]

## Package Legitimacy Audit

| Package | Registry | Age / downloads | Source Repo | slopcheck | Disposition |
|---|---|---|---|---|---|
| `electron` | npm | Created 2022; 5,920,486 downloads for 2026-08-02..09 | `github.com/electron/electron` | Tool version 0.6.1 only checked PyPI and falsely returned `SLOP`; it cannot validate npm here. | **[ASSUMED] Human verify before install**; official Electron docs plus npm metadata support selection, but the required npm-capable slopcheck verdict is unavailable. [VERIFIED: npm registry] [CITED: https://www.electronjs.org/docs/latest/tutorial/security] |

**Packages removed due to slopcheck [SLOP] verdict:** none — the observed `SLOP` result was an invalid PyPI lookup for an npm package, not a package legitimacy finding. [VERIFIED: local environment]

**Packages flagged as suspicious [SUS]:** none; planner must add a `checkpoint:human-verify` before the Electron install because npm-capable slopcheck was unavailable. [ASSUMED]

## Architecture Patterns

### System Architecture Diagram

```text
Local Electron window (only local app assets)
  Renderer: conversation UI / cards / drawers
      │ named, schema-checked preload methods only
      ▼
  Main: IPC sender + payload guard, process supervisor
      │ localhost requests; no DB/filesystem capability to renderer
      ├──────────────► Kernel :8790
      │                 conversation.turn
      │                   └─ contained Pi AgentSession
      │                      model -> active leased Tool -> Domain Bridge -> receipt
      │                      ^----------------------------------------- continued reasoning
      │                 task/session/event/SSE projection (metadata only)
      ▼
  Python rag-api :8000 / Pi Domain Gateway
      ├─ capability + Skill lease validation
      ├─ evidence.sqlite_query (allowlisted SELECT/CTE only)
      ├─ freshness projection (source→AgentView, AgentView→canonical)
      └─ deterministic reflection trigger -> Candidate -> guarded review -> derived projection
              │                          │                    │
              ▼                          ▼                    ▼
       AgentView source RO       canonical authority       append-only feedback
       / approved SQLite RO      + fingerprint guards      + calibration inputs
```

The route is deliberately loopback-preserving: Electron is a local native shell, not a replacement for the Kernel/Python authority boundary. [CITED: 61-CONTEXT.md]

### Recommended Project Structure

```text
apps/personal_intelligence_desktop/
├── package.json                    # Electron-only local run/test scripts
├── src/main.mjs                    # BrowserWindow, CSP/navigation/IPC guards, service supervisor
├── src/preload.mjs                 # contextBridge with one method per allowed action
├── src/desktop-api-schema.mjs      # shared named action/response validators and safe errors
├── src/renderer/                   # local HTML/CSS/JS conversation-first UI (UI-SPEC tokens/copy)
└── test/                           # Node tests for IPC schema, renderer view models, no capability leak

apps/personal_intelligence_kernel/src/
├── runtime/conversation-session.mjs # real-model contained-session factory and per-turn tool lease
├── conversation/turn-service.mjs    # session prompt/event-to-sanitized response adapter
└── kernel-host.mjs                  # narrowly dispatches conversation route; preserve existing user diff

src/personal_knowledge/application/conversation/
├── harness_freshness.py             # typed dual-watermark/freshness projection
└── harness_reflection.py            # deterministic delta -> evidence-bound Candidate adapter

src/personal_knowledge/services/
├── evidence_sqlite_tool.py          # grammar/scope/bounds/fingerprint/receipt authority tool
├── harness_conversation_service.py  # typed desktop-safe read/review view models
└── pi_domain_gateway.py             # explicit operation dispatch only, never dynamic callable/path
```

Exact names are discretionary; the required boundary is not. Do not put Electron UI state or raw bodies in the kernel's metadata-only `SessionStore`, and do not add a second generic broker. [CITED: apps/personal_intelligence_kernel/src/sessions/store.mjs] [CITED: 61-CONTEXT.md]

### Pattern 1: Pi-owned iterative conversation turn

**What:** Build a per-turn contained Pi session with an actual configured model runtime, derive active custom Tools from the selected Skill lease, subscribe before invoking `session.prompt()`, then await idle and emit a sanitized answer/receipt bundle. [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts]

**When to use:** Every Conversation/Reflection model turn. Operator uses a separate profile and is not in the default desktop conversation lease. [CITED: 61-CONTEXT.md]

**Concrete change needed:** `resource-policy.mjs` currently hardcodes `SYNTHETIC_MODEL` plus `providerFreeRuntime()`, while `kernel-host.mjs` calls `providerAdapter.generate()` and `SkillEngine.run()`. Retain the no-extension/no-skill/no-context-file resource policy, but pass a real, already-approved runtime/model and set `session.setActiveToolsByName(leasedToolNames)` before `session.prompt()`. The `productionTool()` wrapper must call the Capability Broker with task/correlation/idempotency bindings and return only bounded tool content plus a receipt descriptor; it must not return raw data/SQL/bodies to the model or renderer. [CITED: apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs] [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs]

```javascript
// Source: local Pi SDK declarations/examples, adapted to project containment.
const events = [];
const unsubscribe = session.subscribe((event) => events.push(projectSafeEvent(event)));
try {
  session.setActiveToolsByName(leasedToolNames); // selected Skill only
  await session.prompt(userPrompt, { expandPromptTemplates: false, source: "rpc" });
  await session.waitForIdle();
  return toConversationTurn(events); // final answer + receipt metadata, no raw trace
} finally {
  unsubscribe();
  session.dispose();
}
```

This uses Pi's prompt and continuation lifecycle instead of reproducing it outside the session. [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts]

### Pattern 2: Lease-scoped Tool registry, not all 44 tools

**What:** The router first returns either no Skill or a single read-only primary Skill, optionally one bounded supporting Skill. Build the union lease from their manifest allowlists, reject any Tool proposal outside it, and bind the Skill checksum, capability-registry checksum, profile, privacy ceiling, budget and timeout into each receipt. [CITED: governance/manifests/ai/pi-skills.json] [CITED: governance/manifests/capabilities/project-capabilities.json]

**When to use:** First slice should select `knowledge.research`: it is active, R1, has only five read operations (`knowledge.search`, `evidence.resolve`, `knowledge.get`, `wiki.page`, `external.list`), and no confirmation/write steps. Do not use data-maintenance, snapshot, or recovery Skills in default conversation. [CITED: governance/manifests/ai/pi-skills.json]

### Pattern 3: Approved-query SQLite authority Tool

**What:** Implement an explicit query descriptor, not a free text SQL console:

```json
{
  "database_id": "agentsview_normalized_v1",
  "query_id": "conversation.session_recent_by_project_v1",
  "parameters": {"project": "…", "limit": 20},
  "scope": {"project": "…"}
}
```

Map `query_id` to a compile-time SQL template that projects only approved views/columns, parameterize user values, clamp row/byte/time limits, open `file:...?mode=ro`, execute `PRAGMA query_only=ON`, and return an immutable receipt: `database_id`, schema/snapshot/freshness binding, statement checksum, row/byte/duration, truncation, result status and receipt ID. The UI may show only the executed/desensitized template, never an editor or raw params. [CITED: src/personal_knowledge/adapters/agentsview.py] [CITED: 61-UI-SPEC.md]

**Why not accept arbitrary SELECT:** A lexical `SELECT` prefix cannot safely prove one statement, table/column scope, CTE mutation, `PRAGMA`, `ATTACH`, `load_extension`, result size, or planner cost. Existing code provides `mode=ro`/`query_only` and schema gates but no generic SQL authorizer or arbitrary-query API; therefore Phase 61 needs a descriptor compiler/allowlist in Python. [CITED: src/personal_knowledge/adapters/agentsview.py] [VERIFIED: codebase grep]

### Pattern 4: Deterministic delta-to-reflection chain

**What:** Subscribe to an explicit canonical conversation-delta event only after the sync/close path has produced its source snapshot and watermark bindings. Form a stable `reflection_key = sha256(event_id + source_snapshot_checksum + rule_version)`, enforce uniqueness before model work, persist evidence refs/Observation/Candidate metadata and receipt, then append a candidate-staged event. Acceptance uses a guarded Python command with explicit confirmation; ignore/edit are append-only feedback records. [CITED: apps/personal_intelligence_kernel/src/events/schema.mjs] [CITED: apps/personal_intelligence_kernel/src/candidates/store.mjs] [CITED: 61-CONTEXT.md]

**Projection:** Adapt the existing personal-state normalization/projection path: generated Candidate has `provenance_class=inference`, valid interval, confidence, uncertainty, snapshot-bound support and conflicts; the derived version is retrieved separately from Evidence. `normalize_candidates()` rejects source bodies/secrets and missing/mixed evidence, while `project_current_state()` exposes formation/lifecycle trace and supersession instead of a fixed personality score. [CITED: src/personal_knowledge/intelligence/state_projection.py]

### Anti-Patterns to Avoid

- **One provider call then fixed SkillEngine steps:** it is the current implementation and does not meet HARNESS-02's real iterative Pi Tool loop. [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs]
- **Expose all capability tools then “tell the model not to use writes”:** least privilege must be enforced by the session's active-tool lease and the Python gateway. [CITED: 61-CONTEXT.md]
- **Electron renderer calls `fetch` to arbitrary localhost endpoints:** route only named preload methods to main; main has fixed paths/schemas and validates the sender. [CITED: https://www.electronjs.org/docs/latest/tutorial/context-isolation] [CITED: https://www.electronjs.org/docs/latest/tutorial/ipc]
- **Free-form SQL textbox or a Node-side SQLite connection:** violates D-16 and bypasses Python evidence/privacy enforcement. [CITED: 61-CONTEXT.md]
- **Treat accepted text as canonical fact or active knowledge:** acceptance only enters the governed Candidate/canonical path and derived projection; existing promotion/rollback gates remain intact. [CITED: 61-CONTEXT.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| Agent planning/tool continuation | A second JavaScript agent loop | Pi `AgentSession.prompt()` + events/idle APIs | The Pi session already owns tool messages, continuation, subscriptions, abort and settle lifecycle. [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts] |
| Capability authorization | Desktop-side policy conditions | Existing capability manifest + Kernel Domain Bridge + Python `PiDomainGateway` | Registry checks checksums/profile; gateway rejects unknown input and requires task/idempotency/binding/capability. [CITED: apps/personal_intelligence_kernel/src/tools/capability-registry.mjs] [CITED: src/personal_knowledge/services/pi_domain_gateway.py] |
| Durable task/event/recovery state | New desktop queues or DB | Existing TaskLedger, EventJournal, SessionStore, CandidateStore, RuntimeControl and SSE | These already provide versioning/idempotency/cancel/reconcile/metadata-only persistence. [CITED: apps/personal_intelligence_kernel/src/tasks/ledger.mjs] [CITED: apps/personal_intelligence_kernel/src/events/journal.mjs] |
| Evidence lineage / state projection | “profile document” tables | Existing typed evidence/Candidate state projection plus a narrow reflection adapter | Existing code enforces snapshot identity, evidence checksums, time, confidence, lifecycle and privacy rejection. [CITED: src/personal_knowledge/intelligence/state_projection.py] |
| Desktop privilege boundary | `nodeIntegration: true` renderer | `contextIsolation`, sandbox, restrictive CSP and one-method-per-action `contextBridge` | Electron explicitly warns against exposing raw IPC or renderer Node access. [CITED: https://www.electronjs.org/docs/latest/tutorial/security] [CITED: https://www.electronjs.org/docs/latest/tutorial/context-isolation] |

## Common Pitfalls

### Pitfall 1: Calling `session.prompt()` on the current contained session

**What goes wrong:** It fails before a model/tool turn because the current factory uses `SYNTHETIC_MODEL` and a runtime whose provider methods throw. [CITED: apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs]

**How to avoid:** Add a separate real-model contained-session factory that retains every containment flag but uses the configured approved provider runtime/model. Assert there are no ambient extensions, Skills, prompts, themes, context files or built-ins before the turn. [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs]

### Pitfall 2: “Skill selected” but its lease never constrains Pi

**What goes wrong:** The present resource factory registers every active production operation at session construction, whereas `SkillEngine` limits only its own fixed steps. A model-driven turn would see too much unless active tools are reduced per lease. [CITED: apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs] [CITED: apps/personal_intelligence_kernel/src/skills/engine.mjs]

**How to avoid:** Derive and checksum an exact leased tool-name set; call `setActiveToolsByName()` before the prompt; have the wrapper and Python gateway independently reject non-leased operation IDs. [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts]

### Pitfall 3: Misreporting freshness as a scalar

**What goes wrong:** AgentView source freshness and canonical sync freshness have different watermarks/backlogs. A successful source probe is not proof canonical has absorbed that delta. [CITED: 61-CONTEXT.md]

**How to avoid:** Return both legs and bind every answer/SQLite receipt to source identity, source snapshot/probe time, canonical watermark time, backlog count/status, and a limitation string. Fail closed to `unknown/stale`, never `current`. [CITED: 61-UI-SPEC.md]

### Pitfall 4: Browser-compatible Electron configuration without true isolation

**What goes wrong:** A renderer with Node integration, raw `ipcRenderer`, broad IPC handlers, remote navigation or permissive CSP turns UI injection into host compromise. [CITED: https://www.electronjs.org/docs/latest/tutorial/security]

**How to avoid:** `nodeIntegration:false`, `contextIsolation:true`, `sandbox:true`, local packaged assets, `default-src 'self'`, deny navigation/new windows/permissions, verify IPC sender and expose one validated bridge method per action. [CITED: https://www.electronjs.org/docs/latest/tutorial/security] [CITED: https://www.electronjs.org/docs/latest/tutorial/context-isolation]

### Pitfall 5: Reusing Candidate staging as a projection write bypass

**What goes wrong:** Kernel CandidateStore intentionally rejects serving/promotion fields and preserves only metadata. Making it write canonical or active state would violate its contract. [CITED: apps/personal_intelligence_kernel/src/candidates/store.mjs]

**How to avoid:** CandidateStore stays staging/audit metadata; a Python authority command performs accepted-version derivation with confirmation, invariant validation and its own receipt. [CITED: 61-CONTEXT.md]

## Code Examples

### Secure Electron preload shape

```javascript
// preload.mjs — no raw ipcRenderer or Node modules exposed to the renderer.
import { contextBridge, ipcRenderer } from "electron";
import { parseConversationInput, parseCandidateAction } from "./desktop-api-schema.mjs";

contextBridge.exposeInMainWorld("harness", {
  sendTurn: (value) => ipcRenderer.invoke("harness:conversation-turn", parseConversationInput(value)),
  reviewCandidate: (value) => ipcRenderer.invoke("harness:candidate-review", parseCandidateAction(value)),
  getLastConversation: () => ipcRenderer.invoke("harness:last-conversation"),
});
```

Use one method per channel, never expose generic `send`/`invoke`. [CITED: https://www.electronjs.org/docs/latest/tutorial/context-isolation] [CITED: https://www.electronjs.org/docs/latest/tutorial/ipc]

### Read-only evidence Tool contract

```python
# EvidenceSqliteTool.execute() sketch: descriptors select the SQL, user input only fills params.
connection = sqlite3.connect(f"file:{approved_path.as_posix()}?mode=ro", uri=True)
connection.execute("PRAGMA query_only=ON")
statement, params = APPROVED_QUERIES[query_id].compile(validated_scope, validated_params)
rows = fetch_bounded(connection, statement, params, max_rows=50, max_bytes=16_384, timeout_ms=3_000)
return receipt_for(statement, database_identity, freshness_binding, rows)
```

This mirrors the existing AgentView RO connection policy but adds the descriptor, result-limit and receipt layers mandated for HARNESS-03. [CITED: src/personal_knowledge/adapters/agentsview.py] [CITED: 61-CONTEXT.md]

## State of the Art

| Old / current approach | Phase 61 approach | Impact |
|---|---|---|
| Current Kernel registers a contained Session but executes a provider single call plus fixed `SkillEngine` steps. | Pi `AgentSession` is the live iterative turn executor; the Skill broker only leases Tools and policies. | Meets D-13 without a parallel agent loop. [CITED: apps/personal_intelligence_kernel/src/kernel-host.mjs] |
| Browser Cockpit has projected state pages. | Electron opens directly in conversation; receipts, freshness, evidence and Candidate review are inline/on-demand. | Meets locked desktop/UI contract without deleting Cockpit. [CITED: 61-CONTEXT.md] [CITED: 61-UI-SPEC.md] |
| Existing adapters use read-only SQLite for fixed code paths. | New dedicated descriptor-limited evidence query Tool makes one governed direct evidence slice available to Pi. | Avoids arbitrary SQL/path capabilities. [CITED: src/personal_knowledge/adapters/agentsview.py] |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | A runnable local Electron shell is sufficient for Phase 61; installer/auto-update packaging can wait. | Standard Stack | Planner may need an installer task if “packaged” is interpreted more strictly. |
| A2 | `knowledge.research` is the safest first default Skill for the vertical conversational path. | Architecture Patterns | It may need a narrower new read-only Skill after live model/tool prompt evaluation. |
| A3 | The currently installed slopcheck cannot perform an npm legitimacy verdict, so Electron install needs a human checkpoint. | Package Legitimacy Audit | Package install remains gated despite official docs/npm evidence. |

## Resolved Planning Decisions

1. **R-61-01 — Provider and UAT.** Required automated and desktop UAT uses the existing deterministic fixture/replay provider with zero paid/live calls, while traversing the real Pi `AgentSession.prompt()` event, Tool, and idle path. An optional live/paid-provider smoke is excluded from Phase 61 acceptance and requires a separate explicit human approval and budget checkpoint.

2. **R-61-02 — Conversation projection and retention.** Python's canonical `ConversationRepository` is authoritative for last/recent/selected thread reads. A named read-only local projection route returns a safe `ConversationThreadView`: normalized user/assistant display messages only, stable message ID, role, display text, created time, source/evidence ref, pagination/truncation, and freshness. It excludes thinking, raw Tool bodies, `input_json`, provider bodies, credentials, and private diagnostics. Desktop main/preload/renderer do not persist conversation bodies to disk or localStorage; selected-thread content is ephemeral renderer state, and logs/receipts/telemetry retain only IDs, counts, checksums, and status. Empty, stale, partial, and paginated responses have explicit safe states and Node, Python, and UAT privacy tests.

3. **R-61-03 — SQLite descriptor.** The first fixed Tool operation is `evidence.sqlite_query`; the model supplies only a versioned query ID and typed parameters, never SQL. Descriptor `conversation.evidence_messages.v1` is backed only by the canonical conversation SSOT through a Python-owned prepared-query/repository adapter. It returns a bounded evidence-safe row projection for the inline SQLite card, with source/database identity, version/freshness binding, query checksum, truncation, and receipt metadata. The executor derives the physical table/column mapping from the live repository/schema and keeps it private to the Python adapter; the manifest exposes stable descriptor fields rather than physical SQL.

4. **R-61-04 — Skill lease.** `knowledge.research` remains the sole selected read-only primary Skill for the Walking Skeleton. After the capability is registered, its versioned/checksummed `allowed_tools` lease includes `evidence.sqlite_query`. Manifest-drift, privacy-ceiling, lease, unknown-query-ID, and Python-gateway double-denial tests are mandatory. No second Skill selector or recursive supporting-Skill invocation is introduced.

5. **R-61-05 — Route dependencies.** Proactive local-route registration and guarded wiring occur only after deterministic Candidate/proactive contracts exist. The desktop shell first exposes schemas and a safe bridge; fixed local route integration waits for the conversation, evidence/freshness, and proactive providers. Dependency waves must remain acyclic. The renderer references `getProactiveState`, `updateProactiveControls`, `dismissProactive`, and `undoProactiveDismissal` exactly.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---|---|---|
| Node.js | Kernel/Electron main | ✓ | v24.13.0 | — [VERIFIED: local environment] |
| npm | Electron install/build | ✓ | 11.6.2 | — [VERIFIED: local environment] |
| Python | Python authority/tests | ✓ | 3.14.2 | — [VERIFIED: local environment] |
| Pi packages | real AgentSession loop | ✓ | `@earendil-works/pi-coding-agent` 0.83.0 installed | Existing pinned installation. [VERIFIED: codebase] |
| Electron | desktop shell | ✗ | — | Install is required and human-verification-gated. [VERIFIED: codebase] |
| npm-capable slopcheck | dependency legitimacy gate | ✗ | installed 0.6.1 only queried PyPI | Human package review before Electron install. [VERIFIED: local environment] |

**Missing dependencies with no fallback:** Electron package installation (after human verification). [ASSUMED]

**Missing dependencies with fallback:** None. [VERIFIED: local environment]

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Python framework | pytest, configured in `pytest.ini`; focused commands can use `python -m pytest -q`. [CITED: pytest.ini] |
| Kernel framework | Node built-in test runner, `node --test test/*.test.mjs`. [CITED: apps/personal_intelligence_kernel/package.json] |
| Desktop framework | Wave 0: Node built-in test runner over pure IPC/schema/view-model modules; no Electron automation framework exists now. [VERIFIED: codebase grep] |
| Desktop UAT | Manual local Electron launch with a deterministic fixture/replay provider and an evidence-safe checklist. [ASSUMED] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| HARNESS-01 | Main creates secure local window; last-conversation view model and navigation load. | Node unit + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs` | ❌ Wave 0 |
| HARNESS-02 | One `session.prompt()` turn calls only leased Tool(s), receives Tool receipt, then final answer; no outer fixed loop. | Kernel integration | `node --test apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | ❌ Wave 0 |
| HARNESS-03 | SELECT/CTE descriptors succeed; mutation, ATTACH, unsafe PRAGMA, extension/load, scope escape, excessive rows/bytes/time reject; DB fingerprints unchanged. | Python unit/integration | `python -m pytest -q tests/unit/test_evidence_sqlite_tool.py tests/integration/test_evidence_sqlite_tool.py` | ❌ Wave 0 |
| HARNESS-04 | Two-hop freshness/backlog is returned and stale/unknown never says current. | Python contract | `python -m pytest -q tests/contract/test_harness_freshness.py` | ❌ Wave 0 |
| HARNESS-05 | Same canonical delta/rule version deduplicates; Candidate has evidence/conflict/time/confidence/receipt. | Python integration + Kernel event test | `python -m pytest -q tests/integration/test_harness_reflection.py` | ❌ Wave 0 |
| HARNESS-06 | accept/edit/ignore require correct confirmation/version; no direct authority mutation; receipts and feedback are append-only. | Python contract + desktop UAT | `python -m pytest -q tests/contract/test_harness_candidate_review.py` | ❌ Wave 0 |
| HARNESS-07 | accepted version projects later with provenance/freshness/confidence/time/conflicts/supersession; generated draft never becomes fact. | Python unit/integration | `python -m pytest -q tests/unit/test_personal_state_projection.py tests/integration/test_harness_projection.py` | ✅ / ❌ Wave 0 |
| HARNESS-08 | renderer has no Node/raw IPC/endpoint escape; cancel/reconcile remains truthful; privacy and authority fingerprints hold. | Node/Python integration + desktop UAT | `node --test apps/personal_intelligence_desktop/test/*.test.mjs && python -m pytest -q tests/integration/test_pi_kernel_events.py` | ❌ / ✅ |

### Required Negative and Invariant Tests

- Assert a real conversation route calls `session.prompt()` and observes Tool-call/result plus final `agent_settled`; reject a provider-only or `SkillEngine.run()`-only implementation. [CITED: apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts]
- Assert every Tool proposal outside the current lease is refused both before bridge dispatch and by Python gateway; production default turn exposes no mutation/promotion/snapshot Tools. [CITED: src/personal_knowledge/services/pi_domain_gateway.py]
- Fingerprint every authority DB and active pointer before/after read-only SQL, error, cancel, and ignored Candidate cases; fingerprints must match except the intended append-only Candidate/feedback/projection store for confirmed acceptance. [CITED: 61-CONTEXT.md]
- Scan all renderer/preload/main response objects, logs and receipts for body/prompt/completion/credential/secret fields; fixtures should contain sentinel secrets and raw bodies to prove redaction. [CITED: apps/personal_intelligence_kernel/src/sessions/store.mjs] [CITED: src/personal_knowledge/intelligence/state_projection.py]
- Assert Electron configuration: `nodeIntegration === false`, `contextIsolation === true`, `sandbox === true`, CSP present, navigation/new-window denied, and preload exports no raw `ipcRenderer`. [CITED: https://www.electronjs.org/docs/latest/tutorial/security] [CITED: https://www.electronjs.org/docs/latest/tutorial/context-isolation]
- Preserve a regression test for the user's non-default provider mode behavior in `kernel-host.mjs`. [CITED: git diff -- apps/personal_intelligence_kernel/src/kernel-host.mjs]

### Desktop UAT Script

1. Start the existing local REST/Kernel dependencies with an approved non-production test/replay provider; open the Electron app and confirm it restores the last allowed conversation or declared empty state without opening a browser. [CITED: docs/AGENTS.md] [ASSUMED]
2. Submit the fixed historical/project prompt; observe one selected read-only Skill, collapsed tool row, final answer and expandable receipt, with no raw trace/body. [CITED: 61-UI-SPEC.md]
3. Open the SQLite evidence card; verify identity, checksum, two freshness legs, bounds/truncation and safe empty/rejected error copy. Exercise one rejected query fixture and prove no fingerprint change. [CITED: 61-UI-SPEC.md]
4. Emit the fixed canonical conversation-delta fixture twice; verify exactly one inline Candidate with source evidence, conflict/time/confidence and receipt. [CITED: 61-CONTEXT.md]
5. Exercise edit → explicit accept confirmation and ignore → undo. Verify accepted content appears only as a versioned derived projection in a next turn; verify ignored Evidence/history remains traceable. [CITED: 61-UI-SPEC.md]
6. Exercise cancel and `outcome_unknown` reconcile UI; verify neither appears as success and no partial write is claimed. [CITED: 61-UI-SPEC.md] [CITED: apps/personal_intelligence_kernel/test/kernel-workflow.test.mjs]

### Sampling Rate

- **Per task commit:** impacted Node or pytest command from the map, plus `git diff --check`. [CITED: pytest.ini]
- **Per wave merge:** `npm --prefix apps/personal_intelligence_kernel test` and focused Python harness suite. [CITED: apps/personal_intelligence_kernel/package.json]
- **Phase gate:** all mapped tests green, current Phase 55–60 activation/rollback regressions green, and the six-step desktop UAT recorded without private bodies. [CITED: .planning/STATE.md]

### Wave 0 Gaps

- [ ] `apps/personal_intelligence_desktop/test/main-preload.test.mjs` — validates IPC allowlist, sender, unsafe config and safe error projection.
- [ ] `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` — proves real Pi session event loop/leased tools/cancel/reconcile.
- [ ] `tests/unit/test_evidence_sqlite_tool.py` and `tests/integration/test_evidence_sqlite_tool.py` — all positive/negative SQL and fingerprint cases.
- [ ] `tests/contract/test_harness_freshness.py`, `tests/integration/test_harness_reflection.py`, `tests/contract/test_harness_candidate_review.py`, `tests/integration/test_harness_projection.py`.
- [ ] A redacted deterministic fixture package and a desktop UAT record template; fixtures must not use `data/` or `var/` private content. [CITED: docs/AGENTS.md]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | Yes | Local process capability header and trusted main→loopback boundary; do not treat renderer as trusted. [CITED: src/personal_knowledge/services/pi_domain_gateway.py] |
| V3 Session Management | Yes | Existing versioned Task/Session/Event identity, idempotency, cancellation and reconcile; explicit desktop retention design required. [CITED: apps/personal_intelligence_kernel/src/sessions/store.mjs] |
| V4 Access Control | Yes | Skill-derived tool lease, capability registry checksums/profile, named Electron bridge and sender verification. [CITED: governance/manifests/ai/pi-skills.json] [CITED: https://www.electronjs.org/docs/latest/tutorial/security] |
| V5 Input Validation | Yes | Schema-check all IPC and Domain Tool inputs; descriptor IDs/typed params only for SQLite, no raw endpoint/path/SQL. [CITED: src/personal_knowledge/services/pi_domain_gateway.py] |
| V6 Cryptography | Yes | Reuse existing SHA-256 checksums/fingerprints/confirmation mechanisms; do not introduce custom cryptography. [CITED: apps/personal_intelligence_kernel/src/events/schema.mjs] |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| XSS/renderer-to-host escape | Elevation of Privilege | Sandbox/context isolation/no Node integration/CSP/named bridge/IPC sender check. [CITED: https://www.electronjs.org/docs/latest/tutorial/security] |
| Arbitrary SQLite SQL, ATTACH, PRAGMA or resource enumeration | Tampering / Information Disclosure | Descriptor-only allowlist, RO URI + `query_only`, one statement, scoped columns, parameter binding, row/byte/time limits and fingerprints. [CITED: 61-CONTEXT.md] |
| Tool lease escalation / manifest drift | Elevation of Privilege | Hash-bound Skill and registry descriptors, active-tool set plus bridge/gateway double check, fail closed. [CITED: apps/personal_intelligence_kernel/src/tools/capability-registry.mjs] |
| Receipt/trace leaks raw private body or credentials | Information Disclosure | Metadata-only stores, projection sanitizers, sentinel negative tests, no UI raw trace. [CITED: apps/personal_intelligence_kernel/src/sessions/store.mjs] [CITED: 61-UI-SPEC.md] |
| Duplicate trigger or retry creates repeated Candidate/write | Repudiation / Tampering | Event idempotency, deterministic reflection key, candidate uniqueness, version/confirmation checks and append-only receipts. [CITED: apps/personal_intelligence_kernel/src/events/journal.mjs] |

## Sources

### Primary (HIGH confidence)

- [Pi AgentSession local declarations](apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts) — prompt, subscription, tool activation, idle and abort APIs from installed pinned package.
- [Kernel host and containment policy](apps/personal_intelligence_kernel/src/kernel-host.mjs) — current one-shot/fixed-skill execution gap and user-owned provider-mode edit.
- [Capability/Skill manifests](governance/manifests/capabilities/project-capabilities.json) and [Skill manifests](governance/manifests/ai/pi-skills.json) — current active operation/Skill contracts.
- [AgentView adapter](src/personal_knowledge/adapters/agentsview.py) — live source RO, schema/probe/snapshot safeguards.
- [Personal state projection](src/personal_knowledge/intelligence/state_projection.py) — evidence/time/confidence/lifecycle projection invariants.
- [Electron Security](https://www.electronjs.org/docs/latest/tutorial/security), [Context Isolation](https://www.electronjs.org/docs/latest/tutorial/context-isolation), [IPC](https://www.electronjs.org/docs/latest/tutorial/ipc) — official desktop process/bridge security guidance.

### Secondary (MEDIUM confidence)

- [Electron Application Packaging](https://www.electronjs.org/docs/latest/tutorial/application-distribution) — distribution context; no packaging workflow is selected for this phase.
- npm registry metadata queried for `electron@43.3.0` — version, publish date, repository and download count.

### Tertiary (LOW confidence)

- None; package-install decision is explicitly human-gated because the local slopcheck lacks npm support.

## Metadata

**Confidence breakdown:**

- Standard stack: MEDIUM — Pi/runtime and project topology are live-code verified; Electron package selection is locked but npm-capable slopcheck was unavailable.
- Architecture: HIGH — driven by locked CONTEXT/UI-SPEC and existing Kernel/Python boundaries.
- Pitfalls: HIGH — concrete current execution gap, existing read-only contracts and official Electron security guidance were verified.

**Research date:** 2026-08-09
**Valid until:** 2026-08-16 for Electron/npm package and Pi integration surface; 2026-09-08 for codebase architecture if no intervening changes.
