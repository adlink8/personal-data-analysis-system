---
phase: 17
reviewed: 2026-07-17
overall_score: 73
verdict: NEEDS_WORK
critical_gap_count: 5
---

# Phase 17 Evaluation Coverage Review

## Verdict

The evaluation system is structurally complete and now enforces its declared v1 policy fail-closed, but the product-quality claim is not proven. Promotion must remain blocked.

Latest live run: `var/reports/analysis/evaluations/ee36a1f178c17020/summary.json`.

## Coverage score

| Dimension | Score | Evidence |
|---|---:|---|
| Versioned dataset/contracts | 13/15 | Private suite 178 cases; 20/20 real gold refs resolve; no split leakage |
| Retrieval modes/statistics | 13/20 | Raw/L1/L1+L2/Hybrid live; paired bootstrap present; L2-only still blocked |
| Extraction/lineage | 9/10 | 768 full + 47 pilot = 815 reconciled; DB unchanged |
| Answer evaluation | 9/15 | Deterministic answer path now uses real ephemeral contexts; no calibrated judge |
| Policy gate | 14/15 | All declared hard/quality gates enforced fail-closed |
| Privacy/artifacts | 9/10 | Reports contain IDs/metrics; human packet remains under private runtime |
| Human calibration/UAT | 6/15 | Grounded packet prepared; labels, judge calibration and rollback sign-off pending |
| **Total** | **73/100** | **NEEDS WORK** |

## Latest live findings

| Metric | Result | Required |
|---|---:|---:|
| L1+L2 vs Raw Recall@5 delta | +8.90pp | >= +10pp, CI low > 0 |
| Cross-turn L1+L2 vs L1 | 0pp (n=30) | >= +10pp, CI low > 0 |
| No-answer FP | 90.625% | <= 10% |
| Privacy/secret hard gate | hits present | 0 |
| Gold evidence resolvable | 20/20 | 100% |
| Grounded L2 human sample | packet 50, labels 0 | precision >= 0.90, n >= 50 |
| Active pointer | unchanged | unchanged on FAIL/dry-run |

## Critical gaps

1. L2-only cannot be scored on the shared canonical collection until a genuinely purified candidate collection or server-side lineage filter exists.
2. Retrieval quality does not meet the pre-registered primary claim; it must not be reworded as a pass.
3. Privacy/secret hits and no-answer false positives require case-level triage and retrieval threshold/filter fixes.
4. `grounded_l2_review_v1.jsonl` requires 50 human labels; unlabelled rows cannot enter the gate.
5. Judge calibration (>=30 cases x 5 paired answers) and promote/rollback UAT remain unsigned.

## Remediation order

1. Complete the private grounded review packet at `var/runtime/private_evals/grounded_l2_review_v1.jsonl`, then rerun extraction quality with `--human-labels`.
2. Triage only the failed case IDs from the immutable run; fix privacy/no-answer behavior without changing frozen gold or v1 thresholds.
3. Build an auditable L2-only collection from canonical IDs resolved through `canonical_unit_members`.
4. Produce the 30x5 judge calibration artifact and keep judge informational until agreement >=0.7.
5. Rerun live full evaluation; only after a genuine PASS perform the sandbox promote/rollback UAT and sign `17-UAT.md`.

## Guardrails

- Do not call paid judges without explicit authorization.
- Do not promote, advance watermark, or rewrite v1 thresholds while the gate is FAIL.
- Do not commit private queries, answers, evidence text, or human label packets.
