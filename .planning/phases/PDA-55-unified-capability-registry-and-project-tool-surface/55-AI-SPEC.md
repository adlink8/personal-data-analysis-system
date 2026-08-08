# Phase 55 AI Design Contract

**System:** Tool-using agent capability registry  
**Selected Framework:** existing `@earendil-works/pi-coding-agent` 0.83.0 plus project-owned registry/adapter  
**Alternative:** exposing all MCP tools directly — rejected because duplicated names and excess tool-selection surface

## Tool Contract

The model sees only registry-filtered names, descriptions and JSON schemas. Tool results use compact typed envelopes plus artifact/evidence references; no raw exception, credential, path or unbounded personal body.

## Selection and Safety

- Zero or one exact operation per requested tool name.
- Schema and profile checks run before Python invocation.
- Read tools cannot return mutation tokens or perform provider calls.
- Unknown tools, duplicate aliases, drift and privacy/profile escalation abstain.

## Evaluation

| Dimension | Pass condition |
|---|---|
| Tool selection | exact operation on deterministic fixtures; unknown abstains |
| Schema parity | REST/MCP/Pi checksums identical |
| Safety | forbidden capability/profile fixtures produce zero invocation |
| Compatibility | existing MCP read tests pass through aliases |

## Domain Rubric

- **Good:** one canonical operation/schema/checksum appears identically in every adapter.
- **Bad:** duplicated descriptors, ambiguous aliases, broad tools or leaked implementation details.
- **Stakes:** drift can grant an Agent a capability that Python/MCP policy did not approve.

## Entry Point Pattern

```python
capability = registry.require(operation_id, profile="production")
request = capability.input_model.model_validate(payload)
return gateway.invoke(capability, request)
```

## Typed Boundary Example

```python
class CapabilityInvocation(BaseModel):
    operation_id: str
    profile: Literal["production", "operator"]
    task_id: str
    binding: dict[str, str]
    payload: dict[str, object]
```

## Guardrails, Dataset and Tracing

- Online: schema/profile/privacy/side-effect preflight before invocation.
- Reference set: at least 20 approved/denied/alias/drift fixtures across all read domains.
- Trace: capability ID/version/checksum, profile, task/session, safe status and receipt ref; no body/path/credential.
- [x] Framework and alternative selected
- [x] Domain stakes and deterministic evaluation defined
- [x] Typed entry point and online guardrails defined
