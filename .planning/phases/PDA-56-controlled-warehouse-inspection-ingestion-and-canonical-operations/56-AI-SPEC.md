# Phase 56 AI Design Contract

**System:** Tool-using data-plane agent  
**Selected Framework:** Pi SDK Tool calling over project-owned Python transactional facade  
**Alternative:** arbitrary SQL agent — rejected

## Agent Boundary

The model may choose registered operations and parameters; Python resolves real stores, validates authority binding, computes preview/checksum and owns transactions. The model never sees credentials, connection strings or unrestricted row bodies.

## Critical Failure Modes

- Wrong source/store selected.
- Duplicate ingestion after timeout.
- Canonical history overwritten rather than compensated.
- Preview differs from execution.
- Raw body/path/secret leaks in response or logs.

## Evaluation

Code-based transaction/invariant checks are blocking. Human review is required for a live L3 canonical mutation drill; model quality is not an acceptance metric for deterministic warehouse tools.

## Domain Rubric

- **Good:** bounded operation targets the correct logical authority, previews exact effects and converges to one receipt.
- **Bad:** raw overwrite, duplicate ingestion, stale commit, blind retry or unbounded data exposure.
- **Stakes:** a single bad operation can corrupt personal history or make later retrieval unverifiable.

## Entry Point Pattern

```python
preview = warehouse.plan(operation_id, binding, bounded_input)
receipt = warehouse.confirm(preview=preview, confirmed=True, idempotency_key=key)
```

## Typed Boundary Example

```python
class WarehouseOperationRequest(BaseModel):
    operation_id: str
    authority_id: str
    snapshot_id: str
    watermark: str
    idempotency_key: str
    parameters: dict[str, object]
```

## Guardrails, Dataset and Tracing

- Online: operation enum, logical authority map, preview checksum, CAS binding and row/result ceilings.
- Reference set: at least 20 normal, stale, duplicate, crash, SQL/path and compensation fixtures.
- Trace: operation/preview/receipt IDs, counts and fingerprints only.
- [x] Framework and alternative selected
- [x] Domain failure stakes and human L3 gate defined
- [x] Typed transaction boundary and recovery evidence defined
