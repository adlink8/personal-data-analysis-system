---
phase: 17
reviewed: 2026-07-17
overall_score: 74
verdict: NEEDS_WORK
critical_gap_count: 5
---

# Phase 17 Evaluation Coverage Review

## Verdict

The evaluation system is structurally complete and now enforces its declared v1 policy fail-closed, but the product-quality claim is not proven. Promotion must remain blocked.

Latest live run: `var/reports/analysis/evaluations/6d7233db5da0414c/summary.json` (scorer v2, policy v2).

## Coverage score

| Dimension | Score | Evidence |
|---|---:|---|
| Versioned dataset/contracts | 10/15 | 178 rows, but only 22 real scoreable gold cases and 0 real cross-turn gold; 150 synthetic shells are safety/CI-only |
| Retrieval modes/statistics | 17/20 | All five modes live on 22 real gold cases; paired bootstrap present; L2-only exact collection audit 764/764 |
| Extraction/lineage | 9/10 | 768 full + 47 pilot = 815 reconciled; DB unchanged |
| Answer evaluation | 9/15 | Deterministic answer path now uses real ephemeral contexts; no calibrated judge |
| Policy gate | 15/15 | Policy v2 preserves v1 thresholds, requires all five modes, and applies safety vetoes only to publishable candidate modes |
| Privacy/artifacts | 9/10 | Reports contain IDs/metrics; human packet remains under private runtime |
| Human calibration/UAT | 5/15 | Grounded packet prepared; real cross-turn gold, labels, judge calibration and rollback sign-off pending |
| **Total** | **74/100** | **NEEDS WORK** |

## Latest live findings

| Metric | Result | Required |
|---|---:|---:|
| L1+L2 Recall@5 | 59.09% (n=22 real gold) | dataset n >= 30 |
| L2-only Recall@5 | 18.18% (n=22 real gold) | diagnostic; exact collection required |
| L1+L2 vs Raw Recall@5 delta | +59.09pp; CI low +36.36pp | >= +10pp, CI low > 0; dataset gate must also pass |
| Cross-turn L1+L2 vs L1 | N/A (real gold n=0) | >= +10pp, CI low > 0, n >= 30 |
| No-answer FP | 90.625% | <= 10% |
| Privacy hard gate | hits remain in raw/L1/L2-only/hybrid; L1+L2=0 | 0 |
| Secret provenance hard gate | 0 in all five modes | 0 |
| Real scoreable gold / evidence refs | 22 cases; 20/20 refs resolve | cases >= 30; refs 100% |
| Grounded L2 human sample | packet 50, labels 0 | precision >= 0.90, n >= 50 |
| Active pointer | unchanged | unchanged on FAIL/dry-run |

## Critical gaps

1. Private coverage is below policy: 22 real scoreable gold cases and 0 real cross-turn gold; the 150 synthetic shells cannot substitute for human gold.
2. The positive primary delta is not promotion evidence while the dataset gate fails; it must not be reworded as a full-suite pass.
3. Privacy hits and 90.625% no-answer false positives require evidence-aware relevance/abstention; score-only thresholding is proven insufficient on the isolated dev set.
4. `grounded_l2_review_v1.jsonl` requires 50 human labels; unlabelled rows cannot enter the gate.
5. Judge calibration (>=30 cases x 5 paired answers) and promote/rollback UAT remain unsigned.

## Remediation order

1. Add at least 8 real scoreable gold cases and at least 30 real cross-turn gold cases from operator-reviewed evidence; do not relabel synthetic shells as real.
2. Complete the private grounded review packet at `var/runtime/private_evals/grounded_l2_review_v1.jsonl`, then rerun extraction quality with `--human-labels`.
3. Triage only the failed case IDs from the immutable run. Add independently reviewed no-answer negatives and implement evidence-aware relevance/abstention; do not select thresholds on frozen data.
4. Produce the 30x5 judge calibration artifact and keep judge informational until agreement >=0.7.
5. Rerun live full evaluation; only after a genuine PASS perform the sandbox promote/rollback UAT and sign `17-UAT.md`.

## Guardrails

- Do not call paid judges without explicit authorization.
- Do not promote, advance watermark, or rewrite v1 thresholds while the gate is FAIL.
- Do not commit private queries, answers, evidence text, or human label packets.

## Closed in this re-audit

- Synthetic shells and unlabelled non-abstain cases no longer enter retrieval denominators.
- Evaluation-only collection `knowledge_units_eval_l2_894985b38fe5` contains exactly 764 configured L2 lineage canonical IDs (missing=0, orphan=0), is bound to the evaluated Active source, and is not Active itself.
- L2-only now runs as a genuine fifth mode; its current R@5 is 18.18% on the limited 22-case real-gold set.
- Scorer v2 replaces lexical `API/secret` matching with canonical evidence provenance. The 11 previously implicated units all came from evidence-eligible sessions; secret leakage is now correctly 0 across all modes.
- Private abstention dev set contains 29 independently labeled canary positives and 29 paired absent-nonce hard negatives. No score threshold passed both FP<=10% and positive retention>=80%; observed positive retention was 6.9%–55.2%, so no threshold was deployed.
- Policy v2 keeps raw/L1 as diagnostic baselines and scopes hard safety vetoes to L2-only, L1+L2, and Hybrid. The final gate still FAILS on genuine candidate issues: L2-only/Hybrid privacy, all candidate modes' no-answer FP, dataset coverage, cross-turn, and grounded-human evidence.
