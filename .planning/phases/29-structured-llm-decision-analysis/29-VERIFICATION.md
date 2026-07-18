---
phase: 29
status: incomplete
updated: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Verification

## Automated evidence

On 2026-07-18 the focused Phase 29 suite passed `55/55` after adding guarded
live-UAT, direct-runtime selection, redacted failure classification and
structured-output closure/authorization-lineage contracts:

```powershell
python -m pytest tests/integration/test_analysis_authority_schema.py tests/integration/test_analysis_candidates.py tests/contract/test_analysis_prompt_lineage.py tests/contract/test_analysis_evidence_gates.py tests/contract/test_analysis_live_uat.py tests/security/test_analysis_safety_gates.py tests/e2e/test_structured_llm_analysis.py -q
```

Governance preflight passed `13/13`, and `git diff --check` passed. Replay,
strict parsing, evidence allowlists, deterministic safety gates, bounded usage,
timeout/fault abstention and zero source-authority mutation are technically
verified.

The real read-only provider preflight for `gpt-5.4` passes on the corrected
direct `codex-cli 0.145.0` runtime: ChatGPT login present, model catalog
membership true, provider calls zero and identical Personal/External/Analysis
authority fingerprints before and after. Resolver tests prove the newer direct
runtime wins over the older npm wrapper, and failure-classification tests prove
stderr is reduced to stable codes without diagnostic disclosure.

The frozen corrected request also passes strict parsing, live dual-snapshot
binding and presentation of one Personal observation plus four External facts.
Its prompt is 7,152 bytes. The guarded CLI contract rejects a wrong
confirmation before preflight and fixes execution to `max_attempts=1`, one
provider call and zero external actions.

## Live authority binding

- Personal snapshot: `ss_5d816a6bf3ebd0bce9463236`
- External snapshot: `exs_a7770b7d4e9e2727e359befc`
- External snapshot hash:
  `612dbb3d6ffda4f1c4be1aa7eabba177d53f4da3eb1e02f040f69096bbfa149e`
- External authority sequence: `1`

Two explicitly authorized non-stub attempts used this confirmed context but
failed before producing a response. The latest `gpt-5.4` receipt recorded
binding hash `eeb9221568a4abcf9b6b60ffa619f437c60128b5c16a5befece62c9f870655ca`,
request checksum `b85f8fd1aea282e44bc43f47d1206e716745fa512678658a636ce3ecb5553755`,
one provider call, reason `codex_cli_failed`, no response/run/candidate and
unchanged Analysis, Personal and External authorities. The attempt used the
older PATH npm wrapper; no retry was made after correcting runtime selection.

A third, separately authorized `gpt-5.4` attempt used direct
`codex-cli 0.145.0` and still failed before response creation. It recorded
binding hash `5b13104ee2d4b609a38e4d6749ad6fad61bca021dc2efaa541b7ebef11ed7f93`,
request checksum `cc0d552c4909386553303e8a786ab6e88d33be8559d85219ba478ce01d515b06`,
one call, zero retries, no response/run/candidate and unchanged source/analysis
authorities. Offline inspection then found and fixed one open object branch in
the structured-output Schema. The current Schema passes Draft 2020-12
validation and a recursive all-objects-closed contract. Authorization now
binds spec, Prompt, Schema, Policy and model checksums; no post-fix call has run.

A fourth explicitly authorized lineage-bound attempt still exited before a
response. It recorded authorization checksum
`3e0dcc32f21359e42ccf92c8ebc0a63d631f5e649b1fd6a8bc9afb5cf2bf757e`,
binding hash `77c7fdfcb1936633c407d5130e4ce01cb47868ab6436a98c712bd1460d2db822`,
request checksum `a01718b8377b99da433d96363fa47461da17c8f0f89390c9e3e9c3b1cb5a77bc`,
one call, zero retries, no response/run/candidate and unchanged authorities.
The remaining local defect was implicit Windows locale encoding for the
Chinese prompt. The provider now uses strict UTF-8 for stdin/stdout/stderr and
the E2E contract asserts an actual Chinese prompt plus encoding arguments. No
post-encoding-fix call has run.

## Verdict

Technical replay and safety gates pass, but Phase 29 does not yet satisfy the
required successful real structured LLM execution and user review. Verification
status remains `incomplete`; PDI-05 and PDI-06 must not be marked complete.
