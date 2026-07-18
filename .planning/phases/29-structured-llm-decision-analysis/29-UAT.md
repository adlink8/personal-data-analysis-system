---
phase: 29
plan: 04
status: incomplete
updated: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Product UAT

## Authorization and bounded attempt

- User authorization: existing ChatGPT login, explicitly granted 2026-07-18.
- Planned model: `gpt-5.6-luna`.
- Hard call budget: one provider invocation, no automatic retry.
- Sampling: temperature `0.0`; output and total-token limits enforced by the
  production executor.
- Credential check: `codex login status` reported ChatGPT login present; no
  credential value was displayed or persisted.

The single authorized invocation ended at the provider boundary with
`codex_cli_failed`. The executor returned `abstain`; it did not create a run or
candidate and did not retry.

## Attempt evidence

| Field | Value |
|---|---|
| Provider | local Codex CLI using existing ChatGPT login |
| Requested model | `gpt-5.6-luna` |
| Provider calls | 1 |
| Request checksum | `1484cf6d0d4217c0008139bcfd0e6d19646aaafcf4377ed5ac7a171d6c716d3a` |
| Result | `abstain` at provider boundary |
| Reason | `codex_cli_failed` |
| Run / candidate | none |
| Analysis authority changed | false |
| Personal authority changed | false |
| External authority changed | false |

Post-attempt diagnosis found no `gpt-5.6-luna` entry in the Codex CLI remote
model catalog. The current user configuration names `gpt-5.6-sol`; therefore
the failed Luna invocation is not accepted as the required successful real LLM
UAT. No second invocation is authorized by this record.

The corrected read-only preflight now verifies login and catalog membership
before generation. It reports `gpt-5.5` available, ChatGPT credential present,
all three authority fingerprints unchanged and `provider_calls=0`. The same
preflight rejects `gpt-5.6-luna` as `provider_model_unavailable` without
consuming the one-call budget.

## Open scenarios

1. Obtain explicit authorization for one corrected bounded `gpt-5.5` call.
2. Review the resulting exact candidate or deterministic post-model abstention,
   evidence bindings, telemetry, privacy report and zero-side-effect proof.
3. Record explicit user acceptance or rejection of that exact evidence.

Phase 29 remains incomplete. Replay evidence or this pre-generation failure
cannot substitute for the live structured-output checkpoint.
