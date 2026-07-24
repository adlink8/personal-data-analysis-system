---
phase: 39
slug: feedback-proactive-and-runtime-truthfulness
date: 2026-07-22
requirements: [FDB-01, FDB-02, RUN-01]
research_mode: implementation
confidence: high
---

# Phase 39 Research: Feedback, Proactive and Runtime Truthfulness

## Research Question

How should the Cockpit present the already-authoritative feedback chain,
proactive intelligence, calibration and local runtime state so that users can
reconstruct what happened without mistaking correlation for causality, a
disabled control for an available API, or a reachable REST process for a
healthy end-to-end Agent stack?

## Scope and Non-goals

Phase 39 is a read-only, product-facing completion of the following existing
authorities:

```text
Decision authority
  Recommendation → Decision → Action → Outcome → Effectiveness
                                      ↓
                             Calibration authority

Proactive authority
  candidate → evaluation/coordination → control-history → inbox/digest

Runtime observations
  REST / MCP / Tunnel / Chroma / authority readable-and-freshness state
```

It depends on Phase 36's safe Projection/HTTP baseline and Phase 38's guarded
project-domain workflow.  It must not add a new write route, database table,
notification scheduler, control executor, external action, automatic
promotion, service-management command, fact authority, or browser cache.

The present Cockpit, Projection and Phase-39-oriented tests are **untracked
WIP candidates** in this worktree.  Their existence is useful implementation
evidence, but it is not proof that FDB-01, FDB-02 or RUN-01 has shipped.

## Existing Capability Map

| Concern | Existing reusable implementation | Preserved invariant | Gap Phase 39 must close |
|---|---|---|---|
| Decision feedback read | `DecisionFeedbackService` in `src/personal_knowledge/intelligence/decision/service.py` | All reads use `mode=ro`, `query_only`; history is checksum-chain based and typed records verify payload checksums | The Cockpit needs to render the chain honestly, including truncation/absence and non-causal limitations. |
| Feedback projection | `CockpitProjectionService._actions_recent_get()` and `_build_timeline()` in `src/personal_knowledge/services/ui_projection.py` | Six timeline stages are fixed and absent stages remain explicit `present=false` | `recommendations.list` is currently ascending and bounded before the projection selects its tail; an old window can be labelled “recent”.  Per-item errors currently leak raw exception text until Phase 36's safe-error policy is complete. |
| Action/result page | `ActionsPage.tsx`, `OutcomeTimeline.tsx`, `CalibrationPanel.tsx` | Visible `causal_claim=false` warning, fixed stage ordering and partial-state components already have an intended shape | The page must show the source limits/sample context for every outcome/effectiveness/calibration assertion and must not infer causal benefit from a positive verdict. |
| Calibration evidence | `intelligence/calibration/service.py:explain()` | Read-only checksum verification; it always returns `causal_claim=False`, `promotion_available=False`, `external_action_available=False` | The UI needs to preserve these exact fields and display `INCONCLUSIVE`, sample size and protocol limitations rather than a success score. |
| Proactive read | `ProactiveIntelligenceService` plus `/proactive/*` GET adapters | Inbox filters deterministic eligible candidates; `controls.status` is a read; metrics report zero external/network/paid actions | The UI must distinguish eligible, suppressed/cooldown and unavailable controls; it must not invent a REST write surface or hide the limitation. |
| Proactive page | `ProactivePage.tsx`, `ProactiveCard.tsx`, `api/proactive.ts` | Candidate detail/explain is on-demand and control buttons are currently disabled | `ImportanceLine` looks for `importance.score`, while the authoritative ranking field is `importance.final_score`.  A disabled button alone is insufficient if its status/recovery path is not explained in context. |
| System status | `_system_status_get()` in `ui_projection.py`; `SystemPage.tsx`; `SystemHealthStrip.tsx` | `get_knowledge_status(probe_chroma=True)` provides a true Chroma probe and serving-snapshot fields; authority DB access is read-only | `_ports_section()` currently treats the serving REST handler as `up=True` and uses TCP reachability for MCP/Tunnel.  That must not be rendered as full endpoint or stack readiness. |
| Supervisor observations | `ops/runtime/start-agent-stack.ps1` writes `ops/state/agent-stack.json` | Supervisor state contains a saved `updated_at`, PID, per-service health URL and last health result | It is a last-observed local record, not proof that the PID, endpoint, or Tunnel is still live.  It must be labelled as such and corroborated by a fresh safe probe when available. |

