# Phase 61: Conversation-first Desktop Harness and Evidence-bound Reflection Loop - Pattern Map

**Mapped:** 2026-08-09  
**Files analyzed:** 31 likely new/modified files (research names are discretionary where noted)  
**Analogs found:** 24 / 31

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `apps/personal_intelligence_desktop/package.json` | config | request-response | `apps/personal_intelligence_kernel/package.json` | role-match |
| `apps/personal_intelligence_desktop/src/main.mjs` | controller | request-response | `apps/personal_intelligence_kernel/src/server.mjs` | flow-match |
| `apps/personal_intelligence_desktop/src/preload.mjs` | provider | request-response | None (no Electron/preload code exists) | none |
| `apps/personal_intelligence_desktop/src/desktop-api-schema.mjs` | utility | transform | `apps/personal_intelligence_kernel/src/server.mjs` | partial |
| `apps/personal_intelligence_desktop/src/renderer/index.html` | component | event-driven | None (Cockpit is explicitly not a UI base) | none |
| `apps/personal_intelligence_desktop/src/renderer/app.mjs` | component | event-driven | `apps/personal_decision_cockpit/src/` (reference only) | partial |
| `apps/personal_intelligence_desktop/src/renderer/styles.css` | component | event-driven | None (new UI contract) | none |
| `apps/personal_intelligence_desktop/test/main-preload.test.mjs` | test | request-response | `apps/personal_intelligence_kernel/test/kernel-workflow.test.mjs` | flow-match |
| `apps/personal_intelligence_kernel/src/runtime/conversation-session.mjs` | service | streaming | `src/runtime/resource-policy.mjs` | role-match |
| `apps/personal_intelligence_kernel/src/conversation/turn-service.mjs` | service | streaming | `src/kernel-host.mjs` + Pi `agent-session.d.ts` | flow-match |
| `apps/personal_intelligence_kernel/src/kernel-host.mjs` | controller | request-response | itself: `executeSkillTask()` | modify-in-place |
| `apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs` | provider | request-response | itself: `createContainedSession()` | modify-in-place |
| `apps/personal_intelligence_kernel/src/server.mjs` | route | request-response | itself: `attachRequestHandler()` | modify-in-place |
| `apps/personal_intelligence_kernel/src/tools/domain-bridge.mjs` | service | request-response | itself: `createProjectDomainBridge()` | modify-in-place |
| `apps/personal_intelligence_kernel/src/tools/capability-registry.mjs` | utility | transform | itself: `loadCapabilityRegistry()` | modify-in-place |
| `governance/manifests/ai/pi-skills.json` | config | transform | existing `knowledge.research` entry | exact |
| `governance/manifests/capabilities/project-capabilities.json` | config | transform | existing `knowledge.search` entry | exact |
| `src/personal_knowledge/services/evidence_sqlite_tool.py` | service | file-I/O | `src/personal_knowledge/adapters/agentsview.py` | flow-match |
| `src/personal_knowledge/application/conversation/harness_freshness.py` | service | transform | `src/personal_knowledge/adapters/agentsview.py` | flow-match |
| `src/personal_knowledge/application/conversation/harness_reflection.py` | service | event-driven | `apps/.../src/events/journal.mjs` + `intelligence/state_projection.py` | flow-match |
| `src/personal_knowledge/services/harness_conversation_service.py` | service | request-response | `src/personal_knowledge/services/pi_domain_gateway.py` | role-match |
| `src/personal_knowledge/services/pi_domain_gateway.py` | middleware | request-response | itself: `PiDomainGateway.invoke()` | modify-in-place |
| `src/personal_knowledge/intelligence/state_projection.py` | model | transform | itself: normalize/project functions | modify-in-place |
| `apps/personal_intelligence_kernel/test/conversation-turn.test.mjs` | test | streaming | `test/kernel-workflow.test.mjs` | flow-match |
| `tests/unit/test_evidence_sqlite_tool.py` | test | file-I/O | `tests/integration/test_agentsview_source_adapter.py` | flow-match |
| `tests/integration/test_evidence_sqlite_tool.py` | test | file-I/O | `tests/integration/test_agentsview_source_adapter.py` | flow-match |
| `tests/contract/test_harness_freshness.py` | test | transform | `tests/integration/test_agentsview_source_adapter.py` | flow-match |
| `tests/integration/test_harness_reflection.py` | test | event-driven | `tests/integration/test_analysis_candidates.py` | flow-match |
| `tests/contract/test_harness_candidate_review.py` | test | CRUD | `tests/contract/test_pi_domain_gateway.py` | role-match |
| `tests/integration/test_harness_projection.py` | test | transform | `tests/unit/test_personal_state_projection.py` | exact |
| `tests/unit/test_personal_state_projection.py` | test | transform | itself: existing invariants | modify-in-place |

