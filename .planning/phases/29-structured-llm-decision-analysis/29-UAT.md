---
phase: 29
plan: 04
status: incomplete
updated: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Product UAT

## Authorization and bounded attempts

- User authorization: existing ChatGPT login, explicitly granted 2026-07-18.
- First planned model: `gpt-5.6-luna`; corrected user-authorized model:
  `gpt-5.4`.
- Each authorization had a hard budget of one provider invocation and no
  automatic retry.
- Sampling: temperature `0.0`; output and total-token limits enforced by the
  production executor.
- Credential check: `codex login status` reported ChatGPT login present; no
  credential value was displayed or persisted.

Both separately authorized invocations ended at the CLI/provider boundary with
`codex_cli_failed`. Each executor returned `abstain`, created no run/candidate
and did not retry.

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

The user then explicitly authorized one `gpt-5.4` retry. Its exact receipt was:

| Field | Value |
|---|---|
| Confirmation event | `uat-gpt54-20260718T101138Z` |
| Requested model | `gpt-5.4` |
| Provider calls | 1 |
| Frozen spec checksum | `3e6b617ce308588fec77f4a91fc02f6ab1a6984ce7844ed1a76f7fa4131af939` |
| Binding hash | `eeb9221568a4abcf9b6b60ffa619f437c60128b5c16a5befece62c9f870655ca` |
| Request checksum | `b85f8fd1aea282e44bc43f47d1206e716745fa512678658a636ce3ecb5553755` |
| Result / reason | provider-boundary `abstain` / `codex_cli_failed` |
| Response / run / candidate | none |
| Personal / External / Analysis changed | false / false / false |
| External actions | 0 |

Post-attempt diagnosis found no `gpt-5.6-luna` entry in the Codex CLI remote
model catalog. The current user configuration names `gpt-5.6-sol`; therefore
the failed Luna invocation is not accepted as the required successful real LLM
UAT. No second invocation is authorized by this record.

Post-attempt diagnosis proved the failed retry selected the PATH npm wrapper
`codex-cli 0.142.4`, while a newer direct Codex executable is installed. The
resolver now selects the newest direct executable and locks preflight and
generation to that same path. Read-only preflight reports `codex-cli 0.145.0`,
`gpt-5.4` available, ChatGPT credential present, all three authority
fingerprints unchanged and `provider_calls=0`. Failure stderr is now mapped to
stable redacted reason codes without persisting raw prompts or diagnostics.

## Frozen corrected request

- Request artifact: `29-LIVE-UAT-REQUEST.json`
- Request-spec checksum:
  `3e6b617ce308588fec77f4a91fc02f6ab1a6984ce7844ed1a76f7fa4131af939`
- Exact internal confirmation phrase:
  `ONE_CHATGPT_CALL:gpt-5.4:3e6b617ce308588fec77f4a91fc02f6ab1a6984ce7844ed1a76f7fa4131af939`
- Prepared prompt size: 7,152 bytes
- Generation budget: temperature `0.0`, output tokens `3,000`, total tokens
  `7,000`, timeout `120s`, attempts `1`, provider calls `1` maximum.

The guarded command additionally requires `--write`, a fresh UTC confirmation
event and the exact phrase above. The authorized attempt is exhausted and must
not be reissued under the same authorization.

## Open scenarios

1. Obtain a new explicit authorization before any call through the corrected
   direct `codex-cli 0.145.0` runtime.
2. Review the resulting exact candidate or deterministic post-model abstention,
   evidence bindings, telemetry, privacy report and zero-side-effect proof.
3. Record explicit user acceptance or rejection of that exact evidence.

Phase 29 remains incomplete. Replay evidence or this pre-generation failure
cannot substitute for the live structured-output checkpoint.