## Standard Stack

Use the repository's established local stack; Phase 39 needs no new framework
or production dependency.

| Layer | Use | Why |
|---|---|---|
| Web UI | React 18, TypeScript, React Router and Vite in `apps/personal_decision_cockpit/` | Existing Cockpit shell, semantic state panels and routes are the intended local product surface. |
| Client data state | TanStack Query 5 | Retains in-memory request/load/error state without persisting personal data in LocalStorage, IndexedDB or a service worker. |
| Client contract boundary | Zod 3 endpoint schemas in `src/api/schemas.ts` | Parses the versioned Projection envelope before rendering data. |
| Server aggregation | `CockpitProjectionService` | Is the only service allowed to aggregate existing authorities into `/ui/*`; pages must not query SQLite/Chroma or join authority records themselves. |
| Decision/feedback reads | `DecisionFeedbackService` | Already validates typed-record checksums and state-machine history. |
| Proactive reads | `ProactiveIntelligenceService` | Already exposes metadata-only inbox, candidate explain, control status and metrics without a REST mutation route. |
| Calibration reads | `DecisionIntelligenceReadService` + `calibration.service.explain` | Preserves frozen protocol, cohort, verdict and limitation semantics. |
| Runtime source | Direct read-only probes plus the supervisor's saved state file | Separates “observed now” from “last observed by supervisor”; no Cockpit process control is needed. |
| Verification | Pytest contract/integration tests; Vitest + Testing Library; Playwright only in Phase 40 UAT | Gives Python/TypeScript contract evidence now without misrepresenting a browser UAT as complete. |

## Architecture Patterns

### 1. Append-only timeline is a trace, not a success funnel

The primary product object is an immutable evidence trace, not a conversion
funnel.  Its fixed display stages must remain visible even when a stage was not
reached:

```text
recommendation
  → confirmation/decision
  → action started
  → action completed
  → observed outcome
  → non-causal effectiveness assessment
```

`_build_timeline()` already produces six stable stage objects with `present`,
`event_id`, `sequence` and `checksum`.  Keep that contract.  The UI may use
the stage order for navigation, but it must never synthesize a missing event,
infer a timestamp, or turn the presence of an assessment into evidence of
effectiveness.

Each displayed assessment needs the following literal semantics near the
verdict, not buried in an expandable raw record:

```text
causal_claim: false
sample/cohort: <reported count or unavailable>
limitations: <authority-provided reasons>
```

The calibration source already makes this explicit:

```python
# src/personal_knowledge/intelligence/calibration/service.py
"causal_claim": False,
"promotion_available": False,
"external_action_available": False,
```

The projection should carry these values through.  It must not derive
“personalized wins” or enable promotion from a PASS, and it must show
`INCONCLUSIVE` as a valid, useful result rather than an error that the UI
tries to conceal.

### 2. Read model is bounded, ordered and visibly incomplete

The current implementation reads recommendations ordered by `created_at`,
then takes a bounded list.  The projection later selects its tail.  When the
underlying list is longer than its limit, its `recent` label is not reliable:
newer rows may never be fetched.  Phase 39 must settle one correct strategy:

```text
authority query ordered newest-first with a stable ID tie-breaker
  → bounded Projection window
  → explicit total_available / shown / “older records not shown” limitation
```

Alternatively, an authority-level cursor may be reused only if it already
preserves exact chronological semantics.  Do not filter, rank or re-order
history in the browser.  Every bounded section must expose both an exact
number where available and a clear lower-bound/truncation statement where it
is not.

Per-item failure isolation remains appropriate:

```text
one recommendation detail cannot be read
  → that item is partial/error
  → other recommendations remain readable
  → the envelope remains truthful about the affected limitation
```

After Phase 36, this error state must use a safe public code/message rather
than `str(exc)` or database details.

### 3. Proactive display is an inbox, not an automation surface

The proactive authority already separates candidate eligibility from user
control projection:

