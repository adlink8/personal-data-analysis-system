---
phase: 29
status: incomplete
updated: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Verification

## Automated evidence

On 2026-07-18 the focused Phase 29 suite passed `48/48`:

```powershell
python -m pytest tests/integration/test_analysis_authority_schema.py tests/integration/test_analysis_candidates.py tests/contract/test_analysis_prompt_lineage.py tests/contract/test_analysis_evidence_gates.py tests/security/test_analysis_safety_gates.py tests/e2e/test_structured_llm_analysis.py -q
```

Governance preflight passed `13/13`, and `git diff --check` passed. Replay,
strict parsing, evidence allowlists, deterministic safety gates, bounded usage,
timeout/fault abstention and zero source-authority mutation are technically
verified.

The real read-only provider preflight for `gpt-5.5` also passed: ChatGPT login
present, model catalog membership true, provider calls zero and identical
Personal/External/Analysis authority fingerprints before and after. A negative
preflight proves `gpt-5.6-luna` fails before generation and leaves the call
budget untouched.

## Live authority binding

- Personal snapshot: `ss_5d816a6bf3ebd0bce9463236`
- External snapshot: `exs_a7770b7d4e9e2727e359befc`
- External snapshot hash:
  `612dbb3d6ffda4f1c4be1aa7eabba177d53f4da3eb1e02f040f69096bbfa149e`
- External authority sequence: `1`

The first explicitly authorized non-stub attempt used this confirmed context
but failed before producing a response. It recorded one provider call,
request checksum
`1484cf6d0d4217c0008139bcfd0e6d19646aaafcf4377ed5ac7a171d6c716d3a`,
reason `codex_cli_failed`, no run/candidate, and unchanged Analysis, Personal and
External authorities.

## Verdict

Technical replay and safety gates pass, but Phase 29 does not yet satisfy the
required successful real structured LLM execution and user review. Verification
status remains `incomplete`; PDI-05 and PDI-06 must not be marked complete.
