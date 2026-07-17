---
phase: 17
status: partial
last_run: 2026-07-17
---

# Phase 17 UAT — Promotion Gate & Full Eval

## Command

```powershell
python -m personal_knowledge.evaluation.run_knowledge_eval --config assets/evals/knowledge_units/eval_v1.yaml --full --render --gate --dry-run
# Promotion-capable live run (only after all gates can pass):
python -m personal_knowledge.evaluation.run_knowledge_eval --config assets/evals/knowledge_units/eval_v1.yaml --full --render --gate
```

## Checklist

| Step | Expected | Actual | Pass? |
|------|----------|--------|-------|
| Active pointer before | record | `knowledge_units_ir_4cd8af4ad_20260716020508` | PASS |
| Active checksum proxy before | record | recorded in immutable summary | PASS |
| Dataset audit | private gold >=30; real cross-turn gold >=30 | FAIL: 178 rows include 150 synthetic shells; real scoreable gold=22; real cross-turn gold=0; 20/20 real refs resolve | PASS (correct fail-closed) |
| L2 lineage | 768+47=815 explained | `ok=True`, DB unchanged | PASS |
| Five modes | raw/l1/l2_only/l1_l2/hybrid | all five live; L2-only exact collection audit 764/764 and R@5=18.18% on 22 real gold cases | PASS |
| Answer eval | present or skip reason | present for all five live modes; real context kept ephemeral | PASS |
| HTML report | under `var/reports/analysis/evaluations/` | `6d7233db5da0414c/report.html` | PASS |
| Gate verdict | PASS or FAIL with reasons | FAIL with explicit policy checks | PASS (correct fail) |
| Active after | **unchanged** on dry-run / FAIL | unchanged | PASS |
| Promote refuse without PASS | `--require-eval-pass` | contract tests pass; no promotion attempted | PASS |
| Rollback | previous collection restore | not executed because gate is FAIL | PENDING |

## Notes

- Human gold labeling is a blocking checkpoint: add >=8 real scoreable cases and reach cross-turn >=30 with real evidence; CI synthetic fixtures remain excluded from retrieval metrics.
- Judge calibration (`judge_calibration_v1.jsonl`) must reach κ/ρ ≥ 0.7 before judge enters gate.
- Grounded review packet prepared at `var/runtime/private_evals/grounded_l2_review_v1.jsonl` (50 rows; private; labels pending).
- Latest full live run is intentionally FAIL; rollback UAT must wait for a genuine PASS candidate.
- L2-only collection `knowledge_units_eval_l2_894985b38fe5` is evaluation-only, exact 764/764, and did not change Active.
- Scorer v2 provenance audit reports secret_hit=0 for every mode; privacy hits remain and the overall gate stays FAIL.
- Abstention calibration artifact `abstention_calibration_v1.json` is development-only and FAILS its positive-retention constraint; no threshold was applied.
- Policy v2 gate scope verified: raw/L1 safety metrics remain diagnostic; enforced candidate checks are L2-only/L1+L2/Hybrid, and the final verdict remains FAIL.