```text
inbox.list
  → only deterministic eligible candidates
controls.status(candidate_id, as_of)
  → actual control eligibility/reason codes/history
metrics.get
  → metadata-only counters; external_actions/network_calls/paid_calls = 0
```

The Cockpit should therefore render three distinct concepts:

| UI concept | Authority source | Required wording |
|---|---|---|
| Candidate priority | `importance.final_score`, policy threshold, reason codes | “Current ranking result”, never a user fact or model certainty. |
| Current control state | `controls.status` / `current_control_*` | “Eligible / suppressed / cooldown / unavailable”, with reasons and an as-of time. |
| Available browser action | actual guarded REST route only | “Available through this Cockpit” or “Not available in REST; use MCP/CLI”, never an optimistic fake button. |

`Snooze`, `Suppress`, `限定 Scope` and `Restore` can be present as disabled
explanations while REST lacks their guarded mutation surface, but they must
not trigger a client-side state mutation, claim success, or hide the
alternative MCP/CLI recovery path.  “Create Decision Case” may navigate to
the existing guarded workflow; it does not itself create a record.

No automatic notification sender, scheduler or “mark as presented” read-side
write belongs in this phase.  Reading an inbox remains side-effect free.

### 4. Runtime status is an observation matrix, not one green badge

The system page needs independent rows, observation timestamps and semantic
labels:

```text
REST serving this page     | current endpoint response, observed now
MCP endpoint              | endpoint-specific health/readiness if reachable
Tunnel readiness           | /readyz when configured/reachable
Chroma retrieval backing   | actual probe_chroma result, not REST success
Authority databases        | exists/readable only, not “fresh/current”
Authority freshness        | exact snapshot/as-of/generated time per authority when available
Supervisor saved state     | last observed at <updated_at>; may be stale
```

TCP connection success alone means only “a listener accepted a connection”.
It does not prove that the listener is the expected MCP/Tunnel service or that
it is ready.  Conversely, the current Handler can truthfully label itself as
“this REST request succeeded”; it must not use that fact to label Chroma,
MCP, Tunnel, authorities or the entire Agent stack healthy.

Use an explicit finite vocabulary in the Projection and Zod DTO:

```text
healthy | reachable_only | unavailable | stale_observation |
unknown | partial
```

Each value must include `observed_at`, `source` and a safe recovery hint.  A
missing/stale `ops/state/agent-stack.json` should be rendered as a stale saved
observation, not as a current failure or current success.  The Cockpit never
offers start, stop, restart, kill, tunnel reconfiguration or supervisor
controls.

### 5. One safe display envelope, independent section degradation

Continue using the common Cockpit envelope:

```text
decision_cockpit_projection_v1
{ generated_at, snapshot_bindings, freshness, authorities,
  partial, limitations, data }
```

Phase 39 should add only typed, server-owned read fields required for the
feedback/proactive/runtime views.  It must not introduce a second “dashboard
state” contract in React.  A section failure becomes explicit `partial` plus
an authority/status limitation; an empty authority is not silently converted
to a healthy zero.

## Recommended Implementation Order

### Plan 39-01 — Make feedback chronology and non-causal context exact

1. Write contract tests that demonstrate newest-first, stable, bounded
   recommendation retrieval or an equivalent cursor-based result.
2. Keep the six-stage timeline and append-only event/checksum fields, but
   extend its read projection only with source-provided result/effectiveness
   fields and explicit history-window limitations.
3. Ensure outcome/effectiveness cards render `causal_claim=false`, absence,
   and authority limitations in a predictable, accessible form.
4. Do not add a direct “record outcome” mutation.  Any existing link only
   enters the Phase-38 guarded session flow.

### Plan 39-02 — Surface proactive and calibration truth without fake controls

1. Make TypeScript schemas and page components consume
   `importance.final_score`, `current_control_eligible`, current control reason
   codes and stable candidate IDs rather than display-only aliases.
2. Keep candidate details/explanations as on-demand read calls; show failure,
   unavailable and empty states separately.
3. Display frozen protocol status, verdict, `causal_claim=false`, sample size,
   inconclusive reason codes, source limitations, no-promotion and no-external-
   action state for calibration.
4. Add static/contract tests that `/proactive/*` stays GET-only and Cockpit
   code has no client mutation for controls, promotion or external actions.