`apps/personal_intelligence_desktop/src/renderer/` is classified as three files for planning clarity. The UI-SPEC permits the exact internal layout to vary, but all renderer code stays presentation-only: it consumes sanitized view models and named preload actions, never loopback endpoints, database paths, raw receipts, or authority commands.

## Pattern Assignments

### Kernel real Pi turn: `runtime/conversation-session.mjs`, `conversation/turn-service.mjs`, `kernel-host.mjs`, `runtime/resource-policy.mjs`

**Primary analogs:** `apps/personal_intelligence_kernel/src/runtime/resource-policy.mjs`, `apps/personal_intelligence_kernel/src/kernel-host.mjs`, and installed Pi declarations `apps/personal_intelligence_kernel/node_modules/@earendil-works/pi-coding-agent/dist/core/agent-session.d.ts`.

**Imports and contained-resource pattern** (`resource-policy.mjs:1-11`, `135-170`):

```javascript
import { createAgentSession, DefaultResourceLoader, defineTool, SessionManager, SettingsManager } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { capabilityToolNames, loadCapabilityRegistry } from "../tools/capability-registry.mjs";

const resourceLoader = new DefaultResourceLoader({
  cwd: explicitCwd, agentDir: explicitAgentDir, settingsManager,
  noExtensions: true, noSkills: true, noPromptTemplates: true,
  noThemes: true, noContextFiles: true, systemPrompt: PRODUCTION_SYSTEM_PROMPT,
});
await resourceLoader.reload();
const { session } = await createAgentSession({
  cwd: explicitCwd, agentDir: explicitAgentDir, model, modelRuntime,
  resourceLoader, settingsManager, sessionManager,
  noTools: "builtin", tools: toolNames, customTools, thinkingLevel: "off",
});
```

**Lease and bridge pattern** (`resource-policy.mjs:54-72`; `domain-bridge.mjs:63-71`):

```javascript
const result = await invokeTool(operation.id, params);
return { content: [{ type: "text", text: JSON.stringify(result) }], details: result };

if (!allowed.has(operation)) throw new DomainBridgeError("skill_tool_escalation");
if (!input.task_id || !input.idempotency_key || !input.binding) {
  throw new DomainBridgeError("binding_required");
}
```

For Phase 61, create a **separate per-turn real-model factory**, retaining every containment flag above. Its only active tools must be the exact union of the selected zero/one primary Skill plus optional bounded support Skill; set that lease immediately before calling Pi. The present `createContainedSession()` hardcodes `SYNTHETIC_MODEL`/`providerFreeRuntime()` (`resource-policy.mjs:22-32,75-127,158-163`), so it is an isolation template, not the runnable conversation implementation.

**Pi lifecycle to copy** (SDK `agent-session.d.ts:272-276,318-323,364,436-441`): subscribe before `prompt`, call `setActiveToolsByName(leasedToolNames)`, await `prompt()` and `waitForIdle()`, and always unsubscribe/dispose. Observe only projected safe event categories such as tool call/result, `agent_settled`, and cancellation; never expose Pi message/trace objects verbatim.

```javascript
const events = [];
const unsubscribe = session.subscribe((event) => events.push(projectSafeEvent(event)));
try {
  session.setActiveToolsByName(leasedToolNames);
  await session.prompt(userPrompt, { expandPromptTemplates: false, source: "rpc" });
  await session.waitForIdle();
  return toConversationTurn(events);
} finally {
  unsubscribe();
  session.dispose();
}
```

**Task/event/receipt ownership to retain** (`kernel-host.mjs:250-262,293-310,321-339`): register durable control before execution; append lifecycle events before/after each Tool; write only checksums/receipt metadata to `SessionStore`; keep final private text process-ephemeral only when an existing trusted adapter needs it. Do not reintroduce `providerAdapter.generate()` + `SkillEngine.run()` as a second outer tool loop (current legacy branch is `kernel-host.mjs:263-313`).

