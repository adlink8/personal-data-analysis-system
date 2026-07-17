---
phase: 17
reviewed: 2026-07-17
overall_score: 71
verdict: NEEDS_WORK
critical_gap_count: 6
---

# Phase 17 Evaluation Coverage Review

## Verdict

The evaluation system is structurally complete and now enforces its declared v1 policy fail-closed, but the product-quality claim is not proven. Promotion must remain blocked.

Latest live run: `var/reports/analysis/evaluations/ee36a1f178c17020/summary.json`.

## Coverage score

| Dimension | Score | Evidence |
|---|---:|---|
| Versioned dataset/contracts | 10/15 | 178 rows, but only 22 real scoreable gold cases and 0 real cross-turn gold; 150 synthetic shells are safety/CI-only |
| Retrieval modes/statistics | 14/20 | Raw/L1/L1+L2/Hybrid live on 22 real gold cases; paired bootstrap present; L2-only still blocked |
| Extraction/lineage | 9/10 | 768 full + 47 pilot = 815 reconciled; DB unchanged |
| Answer evaluation | 9/15 | Deterministic answer path now uses real ephemeral contexts; no calibrated judge |
| Policy gate | 15/15 | All declared hard/quality gates, including private-gold coverage, enforce fail-closed |
| Privacy/artifacts | 9/10 | Reports contain IDs/metrics; human packet remains under private runtime |
| Human calibration/UAT | 5/15 | Grounded packet prepared; real cross-turn gold, labels, judge calibration and rollback sign-off pending |
| **Total** | **71/100** | **NEEDS WORK** |

## Latest live findings

| Metric | Result | Required |
|---|---:|---:|
| L1+L2 Recall@5 | 59.09% (n=22 real gold) | dataset n >= 30 |
| L1+L2 vs Raw Recall@5 delta | +59.09pp; CI low +36.36pp | >= +10pp, CI low > 0; dataset gate must also pass |
| Cross-turn L1+L2 vs L1 | N/A (real gold n=0) | >= +10pp, CI low > 0, n >= 30 |
| No-answer FP | 90.625% | <= 10% |
| Privacy/secret hard gate | hits present | 0 |
| Real scoreable gold / evidence refs | 22 cases; 20/20 refs resolve | cases >= 30; refs 100% |
| Grounded L2 human sample | packet 50, labels 0 | precision >= 0.90, n >= 50 |
| Active pointer | unchanged | unchanged on FAIL/dry-run |

## Critical gaps

1. Private coverage is below policy: 22 real scoreable gold cases and 0 real cross-turn gold; the 150 synthetic shells cannot substitute for human gold.
2. L2-only cannot be scored on the shared canonical collection until a genuinely purified candidate collection or server-side lineage filter exists.
3. The positive primary delta is not promotion evidence while the dataset gate fails; it must not be reworded as a full-suite pass.
4. Privacy/secret hits and 90.625% no-answer false positives require case-level triage and retrieval threshold/filter fixes.
5. `grounded_l2_review_v1.jsonl` requires 50 human labels; unlabelled rows cannot enter the gate.
6. Judge calibration (>=30 cases x 5 paired answers) and promote/rollback UAT remain unsigned.

## Remediation order

1. Add at least 8 real scoreable gold cases and at least 30 real cross-turn gold cases from operator-reviewed evidence; do not relabel synthetic shells as real.
2. Complete the private grounded review packet at `var/runtime/private_evals/grounded_l2_review_v1.jsonl`, then rerun extraction quality with `--human-labels`.
3. Triage only the failed case IDs from the immutable run; fix privacy/no-answer behavior without changing frozen gold or v1 thresholds.
4. Build an auditable L2-only collection from canonical IDs resolved through `canonical_unit_members`.
5. Produce the 30x5 judge calibration artifact and keep judge informational until agreement >=0.7.
6. Rerun live full evaluation; only after a genuine PASS perform the sandbox promote/rollback UAT and sign `17-UAT.md`.

## Guardrails

- Do not call paid judges without explicit authorization.
- Do not promote, advance watermark, or rewrite v1 thresholds while the gate is FAIL.
- Do not commit private queries, answers, evidence text, or human label packets.