### Plan 39-03 — Replace aggregate health with provenance-aware runtime observations

1. Define a small server-side runtime observation DTO and its Zod counterpart.
2. Classify current REST, endpoint-specific MCP/Tunnel readiness, Chroma
   probe, database readability and authority freshness independently.
3. Read the supervisor state file only as a bounded, validated `last_observed`
   record.  It must not be relied upon for current process ownership.
4. Update System page text, badges and recovery copy so it never exposes
   filesystem paths, PIDs/complete IDs by default, raw connection errors or
   service-management controls.

### Plan 39-04 — Lock the read-only boundary and degraded behavior

1. Add Python and TypeScript regression tests for partial sections, safe error
   mapping, missing state file, stale saved state, port-listener-but-not-ready,
   Chroma-unavailable and one-authority-unreadable cases.
2. Confirm every Phase-39 browser endpoint is a read and that neither page
   changes snapshots, lifecycle, calibration policy or control history.
3. Record focused test/build evidence only after the plans are executed;
   Phase 40 remains responsible for actual browser UAT, responsive and
   accessibility acceptance.

## Concrete Code Integration Points

| File / symbol | Phase 39 change boundary |
|---|---|
| `src/personal_knowledge/intelligence/decision/service.py:recommendations_list` | Correct/reuse a stable latest-first bounded read strategy.  Retain `mode=ro`, checksum validation and state-machine source of truth. |
| `src/personal_knowledge/services/ui_projection.py:_actions_recent_get`, `_actions_recent_section`, `_build_timeline` | Project the honest six-stage trace, bounded-history limitations and safe per-item degradation.  Do not generate events or infer outcomes. |
| `ui_projection.py:_proactive_summary_get`, `_proactive_inbox_section`, `_proactive_metrics_section` | Use only `ProactiveIntelligenceService` read operations and authoritative `importance.final_score`/control metadata. |
| `ui_projection.py:_calibration_overview_get`, `_calibration_summary` | Preserve exact frozen/verdict/causal/sample/limitation semantics from `calibration.explain`; never compute a new success or promotion signal. |
| `ui_projection.py:_system_status_get`, `_ports_section`, `_knowledge_status_section`, `_authority_dbs_section` | Replace conflated port booleans with independently observable status/provenance.  Reuse `probe_chroma=True`; treat supervisor JSON as last-observed-only. |
| `ops/runtime/start-agent-stack.ps1:Save-State` and `Show-ManagedStatus` | Source schema reference only.  Do not invoke, modify, start or stop this script from the Cockpit. |
| `apps/personal_decision_cockpit/src/api/schemas.ts` | Add strict DTOs for feedback/proactive/calibration/runtime observations; preserve safe unknown-field tolerance only where the server contract permits it. |
| `apps/personal_decision_cockpit/src/pages/actions/ActionsPage.tsx` and `components/action/{OutcomeTimeline,CalibrationPanel}.tsx` | Render the append-only trace, non-causal warnings, truncation, empty and per-item partial states; no direct write. |
| `apps/personal_decision_cockpit/src/pages/proactive/ProactivePage.tsx` and `components/proactive/ProactiveCard.tsx` | Use `final_score`, as-of control status and explicit disabled/recovery language.  Do not add POST/fetch mutation code. |
| `apps/personal_decision_cockpit/src/pages/system/SystemPage.tsx` and `components/system/SystemHealthStrip.tsx` | Render independent, timestamped observations; keep advanced identifiers hidden by default and do not add operational buttons. |
| `tests/contract/test_ui_projection_actions_proactive.py` | Extend Python projection/REST parity, safe degradation, chronology and runtime truthfulness cases. |
| `apps/personal_decision_cockpit/src/test/{ActionsPage,ProactivePage}.test.tsx` | Extend UI semantic tests for causal labels, final-score vocabulary, disabled control explanation, partial/inconclusive and runtime states. |

## Code Examples

### Safe runtime observation (server-owned pseudocode)

