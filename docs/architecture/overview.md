<!-- generated-by: gsd-doc-writer -->
# System Architecture

## System overview

Personal Knowledge System is a local, privacy-first personal intelligence platform. It ingests native conversation and activity sources, converts them into provenance-bearing canonical records, derives evaluated knowledge and search indexes, and exposes those results through command-line, REST, MCP, and desktop conversation interfaces. The architecture is layered around explicit authority boundaries: adapters capture external data, application modules own synchronization and knowledge lifecycles, retrieval modules read promoted serving state, and delivery surfaces reach those capabilities through fixed contracts rather than direct database access.

The source dependency direction is delivery → application → domain/foundation, with infrastructure reached through explicit contracts. `src/personal_knowledge/domains/` is compatibility-only; new product code imports canonical implementations from `application/`, `evaluation/`, and `core/`.

## Component diagram

```text
Native sources
      |
      v
Adapters + sync ---> Canonical data ---> Knowledge lifecycle ---> Evaluation gates
                           |                                         |
                           |                                         v
                           +-------------------------------> Active retrieval
                           |                                         |
                           v                                         v
                    Python REST / MCP / domain gateway <------> Pi Kernel
                           |    ^                                  ^
                           v    |                                  |
                    CLI / MCP clients                              |
                                +------ Electron desktop shell -----+
```

The desktop uses two deliberately separate read paths. Named Electron bridge methods call fixed loopback routes for predefined desktop state, while AI evidence queries run through a Kernel skill lease, Capability Registry, domain bridge, and governed Python tool. Renderer, preload, and Electron main code do not open authoritative SQLite databases directly.

## Data flow

### Source data to serving knowledge

1. `pk-sync` enters through `personal_knowledge.cli.sync` and delegates to `application.sync`. Conversation-v2 synchronization probes native sources, captures content-addressed artifacts, selects an explicit family adapter, and produces sessions, typed events, relations, fidelity metadata, and provenance.
2. A new conversation generation is staged and checked before activation. The canonical conversation database under `data/canonical/agent/structured/db/` remains the conversation authority and provides compatibility projections for existing consumers.
3. `pk-ku` drives the incremental knowledge lifecycle: inspect, prepare, extract, evaluate, canary, promote, and watermark advancement. Evaluation is a gate; it does not silently promote a candidate.
4. Promotion updates the active knowledge collection selected by `var/db/knowledge_index_active.txt`. Retrieval modules combine canonical messages, conversation turns, knowledge units, and approved fallback layers without treating experimental memory data as the knowledge authority.
5. `rag-search`, REST handlers, MCP handlers, and governed Kernel tools read the active serving state and return bounded results with evidence and freshness metadata.

### Desktop conversation request

1. The renderer calls a named method exposed by `apps/personal_intelligence_desktop/src/preload.cjs`. The preload and main process validate the intent against fixed schemas and IPC allowlists.
2. Electron main routes the normalized request only to the configured loopback authority: Python REST on port `8000` for fixed conversation history and project-scope reads, or the Kernel on port `8790` for turns, task control, candidate review, projection, and proactive controls.
3. For a conversation turn, `KernelHost` creates a contained session. `runConversationTurn` injects only bounded history and approved derived projection context, then exposes tools granted by the selected skill lease.
4. Project operations cross `createProjectDomainBridge` to the fixed Python `/internal/pi-domain/dispatch` route. `PiDomainGateway` validates the capability, declared operation, allowed fields, idempotency key, and binding before dispatching to a concrete read, evidence, orchestration, or guarded-write provider.
5. The Kernel records metadata-only lifecycle events in `EventJournal` and returns safe event categories to the desktop. Prompt bodies, completions, credentials, raw SQL, and physical schemas are excluded from governed event and receipt surfaces.

## Key abstractions

