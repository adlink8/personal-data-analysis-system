# Phase 58 AI Design Contract

**System:** Stateful tool-using workflow agent  
**Selected Framework:** Pi SDK Skill registry plus project-owned declarative state machine  
**Alternative:** free-form prompt library — rejected

## Skill Manifest

Required: id/version/checksum/purpose/input/output/profile/privacy/allowed_tools/steps/budgets/stop_conditions/recovery/receipt schema/instruction checksum/owner/expiry.

## Evaluation Rubric

| Dimension | Blocking expectation |
|---|---|
| Selection | exact zero-or-one Skill |
| Tool correctness | only declared operation and valid order |
| Recovery | resume without duplicate side effects |
| Safety | checkpoint and profile boundaries never skipped |
| Grounding | claims carry evidence refs or abstain |
| Cost | rounds/tool/model usage stay within manifest ceilings |

Human review calibrates usefulness and clarity; it cannot override deterministic safety failures.

## Domain Rubric

- **Good:** exact Skill selection, grounded output, declared Tool sequence, bounded cost and recoverable step receipts.
- **Bad:** free-form hidden workflow, undeclared Tool, skipped confirmation, unsupported claim or repeated side effect.
- **Stakes:** a faulty reusable Skill scales one mistake across many personal and data operations.

## Entry Point Pattern

```javascript
const selected = registry.select({ purpose, input_schema, profile });
const run = await engine.start({ skill: selected.skill, taskId, sessionId, input });
```

## Typed Boundary Example

```python
class SkillInvocation(BaseModel):
    purpose: str
    input_schema: str
    profile: Literal["production", "operator"]
    task_id: str
    session_id: str
    input: dict[str, object]
```

## Guardrails, Dataset and Tracing

- Online: exact checksum, zero-or-one selection, allowed_tools subset, max steps/rounds/budget and L3 checkpoint.
- Reference set: 10–20 product cases plus success/abstain/fault/replay fixtures per Skill.
- Trace: Skill ID/version/checksum, step/tool receipts, stops and usage metadata.
- [x] Framework and alternative selected
- [x] Domain rubric and product reference cases defined
- [x] Typed invocation, guardrails and tracing defined