```python
# ui_projection.py — shape, not a new health authority
def _observation(*, state: str, source: str, observed_at: str, hint: str) -> dict[str, str]:
    return {
        "state": state,                 # healthy/reachable_only/unavailable/stale_observation/unknown
        "source": source,               # fresh_endpoint_probe or supervisor_saved_state
        "observed_at": observed_at,
        "recovery_hint": hint,
    }

# A current /health response proves this REST request succeeded only.
# Chroma must remain a separate get_knowledge_status(probe_chroma=True) observation.
```

### Explicit non-causal result card (client pattern)

```tsx
{record.causal_claim === false && (
  <StatePanel
    variant="partial"
    title="非因果评估"
    description="该结果与建议同时出现，不证明建议导致了结果。"
  />
)}
<p>样本/队列：{record.sample_size ?? '未提供'}</p>
<Limitations items={record.limitations ?? []} />
```

The real DTO must preserve the source's fields rather than fabricate
`sample_size` where a decision outcome authority does not provide one.

### Honest unavailable proactive control

```tsx
<button disabled title="该操作没有受控 REST 写入路径">
  Suppress
</button>
<p>
  此 Cockpit 只能读取控制状态；如需操作，请使用已授权的 MCP/CLI，
  并遵循其显式确认流程。
</p>
```

This remains a display of the existing boundary.  It must not update React
Query data optimistically or create a synthetic “success” toast.

## Don't Hand-Roll

| Do not build | Why | Reuse instead |
|---|---|---|
| A browser event ledger or timeline state machine | Would create a second mutable record of the decision chain | `DecisionFeedbackService`, state-machine history and Projection. |
| Client-side causal score, success rate or personalized-win calculation | Would overstate incomplete cohorts and duplicate calibration rules | Calibration authority's frozen verdict, `causal_claim`, cohort and limitations. |
| A new REST POST route for Proactive controls | Bypasses existing local explicit-write/append-only control requirements | Existing read-only REST and guarded MCP/CLI control interfaces. |
| Browser polling that writes “presented”, snoozed or acknowledged state | Makes reading stateful and creates hidden behavior | Read-only inbox/metrics; explicit existing control path only. |
| A process manager, PID killer, restart button or tunnel configurator | Crosses from truthful observability into operational control | `ops/runtime/start-agent-stack.ps1` remains the operator-owned surface. |
| A global all-green Agent status | REST, MCP, Tunnel, Chroma and each authority fail independently | Per-observation state/source/time/recovery DTO. |
| LocalStorage/IndexedDB/service-worker cache of feedback or runtime data | Creates privacy and stale-state risks with no expiry/revocation design | In-memory TanStack Query plus explicit partial/offline state. |

## Common Pitfalls

| Pitfall | Why it is incorrect | Required prevention |
|---|---|---|
| Calling an ascending, truncated list “recent” | New decisions can be outside the fetched window | Stable latest-first/cursor contract plus total/shown limitation. |
| Rendering all green timeline nodes as successful advice | Node presence proves an event, not the quality or cause of its result | Keep `causal_claim=false`, outcome uncertainty and limitations visible. |
| Hiding `INCONCLUSIVE` under a neutral badge | Makes lack of proof look like a quiet success | Amber/uncertain semantic text with reason codes and sample/limitations. |
| Treating `importance.score` as authoritative | The service emits `importance.final_score`; a UI alias silently misranks candidates | Bind schema/component to actual field and fixture-test it. |
| Optimistically toggling a disabled Proactive control | Creates a fake local state that never entered append-only control history | No mutation client; disabled explanation and alternate authorized path only. |
| Calling any TCP listener a healthy MCP/Tunnel | A different listener can own the port and readiness may be false | Probe endpoint-specific health/readiness when available; otherwise say `reachable_only`/`unknown`. |
| Trusting `agent-stack.json` as current runtime truth | It records a past supervisor observation and PIDs may be stale/reused | Show saved timestamp/source and corroborate with fresh probes; no process action. |
| Treating authority DB `readable=true` as current/fresh | A readable file can be stale, mixed-version or not the active snapshot | Separate readability from snapshot binding and freshness/as-of. |
| Letting raw exceptions appear in status cards | Paths, provider bodies or sensitive records can leak | Depend on Phase 36's safe limitation/error mapper; fault-inject poison strings. |
| Declaring WIP pages complete because tests exist | Current Cockpit/Projection files are untracked | Commit/audit/verification evidence is required at phase execution, not planning. |

