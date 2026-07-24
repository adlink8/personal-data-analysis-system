# Phase 38: Guarded Decision Workspace - Context

**Gathered:** 2026-07-22  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 38 exposes the existing low-risk project decision session as an honest browser workflow. Users can inspect a decision case, compare options and explicitly advance only through the server-owned prepare, exact preview, confirm and replay path.

It does not grant the browser new authority, persist identity hash, add automatic provider retry, add high-risk domains, perform external actions or rewrite recommendation/state evidence.
</domain>

<decisions>
## Implementation Decisions

### Decision explanation
- **D-38-01:** The workspace compares the decision question, goals, hard constraints, risk budget, options, no-action baseline, costs, opportunity cost, assumptions, counter-evidence, stop conditions, missing information and limitations. It never substitutes a single opaque life score.
- **D-38-02:** Recommendation is a candidate, not a fact or user decision. Its supporting Personal/External snapshot and evidence state must remain visible until the user leaves the session.

### Guarded write boundary
- **D-38-03:** Only the existing `project + low` path is exposed. The complete browser path is `prepare → exact preview → explicit confirm → commit/replay`; every write has an operation-specific confirmation label.
- **D-38-04:** Preview displays exact new events, explicitly excluded actions, checksum, expected sequence and idempotency key. A changed/expired preview cannot be confirmed; the UI asks for a new prepare.
- **D-38-05:** Repeated same-payload confirmation displays the server's original event and `replayed=true`; a payload/sequence/binding change is a typed conflict, not a client retry.
- **D-38-06:** Actor identity hash remains volatile. After refresh, a session can be inspected/resumed read-only but cannot be falsely presented as writable.

### Failure and recovery
- **D-38-07:** Stale, integrity, confirmation, sequence, risk, runtime and provider-outcome-unknown paths show stable typed recovery. The client never auto-retries a provider-unknown call or substitutes a different payload.

### the agent's Discretion

The planner may select state-machine UI composition, form layout and receipt rendering provided it preserves D-38-01..07 and DEC-01..03.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — DEC-01..03.
- `.planning/ROADMAP.md` — Phase 38 goal and criteria.
- `.planning/phases/PDA-33-guarded-decision-orchestration/33-CONTEXT.md` and `33-VERIFICATION.md` — existing source-of-truth workflow.
- `.planning/phases/PDA-37-authority-aware-state-external-and-evidence/37-CONTEXT.md` — required snapshot/evidence UI semantics.
- `apps/personal_decision_cockpit/docs/write-flow.md` — current front-end/back-end contract.
</canonical_refs>

<code_context>
## Existing Code Insights

- `apps/personal_decision_cockpit/src/api/orchestration.ts` and `components/decision/ConfirmDrawer.tsx` already encode the candidate confirm flow.
- `src/personal_knowledge/intelligence/orchestration/service.py` owns project/low policy, HMAC confirmation, expected sequence, idempotency and exact replay.
- `src/personal_knowledge/services/api_server.py` forwards guarded session routes; Phase 36 must first make their transport same-origin safe.
- Existing v1.3 orchestration contract, replay and E2E tests provide regression assets; they must not be duplicated with UI-only logic.
</code_context>

<deferred>
## Deferred Ideas

- Non-project or non-low-risk decisions, health/finance/relationship workflows.
- Automatic confirmation, provider calls without confirmation, external actions or automatic strategy promotion.
- Action/outcome history pages beyond the existing authority reads (Phase 39).
</deferred>

---
*Phase: 38-guarded-decision-workspace*  
*Context gathered: 2026-07-22*
