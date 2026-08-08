# AI-SPEC — Phase 51: Provider, Skill Registry and Full AI Workflow Migration

**Framework:** Pi 0.83.0 provider/model/session/tool event loop.  
**Project contracts retained:** Python ProviderRequest/Result/Telemetry, evidence and Candidate schemas.

## Model Routing

Every route is allowlisted by purpose and contains provider/model/token/cost/timeout/retry ceilings. Credentials are injected, never discovered. No silent model fallback; outcome_unknown requires reconciliation.

## Skill Routing

Skill manifests include id, version, checksum, purpose, input/output schema, allowed tools, privacy ceiling and owner. Deterministic policy chooses zero or one skill; ambiguity abstains.

## Migration Acceptance

- Static callsite inventory 100% classified.
- Replay parity for output schema, usage and error codes.
- All real model calls create Pi task/session/event receipts.
- Legacy path is rollback-only and cannot run concurrently except the Phase 53 comparison harness.

## Evals

Phase 51 uses replay/synthetic fixtures only. Real quality/cost judgement remains Phase 53 to prevent implementation tests from certifying production quality.