## Testing Strategy

### Python unit and contract gates

- Verify the decision list's ordering/bounds with timestamps and ID ties;
  prove the item labelled recent is actually in the returned latest window.
- Assert `_build_timeline()` always returns six stages and never synthesizes an
  absent event; verify checksums/sequences are copied from the authority only.
- Create outcome/effectiveness/calibration fixtures for no outcome,
  `causal_claim=false`, `PASS`, `FAIL`, `INCONCLUSIVE`, zero/unknown sample,
  truncated history and per-item read failure.
- Fault-inject a decision, proactive, calibration, Chroma, supervisor-file and
  authority read failure.  The correct envelope must be `partial` or a clearly
  scoped unavailable state; unaffected sections remain usable.
- Assert `proactive_rest_contract` exposes only current GET reads and Phase-39
  UI projection calls produce zero writes, zero external actions, zero provider
  invocations and zero calibration promotions.
- Stub a listener which accepts TCP but does not return the expected MCP/Tunnel
  readiness response.  Its state must not be `healthy`.
- Test absent, corrupt and old supervisor state files as safe
  `unknown`/`stale_observation`, never current health.

### Frontend semantic gates

- Test the Actions page's fixed stage order, textual non-causal warning,
  incomplete-trace explanation, limits and per-item partial render.
- Test the Proactive card renders `importance.final_score`, reason codes and
  as-of control state; every unavailable control remains disabled and has an
  explanatory recovery path.
- Test calibration cards expose `INCONCLUSIVE`, sample context and source
  limitations; a `PASS` never presents an automatic-promotion action.
- Test System page shows separate REST/MCP/Tunnel/Chroma/authority statuses,
  observation time and source; it contains no start/stop/restart button.
- Assert all browser calls remain GET except the Phase-38 guarded session
  workflow.  Phase-39 pages themselves must not issue a POST.

### Focused future verification commands

Run these only when Phase 39 is implemented; their successful result must be
recorded in the later verification artifact rather than asserted today:

```powershell
Set-Location D:\ADLINK\数据分析
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/contract/test_ui_projection_actions_proactive.py tests/contract/test_ui_projection.py tests/contract/test_proactive_interfaces.py tests/contract/test_proactive_boundaries.py tests/contract/test_decision_interfaces.py tests/unit/test_decision_effectiveness.py -q

Set-Location D:\ADLINK\数据分析\apps\personal_decision_cockpit
npm run test -- --run src/test/ActionsPage.test.tsx src/test/ProactivePage.test.tsx src/test/appSmoke.test.tsx
npm run build
```

Phase 40, not Phase 39 research, owns real-browser responsive, keyboard,
offline/degraded and end-to-end UAT acceptance.

## P0 Risks and Mitigations

| Risk | Repository evidence | Required mitigation | Acceptance evidence |
|---|---|---|---|
| An old bounded list is labelled recent | `recommendations_list` orders ascending and `actions_recent` observes a limited window | Stable descending/cursor read plus honest bound note | Fixture with more rows than limit shows actual newest records and explicit truncation. |
| A positive effect is presented as causation | `calibration.service.explain()` explicitly says `causal_claim=False`; current actions have only metadata records | Required causal/sample/limitation display adjacent to verdict | UI/contract snapshots prove warnings survive PASS, FAIL and INCONCLUSIVE. |
| Proactive UI pretends a control executed | REST has only proactive GET routes; existing controls are local guarded/MCP/CLI domain | No client mutation or optimistic state; disabled explanation | Static route/client tests and no-write fingerprint test. |
| Ranking UI reads wrong field | `ProactiveCard.tsx` uses `importance.score`; service uses `final_score` | Match DTO/component to actual field | Typed fixture renders a final score and no fallback misclassification. |
| “All systems healthy” masks a downstream failure | REST handler, TCP port probes and Chroma probe have different meanings | Independent observation matrix with source/time/state | Chroma-down/MCP-listener-only/saved-state-stale tests. |
| Saved supervisor state is stale or sensitive | `agent-stack.json` includes PIDs and health URLs from a prior supervisor run | Treat as last observation; redact advanced operational details by default | Missing/stale file cannot yield healthy status; default UI avoids PID/full endpoint disclosure. |
| WIP becomes a false release claim | Cockpit/Projection/tests are currently untracked | Track only scoped files during execution; later verification records real commands | Roadmap status changes only after Phase 39 verification. |

