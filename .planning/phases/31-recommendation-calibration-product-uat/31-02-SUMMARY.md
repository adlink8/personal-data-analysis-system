---
phase: 31-recommendation-calibration-product-uat
plan: 02
subsystem: decision-intelligence
tags: [paired-arms, gpt-5.4, blinded, leakage, inconclusive]
requires:
  - phase: 31-01
    provides: frozen calibration protocol
provides: [two real GPT-5.4 arm receipts, leakage-proof generic request, non-causal verdict]
affects: [31-03, milestone-audit]
tech-stack:
  added: []
  patterns: [one-difference arm parity, blind labels, protocol-deviation honesty]
key-files:
  created: [src/personal_knowledge/intelligence/calibration/paired.py, src/personal_knowledge/intelligence/calibration/evaluation.py, assets/schemas/calibration_arm_response_v1.json]
  modified: []
key-decisions:
  - "Record INCONCLUSIVE because n=1, generic outcomes are missing, and actual token usage exceeded the frozen budget."
requirements-completed: [PDI-08]
duration: 16min
completed: 2026-07-18
---

# Phase 31 Plan 02: Real Paired Comparison Summary

**Two one-shot GPT-5.4 arms produced exact receipts, but frozen small-sample and budget-deviation rules correctly force an INCONCLUSIVE verdict.**

## Accomplishments

- Personalized arm `cala_49fce560acbd91a3421e7501`: candidate, checksum `fd871ae48b3fc8f8977976def88a3c562c5bda9454f182f64ceef69d22660fde`.
- Generic arm `cala_eec33f90bf2c602f9e46c185`: abstain, checksum `8d15d48e4c2ecd49047f9974e41446c7101fde28b58c024cef0c342a137d2eb4`.
- Both calls used ChatGPT login, GPT-5.4, temperature 0, one call each, zero retry and zero cost.
- Verdict `calv_3aab06de0c879656707f55f7` is `INCONCLUSIVE`, causal claim false.

## Task Commits

1. **Build leakage-proof paired arms** - `cb5ac58`, schema `03965d1`
2. **Authorize bounded paired production calls** - exact protocol `2dc7078c...44e0`, two calls only
3. **Evaluate observed paired results** - `d94bd90`

## Deviations from Plan

- Actual input tokens were 18,567 and 18,515, exceeding the frozen 12,000 budget and differing by 52. This is retained as a protocol deviation, not auto-corrected or hidden.

## Verification

- Pairing/evaluation suite: 4 passed.
- Provider receipts: personalized 13,642 ms / 378 output tokens; generic 14,459 ms / 409 output tokens.
- Generic request contains no Personal snapshot, history, derived feature or identifying metadata.

## Self-Check: PASSED

The exact arm evidence reconstructs the verdict; no missing or deviating evidence can become a gain claim.

## Next Phase Readiness

Ready to create only an immutable candidate proposal; automatic promotion remains forbidden.