```javascript
this.runtimeControl.register({ operation_id: `op:task:${actualTaskId}`, ... });
const startedEvent = this.#appendLifecycle("task_started", { ... });
this.#appendLifecycle("tool_started", { ..., causationId: startedEvent.event.event_id });
const result = await this.domainBridge.invoke(step.tool, params);
this.#appendLifecycle("tool_completed", { ..., causationId: startedEvent.event.event_id });
this.sessionStore.append(actualSessionId, { kind: "skill_receipt", ... },
  { receipt: { kind: "skill", task_id: actualTaskId, report_checksum: reportChecksum } });
```

**Preserve user edit (non-negotiable):** `kernel-host.mjs:511-514` currently intentionally leaves `providerMode` undefined unless supplied through options/environment. Do not overwrite it with the former implicit `"replay"` default. Add the conversation branch around it and regression-test the non-default provider mode before changing execution paths.

---

### Kernel HTTP, event, and metadata boundary: `server.mjs`, `domain-bridge.mjs`, `capability-registry.mjs`, `conversation-turn.test.mjs`

**Route/error analog:** `apps/personal_intelligence_kernel/src/server.mjs:91-130,177-290`.

```javascript
function sendSafeError(response, statusCode, code) {
  sendJson(response, statusCode, { ok: false, error: { code } });
}

const body = await readBoundedJson(request);
const result = await host.executeTask(body);
sendJson(response, result.duplicate ? 200 : 201, { ok: true, ...result });
```

Add a named `POST /v1/conversations/turn` (or equivalent) route with the same bounded JSON parser, safe-code envelope, explicit route allowlist, loopback/internal capability checks, idempotency, and `Cache-Control: no-store`. Do not let Electron call a generic `/v1/tasks` with `include_response`; its preload/main contract should call only this purpose-built sanitized route.

**Registry integrity analog:** `capability-registry.mjs:21-28,33-57`. Any manifest addition must be canonicalized/checksummed as the current entries are, then filter to active operations by profile. The desktop Conversation profile is a narrower runtime lease, not a new way around the production registry.

**Metadata-only invariant:** `sessions/store.mjs:14-18` rejects keys matching `body|content|prompt|completion|credential|secret`, then adds `metadata_only: true`; all new Task/Session/Event/Candidate response projections must respect the same exclusion.

**Test skeleton:** copy `test/kernel-workflow.test.mjs:1-33,35-102`: temporary directory + accepted decision fixture + loopback server + JSON helper + `t.after` cleanup. Extend with a deterministic Pi runtime stub and assertions that `prompt`, Tool result, `agent_settled`, idle, receipt count, cancellation, and `outcome_unknown` reconciliation happen; retain the existing no-private-prompt checks at lines 55-65 and 82-101.

---

### Read-only evidence and dual freshness: `evidence_sqlite_tool.py`, `harness_freshness.py`, `harness_conversation_service.py`, `pi_domain_gateway.py`

**Read-only source analog:** `src/personal_knowledge/adapters/agentsview.py:132-194`.

```python
def _connect_read_only(path: Path) -> sqlite3.Connection:
    con = sqlite3.connect(_read_only_uri(path), uri=True)
    con.execute("PRAGMA query_only=ON")
    return con

def probe_source(source_db: Path = AGENTSVIEW_DB) -> SourceProbe:
    con = _connect_read_only(source_db)
    try:
        integrity = con.execute("PRAGMA integrity_check").fetchone()[0]
        ... # schema/table/column gate and bounded metadata only
    finally:
        con.close()
```

`EvidenceSqliteTool` must follow this connection/close shape but accept a descriptor ID and typed parameters, never SQL or paths. Compile only allowlisted templates/views/columns, use bound values, force RO/query-only, one statement, and return `database_id`, source/schema/snapshot binding, both freshness legs, statement checksum, row/byte/duration limits, truncation/status and receipt ID. Fail closed before executing for mutation/CTE write, `ATTACH`, extensions, unsafe PRAGMA, unapproved scope, multiple statements, or invalid/oversized arguments. Fingerprint authority DBs/active pointers before and after every success/rejection/timeout test.

**Gateway guard pattern:** `src/personal_knowledge/services/pi_domain_gateway.py:90-158`.

```python
if spec is None:
    raise PiDomainGatewayError("unknown_operation")
if capability is None or not hmac.compare_digest(str(capability), str(self.capability)):
    raise PiDomainGatewayError("capability_invalid")
if not isinstance(params, Mapping) or set(params) - spec["allowed"]:
    raise PiDomainGatewayError("undeclared_input")
if not params.get("idempotency_key") or not params.get("binding"):
    raise PiDomainGatewayError("binding_required")
```

