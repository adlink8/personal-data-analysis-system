# AI-SPEC — Phase 50: Durable Task, Domain Tool Bridge and Session Isolation

**Framework:** Pi 0.83.0 AgentSession + project-owned task/session/candidate stores.  
**Provider:** deterministic replay only.  
**Critical rule:** Tool execution is an RPC to Python authority logic, never direct authority access.

## Tool Contract

- Input/output JSON schemas are versioned and operation-specific.
- Read operations return metadata/evidence-bound envelopes.
- Guarded writes reuse Python preview → explicit confirm → exact replay.
- Timeout after dispatch becomes `outcome_unknown`; caller must reconcile by idempotency key before retry.

## State Contract

- Task ledger is control state; Session is trajectory; Candidate is non-serving AI artifact.
- None can represent personal fact, active knowledge or promotion.
- Retention/redaction applies without deleting authority history.

## Evaluation

Atomic claim, transition legality, cancel latency, exact replay, crash recovery, DB separation, privacy and zero-authority mutation are deterministic blocking dimensions.
