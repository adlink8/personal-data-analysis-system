# Phase 33: Guarded Decision Orchestration - Context

**Gathered:** 2026-07-19
**Status:** Ready for planning
**Mode:** Autonomous Smart Discuss — recommended decisions auto-accepted under standing user authorization

<domain>
## Phase Boundary

Phase 33 adds a deterministic, recoverable `project` decision-session state machine over the immutable Phase 28–32 authorities. It exposes `prepare → confirm → generate → publish → decide → observe → calibrate` through shared service, REST, stdio MCP and ChatGPT HTTP MCP contracts. It does not broaden supported risk/domain scope, execute external actions, make provider output authoritative, or automatically promote calibration proposals.

</domain>

<decisions>
## Implementation Decisions

### Session identity and lifecycle
- **D-01:** A session binds exact Personal and External snapshot IDs/hashes, goal, constraints, option weights, low-risk budget and actor identity at prepare time.
- **D-02:** `prepare` is a pure preview: no provider/network call and no write to Analysis, Pilot or Calibration authorities. The orchestration ledger is created only after a valid explicit confirmation.
- **D-03:** Use an explicit finite-state transition table. Invalid, skipped, duplicate or out-of-order transitions abstain with stable reason codes.
- **D-04:** Resume/get/explain reconstruct state from an append-only checksum chain; stored mutable "current state" is never the authority.

### Confirmation and concurrency
- **D-05:** Every mutating step consumes a short-lived confirmation token bound to operation, exact preview checksum, session identity, actor identity, expected sequence and expiry.
- **D-06:** Confirmation tokens are single-purpose. A token for one preview, operation or actor cannot authorize another.
- **D-07:** Every mutation requires a caller-supplied idempotency key. Exact replays return the original result; same key with different input returns `idempotency_conflict`.
- **D-08:** Compare-and-append uses expected sequence inside one SQLite immediate transaction so concurrent callers cannot double append.

### Provider and authority effects
- **D-09:** Only confirmed `generate` may call the provider, at most once per idempotency key. A durable invocation reservation is committed before the call and finalized after it so network retries resume rather than call twice.
- **D-10:** `publish`, `decide`, `observe` and `calibrate` delegate to existing immutable Analysis/Pilot/Calibration writers; the orchestration ledger stores references and checksums, not copied authority bodies.
- **D-11:** User decision and manual observation remain separate transitions. No transition sends messages, runs commands, purchases, deploys or performs any external action.
- **D-12:** Calibration remains non-causal and proposal-only: `INCONCLUSIVE`, `causal_claim=false`, and no automatic promotion are mandatory output boundaries.

### Risk, freshness and abstention
- **D-13:** Only allowlisted low-risk `project` sessions proceed. Health, finance, legal, safety-critical, irreversible, high-cost or connector-action requests abstain.
- **D-14:** Exact snapshot drift, evidence insufficiency/conflict, expired confirmation, preview drift, stale sequence and illegal transition all fail before provider or authority side effects.
- **D-15:** Errors use stable machine-readable reason codes and include the safe next read/preview action, never a silent fallback.
- **D-16:** All negative-path tests fingerprint orchestration plus four downstream authorities and assert zero provider calls, writes and external actions.

### the agent's Discretion

The planner may choose table names, module boundaries, TTL within a short bounded window, and exact route/tool names while preserving D-01..16, the existing Phase 29–31 authority contracts, and ORCH-01..04.

</decisions>

<canonical_refs>
## Canonical References

- `.planning/REQUIREMENTS.md` — ORCH-01..04 and v1.3 exclusions.
- `.planning/ROADMAP.md` — Phase 33 goal and success criteria.
- `.planning/research/v1.3-agent-productization/ARCHITECTURE.md` — confirmation and transport boundary.
- `.planning/phases/29-structured-llm-decision-analysis/29-CONTEXT.md` — provider candidate and deterministic gate contract.
- `.planning/phases/30-low-risk-project-decision-pilot/30-CONTEXT.md` — append-only decision/action/outcome semantics.
- `.planning/phases/31-recommendation-calibration-product-uat/31-CONTEXT.md` — non-causal/no-promotion boundary.
- `.planning/phases/PDA-32-unified-agent-read-surfaces/32-CONTEXT.md` — shared thin-adapter and privacy contract.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `src/personal_knowledge/intelligence/analysis/live_uat.py` already binds exact confirmation and permits one confirmed provider call.
- `src/personal_knowledge/intelligence/pilot/workflow.py` already implements checksum-chained, expected-sequence and idempotent user-owned events.
- `src/personal_knowledge/intelligence/calibration/` already enforces immutable protocol, verdict and proposal-only behavior.
- `src/personal_knowledge/services/decision_intelligence_reads.py` provides the Phase 32 read authority used for prepare/resume/explain.

### Established Patterns
- SQLite append-only ledgers with checksum chains and immutable triggers.
- Stable typed error codes, schema-versioned envelopes and thin REST/MCP transports.
- Explicit confirmation before any real provider or authority write.
- Live acceptance fingerprints authorities before and after negative/read-only paths.

### Integration Points
- New orchestration package under `src/personal_knowledge/intelligence/orchestration/`.
- Shared orchestration facade under `src/personal_knowledge/services/`.
- Additive `/agent/session/...` REST routes and focused stdio/HTTP MCP tools.
- Contract, integration and live-style acceptance suites under `tests/` and the ChatGPT app tests.

</code_context>

<specifics>
## Specific Ideas

The model may select and narrate tools, but deterministic code exclusively owns lifecycle, confirmation, freshness, risk, privacy, concurrency and authority-write gates. Retry behavior must be designed as replay, not as repeated execution.

</specifics>

<deferred>
## Deferred Ideas

- Rich comparison presentation and response formatting belong to Phase 34.
- Tunnel/startup supervision and real ChatGPT online E2E belong to Phase 35.
- High-risk domains and automated external actions remain out of scope.

</deferred>
