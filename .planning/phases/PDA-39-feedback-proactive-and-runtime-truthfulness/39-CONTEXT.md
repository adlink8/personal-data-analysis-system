# Phase 39: Feedback, Proactive and Runtime Truthfulness - Context

**Gathered:** 2026-07-22  
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 39 surfaces existing append-only decision feedback, proactive intelligence, calibration and runtime health as truthful, read-only product views. It helps a user see what was recommended, chosen, done and observed without converting correlation into causality or adding operational controls to the Cockpit.

It does not create recommendations, control Proactive state through new REST routes, alter calibration policy, start/stop services, automatically promote anything or create new external actions.
</domain>

<decisions>
## Implementation Decisions

### Feedback and causal boundary
- **D-39-01:** The product timeline is `Recommendation → Decision → Action → Outcome → Effectiveness → Calibration`, sourced from existing append-only authorities.
- **D-39-02:** Every Outcome/Effectiveness/Calibration view visibly retains `causal_claim=false`, cohort/sample information and limitations. One positive result cannot be rendered as a proven benefit or policy promotion.

### Proactive authority and user controls
- **D-39-03:** Proactive and Calibration pages show candidate, coordination, control-history and limitation data from existing read services.
- **D-39-04:** Snooze/Suppress/Restore and any other control without an exposed guarded REST write route are disabled with an explanation. The UI must never simulate a successful control or add a new mutation API for visual completeness.

### Runtime truthfulness
- **D-39-05:** System status reports REST, MCP, Tunnel, Chroma and authority freshness independently. A REST health result cannot be called an overall retrieval/Chroma health result.
- **D-39-06:** Cockpit has no start, stop, restart or supervisor control. It only presents current status, last observed time and safe recovery guidance.

### Authority boundary
- **D-39-07:** Feedback, proactive and runtime views do not write Personal/External facts, Serving Snapshot, lifecycle state or Calibration policy; they remain display/traceability surfaces.

### the agent's Discretion

The planner may choose timelines, tables and compact status cards, provided D-39-01..07 and FDB-01..02/RUN-01 remain explicit and accessible.
</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — FDB-01..02, RUN-01.
- `.planning/ROADMAP.md` — Phase 39 goal and criteria.
- `.planning/phases/PDA-26-decision-action-feedback-loop-separate-facts-observations-in/` — append-only feedback authority.
- `.planning/phases/PDA-27-proactive-multi-domain-intelligence-and-target-d-acceptance-/` — proactive/trust control authority.
- `.planning/phases/PDA-31-recommendation-calibration-product-uat/` — non-causal and INCONCLUSIVE calibration boundary.
</canonical_refs>

<code_context>
## Existing Code Insights

- `ui_projection.py` already supplies actions recent, proactive summary, calibration overview and system status operations.
- Cockpit has existing `ActionsPage`, `ProactivePage`, `SystemPage` and query hooks; these are implementation candidates, not completed acceptance.
- `/health` uses `probe_chroma=False`; health display must avoid treating it as an end-to-end retrieval proof.
- Proactive controls exist in authority/orchestration history but are not a permitted Cockpit REST mutation surface.
</code_context>

<deferred>
## Deferred Ideas

- New automated notifications, scheduled actions or write controls.
- Causal claims or personalized strategy promotion based on insufficient cohort data.
- Runtime supervisor actions in the Cockpit.
</deferred>

---
*Phase: 39-feedback-proactive-and-runtime-truthfulness*  
*Context gathered: 2026-07-22*
