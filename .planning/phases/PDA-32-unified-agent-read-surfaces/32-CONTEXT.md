# Phase 32: Unified Agent Read Surfaces - Context

**Gathered:** 2026-07-18
**Status:** Ready for planning

<domain>
## Phase Boundary

Phase 32 exposes the already-completed External, Analysis, Pilot and Calibration authorities through shared checksum-verifying read services and semantically equivalent REST, stdio MCP and ChatGPT HTTP MCP tools. It adds no decision writes, provider calls, orchestration state machine or rich widget.

</domain>

<decisions>
## Implementation Decisions

### Tool granularity and transport parity
- **D-01:** Use one clear intent per public tool (`list`, `get`, or `explain`) rather than an operation-dispatch mega-tool.
- **D-02:** Shared Python services define semantics; REST, stdio MCP and Node HTTP Apps MCP remain thin adapters and must pass parity tests.
- **D-03:** HTTP Apps MCP tools carry accurate read-only/non-destructive/closed-world annotations. Existing tool names and behavior remain additive-compatible.

### Read integrity and privacy boundary
- **D-04:** Every detail/explain read validates stored checksums and lineage before returning success; drift, malformed JSON and incomplete authority fail closed with stable codes.
- **D-05:** Default responses are bounded, deterministically ordered metadata summaries. Raw provider response, hidden reasoning, credentials and unnecessary private evidence never enter the default model payload.
- **D-06:** Full evidence is available only through explicit get/explain drill-down and is still filtered by the authority's privacy contract.

### Analysis authority read model
- **D-07:** Add a first-class `AnalysisReadService` matching the established External service envelope instead of duplicating SQL in transports.
- **D-08:** Analysis list/get/explain covers run identity/status, candidate, claims, typed evidence references and provider receipt metadata; request/response bodies remain checksum-addressable but not exposed by default.

### Compatibility and response bounds
- **D-09:** Contracts are additive and versioned. Do not remove or rename Phase 25–27 interfaces.
- **D-10:** List operations enforce hard limits and stable ordering; not-found, invalid-limit and checksum/lineage failures remain distinguishable.
- **D-11:** Phase 32 reads perform zero provider/network calls and zero writes to Personal, External, Analysis, Pilot or Calibration authorities.

### the agent's Discretion

The planner may choose exact route naming, envelope helper placement and test fixture composition as long as D-01..11 and AGENT-01..04 remain satisfied.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone contract
- `.planning/REQUIREMENTS.md` — AGENT-01..04 and v1.3 exclusions.
- `.planning/ROADMAP.md` — Phase 32 goal and success criteria.
- `.planning/research/v1.3-agent-productization/SUMMARY.md` — selected tool-only Apps SDK architecture.
- `.planning/research/v1.3-agent-productization/ARCHITECTURE.md` — transport, confirmation and payload boundaries.

### Prior authority contracts
- `.planning/phases/29-structured-llm-decision-analysis/29-CONTEXT.md` — immutable candidate and deterministic evidence-gate boundary.
- `.planning/phases/30-low-risk-project-decision-pilot/30-CONTEXT.md` — pilot event, manual-action and authority-isolation contract.
- `.planning/phases/31-recommendation-calibration-product-uat/31-CONTEXT.md` — INCONCLUSIVE, no-causal-claim and no-promotion boundary.

### Official platform guidance
- `https://developers.openai.com/apps-sdk/plan/tools` — focused tool design and annotations.
- `https://developers.openai.com/apps-sdk/build/mcp-server` — MCP server/tool/structured result responsibilities.
- `https://developers.openai.com/apps-sdk/reference` — tool descriptor and result metadata contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/personal_knowledge/external_context/service.py`: metadata-only envelope, active-snapshot and fact checksum validation.
- `src/personal_knowledge/intelligence/pilot/service.py`: checksum-verifying case/list/history/control/explain reads.
- `src/personal_knowledge/intelligence/calibration/service.py`: protocol explanation with fixed non-causal/no-promotion limits.
- `src/personal_knowledge/intelligence/analysis/doctor.py` and `runs.py`: complete Analysis table traversal and checksum validation logic to reuse in `AnalysisReadService`.

### Established Patterns
- SQLite read connections use URI `mode=ro`, `PRAGMA query_only=ON` and foreign-key checks.
- Public reads use schema-versioned envelopes and stable error codes.
- Existing Phase 25–27 CLI/REST/MCP surfaces share services and prove metadata-only zero mutation.

### Integration Points
- `src/personal_knowledge/services/api_server.py` for loopback REST routes.
- `src/personal_knowledge/services/mcp_server.py` for stdio MCP descriptors and handlers.
- `apps/personal_data_chatgpt/server.mjs` for ChatGPT HTTP MCP tool descriptors and REST forwarding.
- `tests/contract/` plus `apps/personal_data_chatgpt/test/` for parity, annotations and zero-mutation tests.

</code_context>

<specifics>
## Specific Ideas

Primary app archetype remains tool-only. Compact results should foreground status, stable IDs, limitations and allowed drill-down, not duplicate entire authority records in ChatGPT context.

</specifics>

<deferred>
## Deferred Ideas

- Rich embedded comparison widget/dashboard is deferred to Phase 34 or a later milestone.
- Any write/orchestration tool belongs to Phase 33.

</deferred>

---

*Phase: 32-unified-agent-read-surfaces*
*Context gathered: 2026-07-18*
