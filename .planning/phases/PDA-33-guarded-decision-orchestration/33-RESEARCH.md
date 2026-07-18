---
phase: 33
slug: guarded-decision-orchestration
date: 2026-07-19
requirements: [ORCH-01, ORCH-02, ORCH-03, ORCH-04]
---

# Phase 33 Research: Guarded Decision Orchestration

## Research Question

How should a recoverable Agent session coordinate the existing Analysis, Pilot and Calibration authorities without weakening their confirmation, integrity or no-action boundaries?

## Existing Capability Map

| Capability | Existing authority | Reusable invariant |
|---|---|---|
| Exact dual snapshot binding | `decision/context_binding.py` | Personal/External IDs and hashes are validated at use time |
| Confirmed provider generation | `analysis/executor.py`, `analysis/live_uat.py` | low-risk project only, one provider call, immutable candidate publication |
| Case publication | `pilot/cases.py` | exact run/candidate/option lineage and unchanged source fingerprints |
| Decision/action history | `pilot/workflow.py` | expected sequence, idempotency key, checksum chain, manual-only action |
| Outcome observation | `pilot/outcomes.py` | preregistration required, non-causal assessment |
| Calibration | `calibration/*` | frozen paired protocol, `INCONCLUSIVE`, causal false, proposal-only |
| Read surfaces | Phase 32 shared service/REST/MCP | typed, bounded, checksum-verifying reads |

## Recommended Architecture

Add a separate orchestration authority rather than adding mutable session state to Analysis/Pilot/Calibration:

```text
prepare (pure preview)
  → confirm (creates ledger)
  → generate (reservation → provider → Analysis ref)
  → publish (Pilot case ref)
  → decide (Pilot user decision ref)
  → observe (Pilot outcome ref)
  → calibrate (Calibration ref / honest abstain)
```

The orchestration database contains only session manifests, append-only events, consumed confirmation manifests and provider invocation reservations. Downstream records remain authoritative in their existing databases.

## Provider Exactly-Once Boundary

Network calls cannot be transactionally atomic with SQLite. Therefore ordinary idempotency is insufficient. Use a durable reservation keyed by `(session_id, operation, idempotency_key)`:

1. In `BEGIN IMMEDIATE`, validate confirmation/state/sequence and insert `reserved` invocation with request checksum.
2. Commit before calling the provider.
3. Call provider once.
4. Finalize reservation with receipt/run reference and append event atomically.
5. Exact replay of `completed` returns the stored result.
6. Replay of `reserved` returns `provider_outcome_unknown` and does not call again. Recovery requires explicit reconciliation, never blind retry.

This gives at-most-once provider execution, which is safer than potentially duplicating a paid/non-deterministic call. A crash after provider return but before finalize is honestly uncertain.

## Confirmation Contract

The server issues a preview envelope with:

- session ID and operation
- preview payload and SHA-256 checksum
- exact snapshot/binding hashes
- actor identity hash
- expected sequence
- expiry timestamp (recommended five minutes)
- random nonce stored only as a digest in the confirmation token

The mutation must present the full token plus matching idempotency key. Validation happens before any reservation or downstream write. Tokens are operation-specific and short-lived; the preview checksum covers all user-controlled write inputs.

## State Machine

| Current | Operation | Next | External/provider effect |
|---|---|---|---|
| none | prepare | none | none |
| none | confirm | confirmed | orchestration ledger only |
| confirmed | generate | generated | at most one provider call + Analysis write |
| generated | publish | published | Pilot case write |
| published | decide | decided | Pilot user-decision event |
| decided | observe | observed | Pilot manual/outcome events only |
| observed | calibrate | calibrated or abstained | Calibration record/proposal only |

Resume derives current state by verifying every event checksum and downstream reference. Illegal transitions return `illegal_transition` before effects.

## Threats and Mitigations

| Threat | Mitigation |
|---|---|
| Confirmation replay/drift | operation + preview + actor + session + sequence + expiry binding |
| Concurrent double append | `BEGIN IMMEDIATE`, expected sequence, unique idempotency key |
| Duplicate provider call | durable reservation and fail-closed unknown outcome |
| Authority confusion | store stable IDs/checksums only; validate downstream authority on resume |
| High-risk use | allowlist domain=`project`, risk=`low`; deterministic forbidden-topic/action gates |
| Hidden external action | no connector/command executor in service or tools; manual observation only |
| Calibration overclaim | force causal false, proposal-only, preserve INCONCLUSIVE |

## Validation Architecture

### Unit

- canonical preview/session/event checksums
- token expiry, actor/operation/preview mismatch
- risk and transition table reason codes
- corrupted event chain and reference failure

### Integration

- prepare fingerprints every authority and records zero calls/writes
- exact replay returns identical receipt
- idempotency conflict, stale sequence and expired token have zero side effects
- concurrent duplicate mutation appends once
- provider reservation calls injected provider once; reserved replay never calls
- publish/decide/observe delegate to existing immutable writers with exact references

### Contract

- Service/REST/stdio MCP parity for preview, mutate, resume and explain
- ChatGPT descriptors declare mutations truthfully (`readOnlyHint=false`, `destructiveHint=false`, closed world)
- negative tool calls retain typed reason codes and safe next action

### Acceptance

- disposable four-authority fixture plus orchestration DB executes a full stub-provider path
- fingerprints prove rejected paths and prepare are zero-side-effect
- external actions, automatic promotions and causal claims remain zero/false

## Planning Recommendation

Use four sequential plans: core ledger/confirmation; generation reservation; downstream transitions; transport and all-surface acceptance. This isolates the highest-risk at-most-once provider boundary before adding public tools.
