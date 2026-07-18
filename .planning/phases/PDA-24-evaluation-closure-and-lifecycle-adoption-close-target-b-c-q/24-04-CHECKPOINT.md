---
phase: 24
plan: 04
status: blocked_on_retrieval_quality_and_lifecycle_adoption
updated: 2026-07-18
---

# Phase 24-04 Final Evaluation Checkpoint

## Exact dry-run evidence

- Run ID: `d54e53ea0a78031da04c18aa9502912a55484fa72bf3a3778d10e7071995aa2c`.
- Dataset: 223 rows; 67 real scoreable Gold; 45 real cross-turn Gold.
- Review binding checksum: `3c084cef17ca639f244680d333863db48563598a78b2be9940661643074e0626`.
- Review strict status: PASS; grounded precision `46/50 = 0.92`.
- Judge calibration: rho `0.7853`, kappa `1.0`, privacy disagreement `0`.
- Gate verdict: `FAIL`; claim: `未证明提升`; runtime errors: `0`.
- Active collection before/after:
  `knowledge_units_ir_4cd8af4ad_20260716020508` (unchanged).

## Passing gates

Dataset audit, LLM review evidence, candidate privacy/secret checks,
no-answer false-positive thresholds, five-mode presence, answer evaluation,
citation precision, reconcile integrity, pure-KU regression, MRR
non-inferiority, latency and grounded precision all pass.

## Remaining quality gaps

- Overall L1+L2 versus raw Recall@5 improvement is `+2.99pp`; policy requires
  at least `+10pp` with a positive confidence-interval lower bound. Observed
  lower bound is `0`.
- Cross-turn L2 versus L1 improvement is `+2.22pp` on 45 cases; confidence
  interval lower bound is `-4.44pp`.
- All 170 reviewed Gold IDs exist in the Active collection. A metadata-only
  rank audit found only 5/45 queries with any Gold in Top-500, while a
  self-semantic index-health sample retrieved 47/50 Gold units at Top-1.
  The remaining defect is cross-turn query-to-unit semantic alignment, not
  missing index data.

## Safety decision

Thresholds were not weakened and source answers were not reused as queries to
inflate recall. No promotion, rollback, forward-restore, lifecycle apply or
Active switch was performed. Release remains blocked until retrieval quality
passes and a valid reviewed lifecycle cohort produces real append-only events.
