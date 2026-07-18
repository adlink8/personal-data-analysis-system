---
phase: 24
plan: 02
status: llm_review_complete_quality_gate_open
checkpoint: auditable-llm-review
updated: 2026-07-18
---

# Phase 24-02 LLM Review Checkpoint

The user authorized LLM review in place of manual labeling. Imports remain
fail-closed and distinguish `reviewer_type=llm` from human provenance; no LLM
identity is presented as a person. Private payloads remain gitignored.

## Strict evidence

| Gate | Accepted evidence | Audit binding |
|---|---:|---|
| Additional/cross-turn Gold | 45 | `gpt-5.6-luna`, run `phase24-gold-20260718-ku-bound`, prompt `phase24-gold-review-v3-ku-bound` |
| Grounded L2 | 50 (46 grounded / 4 unsupported) | run `phase24-grounded-20260718-eligible`, prompt `phase24-grounded-review-v2` |
| Judge calibration | 30 × 5 = 150 | independent runs `phase24-judge-20260718-primary` and `phase24-judge-20260718-independent` |

`review_packets status --strict` returns `ok=true`. Judge agreement is
Spearman rho `0.7853`, Cohen kappa `1.0`, with zero privacy disagreement.
Grounded precision is `0.92` on 50 eligible rows.

The historical `human_*` artifact names and `grounded_precision_human` metric
name are retained only for file/schema compatibility. Their manifests carry
the actual reviewer type, model, run ID, prompt version, timestamp and checksum.
