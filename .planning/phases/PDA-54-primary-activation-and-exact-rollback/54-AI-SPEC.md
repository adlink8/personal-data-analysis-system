# AI-SPEC — Phase 54: Primary Activation and Exact Rollback

## Runtime Authority

Pi becomes the sole primary AI controller; Python remains deterministic data authority. Legacy is a disabled standby adapter, not a concurrent agent.

## Activation Guardrails

- Human-confirmed upgrades only; automatic downgrade permitted on stop condition.
- Every primary AI call has Pi task/session/event/model receipts.
- No double Provider side effect in shadow/canary.
- Rollback never deletes Session/Event/Candidate or changes watermark/promotion/active pointer.
- Readiness fails if any production AI callsite bypasses Pi.

## Acceptance

Primary, forced failure, exact rollback and forward-restore all pass with identical authority fingerprints and user-signed activation record.