| Abstraction | Location | Responsibility |
|---|---|---|
| `TypedEvent`, `EventRelation`, `AdaptedSession` | `src/personal_knowledge/core/conversation_events.py` | Canonical conversation event, relation, session, fidelity, and provenance contracts. |
| `SourceArtifactSet`, `CapabilityDescriptor`, `AdaptationResult` | `src/personal_knowledge/adapters/conversation_sources/contracts.py` | Immutable adapter input and deterministic, provenance-validated adapter output. |
| Conversation adapter registry | `src/personal_knowledge/adapters/conversation_sources/registry.py` | Selects a versioned family-specific adapter and fails closed instead of using a generic parser. |
| `shadow_conversation_generation` / `activate_conversation_generation` | `src/personal_knowledge/application/conversation/v2_sync.py` | Stages and activates versioned canonical conversation generations. |
| `pk-ku` command seam | `src/personal_knowledge/application/ku.py` | Coordinates inspection, extraction, evaluation gates, promotion, lifecycle, and watermark operations. |
| Retrieval facade and layers | `src/personal_knowledge/retrieval/unified_search.py`, `src/personal_knowledge/retrieval/layers/` | Presents a stable search API over canonical, knowledge-unit, and fallback retrieval layers. |
| `PiDomainGateway` | `src/personal_knowledge/services/pi_domain_gateway.py` | Enforces the fixed operation registry, capability checks, input allowlists, binding, and idempotency before Python-domain dispatch. |
| `KernelHost` | `apps/personal_intelligence_kernel/src/kernel-host.mjs` | Owns contained model sessions, skills, task control, candidates, domain-tool bridging, and Kernel readiness. |
| `EventJournal` | `apps/personal_intelligence_kernel/src/events/journal.mjs` | Persists bounded Kernel lifecycle events and consumer checkpoints in SQLite. |
| Desktop bridge contract | `apps/personal_intelligence_desktop/src/desktop-api-schema.mjs`, `apps/personal_intelligence_desktop/src/preload.cjs`, `apps/personal_intelligence_desktop/src/main.mjs` | Constrains renderer access to named IPC methods and fixed localhost provider routes. |

## Directory structure rationale

```text
apps/                         User-facing and runtime applications
  personal_intelligence_desktop/  Electron conversation shell
  personal_intelligence_kernel/   Contained Node.js agent runtime
  personal_data_chatgpt/           ChatGPT MCP application and service scripts
  personal_decision_cockpit/       Retained React cockpit source
src/personal_knowledge/       Installable Python product package
  adapters/                   External-source and conversation-family adapters
  application/                Canonical use cases and lifecycle ownership
  core/                       Paths, privacy, event, provider, and SQLite foundations
  evaluation/                 Extraction, retrieval, compare, and audit gates
  retrieval/                  Search backends, serving selection, and stable facade
  services/                   REST, MCP, projection, gateway, and tool delivery
  domains/                    Legacy re-export compatibility shims
tests/                        Unit, contract, integration, governance, and UAT fixtures
assets/                       Versioned prompts, public evaluation fixtures, and vendor assets
governance/                   Machine-readable policies, schemas, and capability manifests
data/                         Private raw, staging, canonical, and import data
var/                          Generated databases, runtime state, reports, logs, and cache
docs/                         Architecture explanations and operator runbooks
tools/ and ops/               Repository tooling and operational helpers
archive/                      Quarantined or retained historical material
```

The separation keeps reviewed source and policies independent from private inputs and generated runtime state. `core.project_paths` is the path authority and derives locations from the repository root, preferring the current `data/` and `var/` layout while retaining limited legacy fallback behavior. `%USERPROFILE%/.agentsview/sessions.db` is an external protected source and is opened read-only; it is never relocated into the repository.

`apps/personal_decision_cockpit/` remains in the tree, but the current Python server explicitly disables its `/app` static hosting and ten cockpit-only projection routes. Active delivery still includes health, search, intelligence, decision, agent, orchestration, review, and wiki-topic handlers defined by `src/personal_knowledge/services/api_server.py`.
