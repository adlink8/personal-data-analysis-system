# Phase 60 AI Design Contract

**System:** Production acceptance for tool-using personal intelligence agents  
**Selected Framework:** existing Pi SDK Kernel + deterministic Python authority  
**Alternative:** activate from synthetic/replay evidence — rejected

## Acceptance Dimensions

| Dimension | Gate |
|---|---|
| Real quality | accepted paired baseline, same cohort/model/budget |
| Tool/Skill correctness | exact selection/sequence and no forbidden call |
| Data integrity | transaction/replay/compensation and fingerprint invariants |
| Privacy | no personal body/credential/path in telemetry/UI/operation receipts |
| Coordination | Pi SDK Kernel sole primary; no second Agent runtime; legacy standby |
| Recovery | cancel/outcome_unknown/forced rollback and confirmed restore |

Any zero-tolerance failure yields revise/reject and no activation.

## Domain Rubric

- **Good:** accepted real baseline, complete receipts, zero critical violations and exact rollback/restore under user control.
- **Bad:** synthetic substitution, incomplete cohort, dual controller, privacy leak, authority drift or premature activation.
- **Stakes:** final activation changes every production AI and data-maintenance workflow.

## Entry Point Pattern

```python
bundle = readiness.build(required_phases=range(48, 60))
readiness.require_accepted(bundle)
preview = activation.prepare(target="primary", evidence_checksum=bundle.checksum)
```

## Typed Boundary Example

```python
class FinalActivationRequest(BaseModel):
    target: Literal["shadow", "canary", "primary", "legacy"]
    evidence_checksum: str
    rollback_target: str
    confirmed: bool
```

## Guardrails, Dataset and Tracing

- Online: accepted baseline/readiness bundle, signed transition, single coordinator/provider path and automatic downgrade only.
- Reference set: all Phase 55–59 acceptance cases plus independent real cohort ≥2 and forced cross-plane failures.
- Trace: immutable evidence, activation, Task/Skill/Tool/data receipts and fingerprints without personal bodies.
- [x] Framework and alternative selected
- [x] Acceptance stakes and zero-tolerance rubric defined
- [x] Typed activation boundary, guardrails and tracing defined
