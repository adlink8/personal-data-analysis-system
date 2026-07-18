---
phase: 29
status: passed
updated: 2026-07-18
requirements: [PDI-05, PDI-06]
---

# Phase 29 Verification

## Automated gates

The focused Phase 29 suite passed `66/66`; governance preflight passed
`13/13`; `git diff --check` passed. Coverage includes replay, strict parsing,
exact evidence, deterministic safety gates, credential/config isolation,
bounded usage, fault-atomic publication, evidence reuse and append-only
migration.

## Real provider proof

Live run `dar_77843392b266cd0a992cc274` published candidate
`dac_8abee23d30d7df2c9df47ab7` through `codex-chatgpt/gpt-5.4` with one call,
zero retries and zero external actions. Request/response checksums are stored
in the run and receipt. Five factual plus three inference claims resolve to
thirteen frozen dual-snapshot references.

Personal and External authorities remained byte-identical. Analysis changed
only through expected committed append-only records. Doctor is `ready`,
unchanged and finding-free.

## Closed defects

- Removed inherited invalid API-key routing; ChatGPT is the only child auth.
- Isolated user MCP/plugins and prioritized JSONL errors over stderr warnings.
- Made the response Schema compatible with the OpenAI strict subset.
- Exposed request checksum to the model without self-referential hashing.
- Repaired legacy evidence payload uniqueness for legitimate evidence reuse.

## Verdict

Passed. PDI-05 and PDI-06 are satisfied, and no UAT scenario remains open.