Register `evidence.sqlite_query` explicitly in the Python operation map and the governed capability manifest; dependency-inject its authority Tool rather than dynamically importing/calling a name. Preserve `_ok`/`_error` envelopes (`pi_domain_gateway.py:68-72`) and safe-code whitelist (`152-158`). Review actions must remain routed only to `GuardedOrchestrationInterface` (`143-147`), not to Electron/Pi.

**Freshness model:** derive two typed legs, not a scalar: AgentView source probe/snapshot identity and AgentView-to-canonical watermark/backlog. `SourceProbe` already carries integrity/schema/count metadata without message bodies (`agentsview.py:79-106`); model unknown/stale explicitly and bind it into every evidence receipt/view model. A good `harness_conversation_service.py` analog is the gateway's typed/sanitized read response, not direct `sqlite3` access from Node.

**Tests:** use `tests/integration/test_agentsview_source_adapter.py:32-149`: create a temporary SQLite fixture, make a baseline fingerprint/mtime, test valid read, then prove source remains unchanged. Use its schema-gate failure form at `155-165` for denied descriptor/scope cases. Copy gateway contract assertions at `tests/contract/test_pi_domain_gateway.py:15-38` for unknown operation, extra parameter, invalid capability, missing binding, and metadata-only success.

---

### Deterministic reflection, review, and projection: `harness_reflection.py`, `state_projection.py`, review route/view model, reflection/projection tests`

**Idempotent event analog:** `apps/personal_intelligence_kernel/src/events/journal.mjs:142-172` derives a stable idempotency identity, returns a duplicate on exact replay, and raises only for conflicting repeat input. `harness_reflection.py` should form one stable key from canonical `event_id + source_snapshot_checksum + rule_version`, check/store it before model work, stage Evidence/Observation/Candidate metadata, and emit a candidate-staged event. Never allow model self-wakeups; inputs are deterministic delta events only.

**Candidate/projection validation analog:** `src/personal_knowledge/intelligence/state_projection.py:71-136,139-215,445-566`.

```python
_reject_private_payload(raw, f"candidate[{ordinal}]")
if str(_required(raw, "snapshot_id")) != snapshot.snapshot_id:
    raise ProjectionError("mixed_snapshot", str(ordinal))
if not 0.0 <= confidence <= 1.0:
    raise ProjectionError("invalid_confidence", str(confidence))
evidence=_normalize_evidence(raw.get("evidence"), snapshot=snapshot)
```

```python
if explicit_conflicts:
    status = "conflict"
    uncertainty.append("unresolved_conflict")
elif active:
    selected = active[-1][1]
    ... # simultaneous contradiction is not silently selected
```

Accepted material is **derived projection**, not raw Evidence or canonical fact. Preserve provenance class, valid interval, observed time, confidence, uncertainty, supporting/conflicting evidence, snapshot binding and supersession/formation history. Ignore/edit/accept must append feedback/receipt history and require expected version + explicit confirmation. No Candidate acceptance can call promotion/rollback directly.

**Tests:** use `tests/unit/test_personal_state_projection.py:36-110` for deterministic fixture builders and fail-closed time/evidence/private-body/secret checks; use `170-269` to assert replay determinism, explicit unknown/uncertain, and unresolved conflict. Use `tests/integration/test_analysis_candidates.py:61-101,114-150` for exact evidence binding and confirmation-before-generation failure cases.

---

### Electron shell and conversation renderer: `apps/personal_intelligence_desktop/**`

**No code analog found.** `rg --files apps | rg -i 'electron|preload|desktop'` returned no existing Electron/preload/desktop module. The React Cockpit exists but is explicitly not the visual or authority base; do not copy its permanent dashboard IA or give it Electron privileges.

Use the Phase 61 research/UI-SPEC contract for the new implementation:

```javascript
// preload shape from 61-RESEARCH.md; one named method per action only.
contextBridge.exposeInMainWorld("harness", {
  sendTurn: (value) => ipcRenderer.invoke("harness:conversation-turn", parseConversationInput(value)),
  reviewCandidate: (value) => ipcRenderer.invoke("harness:candidate-review", parseCandidateAction(value)),
  getLastConversation: () => ipcRenderer.invoke("harness:last-conversation"),
});
```

