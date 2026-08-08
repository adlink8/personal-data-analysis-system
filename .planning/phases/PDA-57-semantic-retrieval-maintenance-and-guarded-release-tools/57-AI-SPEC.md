# Phase 57 AI Design Contract

**System:** Agent-orchestrated semantic and retrieval data pipeline  
**Selected Framework:** Pi durable tasks + existing deterministic Python pipeline/evaluation  
**Alternative:** model-driven direct promotion — rejected

## Generation Contract

LLM output is accepted only as a staged Candidate with source evidence and model receipt. Build, reconcile, evaluation and pointer activation remain deterministic Python operations.

## Guardrails

- Schema/evidence/privacy failures block staging.
- Reconcile nonzero missing/orphan/duplicate blocks evaluation and release.
- Evaluation must explicitly PASS the frozen policy.
- Snapshot activation and rollback require exact human-confirmed preview.

## Evaluation

Measure schema compliance, evidence faithfulness, tool sequence correctness, idempotency, recovery and authority invariants. No subjective model judge can override a deterministic gate.

## Domain Rubric

- **Good:** evidence-bound Candidate, isolated generation, zero reconcile defects and accepted frozen evaluation.
- **Bad:** unsupported semantic fact, cross-snapshot index, failed-eval promotion or split active pointer.
- **Stakes:** incorrect promotion contaminates normal retrieval and downstream personal decisions.

## Entry Point Pattern

```python
generation = maintenance.build(snapshot_id=request.snapshot_id, scope=request.scope)
readiness = maintenance.evaluate(generation.id)
release_preview = release.prepare(generation.id, readiness.checksum)
```

## Typed Boundary Example

```python
class RetrievalMaintenanceRequest(BaseModel):
    snapshot_id: str
    scope: list[str]
    batch_limit: int = Field(ge=1, le=1000)
    idempotency_key: str
```

## Guardrails, Dataset and Tracing

- Online: evidence/schema/privacy before staging; reconcile/eval before release; confirmation before pointer change.
- Reference set: 10–20 supported/unsupported/conflict/reconcile/failure/rollback generations.
- Trace: Candidate/generation/eval/preview/receipt refs and protected fingerprints.
- [x] Framework and alternative selected
- [x] Promotion stakes and deterministic gates defined
- [x] Typed pipeline entry and evaluation evidence defined
