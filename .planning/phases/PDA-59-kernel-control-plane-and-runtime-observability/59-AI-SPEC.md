# Phase 59 AI Design Contract

**System:** Single-kernel operation control and recovery
**Selected Framework:** existing Pi SDK Kernel + deterministic Python authority
**Alternative:** local Pi RPC operator or second Agent controller — rejected

## Control Rubric

- **Good:** every AI/data operation has one coordinator, linked receipts, truthful state and bounded recovery action.
- **Bad:** dual controller, blind side-effect retry, UI authority bypass, copied personal body or fabricated completion.
- **Stakes:** incorrect operation state can duplicate Provider calls, corrupt lifecycle ordering or hide an unknown data outcome.

## Entry Point Pattern

```javascript
const operation = control.bind({ taskId, sessionId, kind, correlationId });
await control.request(operation, { action: "reconcile" });
```

## Typed Boundary Example

```python
class KernelOperationAction(BaseModel):
    operation_id: str
    action: Literal["cancel", "resume", "reconcile"]
    expected_state: str
    receipt_checksum: str | None = None
```

## Guardrails, Dataset and Tracing

- Online: one Pi SDK Kernel, deny-by-default capabilities, authority-bound actions and no direct UI/provider/database access.
- Reference set: duplicate/out-of-order events, timeout, crash, outcome_unknown, compensated transaction and privacy decoys.
- Trace: metadata-only Task/Session/Skill/Tool/Provider/authority receipts with correlation and fingerprint refs.
- [x] Framework and rejected alternative selected
- [x] Control stakes and recovery rubric defined
- [x] Typed boundary, privacy and tracing defined