Required invariants for `main.mjs`/`preload.mjs`: `nodeIntegration:false`, `contextIsolation:true`, `sandbox:true`, restrictive local-only CSP, deny navigation/new windows/permissions, validate IPC sender plus schema in main, and never export raw `ipcRenderer`, endpoint URLs, filesystem/process handles, body/prompt/completion, credentials, or unredacted SQL. Main is the only local supervisor/loopback client; renderer receives safe view models and invokes fixed action names.

For `main-preload.test.mjs`, reuse Node built-in test imports/assertions and temporary fixture setup from `kernel-workflow.test.mjs:1-48`. Make pure schema/main-handler functions injectable so tests can prove every negative: untrusted sender, unknown channel/action, endpoint/path override, unsafe BrowserWindow config, navigation/new-window request, raw IPC exposure, unsafe errors, and secret/body leakage.

Renderer invariants from the approved UI contract: conversation opens at last conversation or declared empty state; answer exposes compact `依据`/`新鲜度`/`限制`; Tool receipt and SQLite card are collapsed/sanitized; Candidate card always says it is AI-generated and not fact; accept requires a confirmation modal; ignore is append-only and undoable; cancel and `outcome_unknown` are never styled as success. The renderer must use keyboard/focus/`aria-live`/reduced-motion behaviour specified by `61-UI-SPEC.md`.

## Shared Patterns

### Capability lease and receipts

**Sources:** `governance/manifests/ai/pi-skills.json:10-11`; `governance/manifests/capabilities/project-capabilities.json:7-11`; `domain-bridge.mjs:63-71`; `pi_domain_gateway.py:90-104`.

Apply to every Pi-invoked tool. The initial conversation slice uses existing `knowledge.research` only: five R1, side-effect-free tools with receipt requirements and 30-second ceiling. Derive a checksum-bound exact lease; reject out-of-lease operations in the Kernel bridge and again at Python gateway. Do not make the 44-operation production set ambient to a conversation session.

### Safe persistence and response shaping

**Sources:** `kernel-host.mjs:102-105`; `sessions/store.mjs:15-18`; `server.mjs:91-103`; `pi_domain_gateway.py:68-72`.

All durable stores receive identifiers, checksums, statuses, freshness/version binding and receipt references only. Public boundaries return `{ ok, status/error.code, data }`-style safe envelopes with `no-store`; raw private bodies live only ephemerally where an existing trusted parser requires them.

### Evidence and personal-model truthfulness

**Sources:** `agentsview.py:132-194`; `state_projection.py:71-136,139-215,445-566`.

All evidence access is read-only, schema-gated, bounded and source-identified. Every answer/projection shows source-to-AgentView plus AgentView-to-canonical freshness/backlog separately. Evidence, Observation, Candidate, Canonical, Projection, Outcome and Calibration remain distinct layers. A generated Candidate cannot become raw fact merely through Agent agreement or UI acknowledgement.

### Event/recovery semantics

**Sources:** `events/journal.mjs:142-172`; `kernel-workflow.test.mjs:105-143`.

Use deterministic idempotency identities; exact retry returns duplicate and divergent repeat fails. Cancellation and reconciliation retain versioned task truth; `outcome_unknown` requires reconcile and is never reported as success.

## No Analog Found

| File/group | Role | Data Flow | Reason / planner action |
|---|---|---|---|
| `apps/personal_intelligence_desktop/src/main.mjs` secure Electron lifecycle | controller | request-response | No Electron exists. Use 61-RESEARCH/UI-SPEC and add pure guards first for Node tests. |
| `apps/personal_intelligence_desktop/src/preload.mjs` | provider | request-response | No preload/contextBridge precedent. Keep its exported surface named and schema-validated. |
| `apps/personal_intelligence_desktop/src/renderer/{index.html,app.mjs,styles.css}` | component | event-driven | Cockpit visual/dashboard patterns are explicitly out of scope. Implement only approved conversation-first contract. |

## Metadata

**Analog search scope:** `apps/personal_intelligence_kernel/src`, `apps/personal_intelligence_kernel/test`, `src/personal_knowledge/{adapters,application,services,intelligence}`, `tests/{unit,integration,contract}`, `governance/manifests`, `apps/personal_decision_cockpit`  
**Strong analogs read:** 12 source/test modules plus the installed Pi AgentSession declarations  
**Files scanned:** 90+ relevant paths returned by targeted `rg --files`/symbol searches  
**Pattern extraction date:** 2026-08-09  
**Worktree preservation note:** Existing user changes include `apps/personal_intelligence_kernel/src/kernel-host.mjs` provider-mode behaviour. This file is a modify-in-place target; retain and reconcile its diff, never replace/revert it.
