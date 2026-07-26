# Phase 37: Authority-aware State, External and Evidence - Context

**Gathered:** 2026-07-22  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 37 makes the Cockpit's read-side trustworthy and usable: Overview, Personal State, External Context, Evidence and their degraded states render from the secured Projection contract. It explains what is current, historical, uncertain, partial or external, and lets users find stable evidence from current objects.

It adds no new decision write surface, no Wiki materialization, no external-source expansion and no authority mutation.
</domain>

<decisions>
## Implementation Decisions

### Truth labels and authority separation
- **D-37-01:** Every state item visibly identifies its kind: Fact, Observation, Inference, Forecast, Recommendation, Confirmation, Conflict, Historical or External. Color reinforces text and icon; it does not establish truth.
- **D-37-02:** External Context remains physically and semantically separate from Personal State. Source, region, validity window, lifecycle, conflict and freshness are displayed; no External fact can become a Personal fact through the UI.
- **D-37-03:** Empty, partial, stale, offline and conflict are separate user-visible states. The UI never presents stale cache, a missing authority or an empty iframe as a current successful result.

### Snapshot and evidence
- **D-37-04:** Actionable conclusions show authority identity, snapshot binding, freshness and evidence availability. Binding mismatch, stale, conflict, partial or insufficient evidence disables entry to Phase 38 prepare/confirm and directs the user to refresh/review.
- **D-37-05:** Evidence drill-down starts from stable IDs/checksums of the current state, external or decision object. The legacy Memory Graph remains an explicitly labelled diagnostic/historical surface, not Personal State SSOT.
- **D-37-06:** MCP Widget failure is a bounded integration failure: show a non-empty recovery panel and protect iframe embedding with explicit origin policy, sandbox/referrer policy and CSP constraints where supported.

### Information architecture
- **D-37-07:** Desktop navigation remains Overview, Personal State, Decisions, Actions, External, Proactive, Evidence and System. Decision/session routes remain subroutes; mobile reduces to Overview, Decisions, Actions, Proactive and More.

### the agent's Discretion

The planner may choose card, table and evidence-drawer composition so long as it preserves D-37-01..07 and STATE-01..03/EVID-01 without copying authority logic into the browser.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — STATE-01..03, EVID-01.
- `.planning/ROADMAP.md` — Phase 37 goal and criteria.
- `.planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-CONTEXT.md` — secured Projection/DTO prerequisite.
- `.planning/research/v1.4-decision-cockpit-ui/{FEATURES,ARCHITECTURE,PITFALLS}.md`.
- `.planning/research/v1.4-decision-cockpit-ui/UI-SPEC.md` — state, external, evidence and responsive visual semantics.
</canonical_refs>

<code_context>
## Existing Code Insights

- `apps/personal_decision_cockpit/src/app/router.tsx` and `AppShell.tsx` already contain the intended route/nav shape.
- `OverviewPage.tsx` has stale confirmation/priority key usage that Phase 36 DTO settlement must correct.
- `ExternalContextPage.tsx` expects fields that differ from `_external_delta_section` in `ui_projection.py`.
- `EvidencePage.tsx` currently embeds MCP Widgets but states that Authority wiring is future work; it needs current-object evidence links and degraded semantics.
- `ui_projection.py` returns partial/limitations/freshness metadata and source authority boundaries to preserve.
</code_context>

<deferred>
## Deferred Ideas

- Decision write/confirm UI (Phase 38).
- Action/outcome/calibration and proactive workflows (Phase 39).
- Topic Wiki pages, backlinks, entity materialization and Wiki search (v1.5).
</deferred>

---
*Phase: 37-authority-aware-state-external-and-evidence*  
*Context gathered: 2026-07-22*