## Prohibited Outcomes

- Do not make `Outcome`, `Effectiveness`, `Calibration`, `PASS` or any chart
  imply a causal claim, automatic promotion, or a personalized strategy win.
- Do not create a REST write, direct browser write or optimistic local mutation
  for Proactive controls, calibration, lifecycle, snapshot or authority data.
- Do not add an automated notification, scheduler, provider call, external
  action, service start/stop/restart or runtime supervisor command.
- Do not call a port listener or stale supervisor file “healthy” without the
  correct source and observation time.
- Do not expose PIDs, raw endpoint URLs, filesystem paths, raw provider bodies,
  confirmation/HMAC material, PII or unguarded exception text in normal UI.
- Do not silently turn empty, stale, partial or unknown records into zeros that
  look current and successful.
- Do not add Personal Wiki materialization, topic pages, backlinks or LLM Wiki
  narratives; those remain explicit v1.5 work.

## Planning Recommendation

Plan Phase 39 as four narrow plans in this dependency order:

1. **Feedback integrity and chronology:** latest-window contract, six-stage
   trace and non-causal/limitation presentation.
2. **Proactive and calibration truth:** real ranking vocabulary, control-status
   explanation, frozen non-promoting calibration display and no-write proof.
3. **Runtime observation matrix:** independent current probes, saved-state
   staleness, authority freshness/readability and safe recovery text.
4. **Degraded/read-only verification:** fault injection and Python/TypeScript
   contracts that prove display cannot mutate an authority.

Keep all plans read-only except for normal source/test/document changes made
when implementation is explicitly authorized.  The Phase 39 plan must name
the dependency on Phase 36's safe error policy and Phase 38's exact guarded
workflow rather than reimplement either one.

## Sources

### Primary repository evidence

- `.planning/REQUIREMENTS.md` — FDB-01, FDB-02 and RUN-01.
- `.planning/ROADMAP.md` — Phase 39 goal, ordering and success criteria.
- `.planning/phases/PDA-39-feedback-proactive-and-runtime-truthfulness/39-CONTEXT.md` — locked phase decisions D-39-01 through D-39-07.
- `.planning/phases/PDA-26-decision-action-feedback-loop-separate-facts-observations-in/26-RESEARCH.md` and `26-VERIFICATION.md` — append-only decision/action/outcome boundary.
- `.planning/phases/PDA-27-proactive-multi-domain-intelligence-and-target-d-acceptance-/27-RESEARCH.md` and `27-VERIFICATION.md` — read-only REST/MCP, explicit local controls and zero-external-action boundary.
- `src/personal_knowledge/intelligence/decision/service.py` — checksum-verifying feedback reads and current ordering.
- `src/personal_knowledge/intelligence/calibration/service.py` — non-causal calibration view and promotion/external-action flags.
- `src/personal_knowledge/intelligence/proactive/service.py` — inbox, candidate, control-status and metric semantics.
- `src/personal_knowledge/services/ui_projection.py` — current feedback, proactive, calibration and system Projection candidates.
- `src/personal_knowledge/services/api_server.py` — existing GET-only proactive/UI routes and guarded session POST boundary.
- `ops/runtime/start-agent-stack.ps1` and `ops/state/agent-stack.json` — supervisor last-observed runtime-state schema.
- `apps/personal_decision_cockpit/src/pages/{actions,proactive,system}/` and `src/components/{action,proactive,system}/` — current WIP display candidates.
- `tests/contract/test_ui_projection_actions_proactive.py`, `tests/contract/test_proactive_interfaces.py`, `tests/contract/test_proactive_boundaries.py`, and Cockpit Vitest files — existing contract baseline.

## Confidence

**HIGH.**  The authority boundaries, data fields, route set, runtime supervisor
format, WIP status and test locations are all directly evidenced in the
repository.  The exact status vocabulary and whether the supervised MCP/Tunnel
health endpoints can be safely probed from the REST process are implementation
choices that the Phase 39 planner must lock down with deterministic tests.
