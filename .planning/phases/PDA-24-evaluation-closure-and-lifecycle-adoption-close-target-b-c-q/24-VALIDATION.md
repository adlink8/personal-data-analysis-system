---
phase: 24
validation_strategy: nyquist
status: llm_evidence_complete_quality_failed
---

# Phase 24 Validation

## Requirement Evidence

| Requirement | Required proof |
|---|---|
| QUAL-01 | One immutable snapshot-bound five-mode run; >=30 real Gold, >=30 real cross-turn; answer metrics; calibrated judge artifact; signed UAT |
| QUAL-02 | Candidate safety modes meet privacy/secret/citation/no-answer gates; unsupported evidence abstains; FAIL leaves active snapshot unchanged |
| LIFE-01 | Real reviewed units use current/superseded/conflict/corrected/historical; product search is current-only; history explains transitions |
| LIFE-02 | Append-only events exist for correction/supersede/conflict/promote/rollback; no hard delete; rollback restores prior state with evidence |

## Automated Gates

1. Unit tests for support decisions, privacy vetoes and abstention reason codes.
2. Contract tests proving all product surfaces use current-only results and explicit history.
3. Integration fault injection for lifecycle manifest tamper, stale version, missing evidence and transaction rollback.
4. Dataset audits that reject synthetic-as-real, unresolved refs, split leakage, missing reviewer provenance and snapshot mismatch.
5. Full evaluation dry-run; gate FAIL must preserve active snapshot ID/hash.
6. Full repository pytest and governance preflight.

## Review Gates

- At least 8 additional real scoreable Gold cases and 30 real cross-turn cases reviewed from resolvable evidence.
- 50 grounded L2 packet rows labeled by an explicitly identified human or LLM reviewer; precision >=0.90.
- 30x5 paired answer judge calibration labeled by two independent review runs; agreement >=0.70 before judge is gating.
- UAT explicitly signs promotion/refusal and rollback/forward-restore evidence.

LLM evidence must record model ID, distinct review run ID, prompt version,
timestamp, per-item confidence and checksums. It must never be represented as
human review. Evidence gates now pass; retrieval quality and lifecycle adoption
still fail, so Phase 24 remains incomplete.

## Live Safety Invariants

- Start and end active snapshot ID are recorded for every eval/UAT command.
- Failed gates, dry-runs and label validation never activate a snapshot.
- No source watermark advances during evaluation/lifecycle review.
- No DELETE statements are used for personal knowledge lifecycle changes.
