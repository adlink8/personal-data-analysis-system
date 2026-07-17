---
phase: 17
status: partial
last_run: 2026-07-17
---

# Phase 17 UAT — Promotion Gate & Full Eval

## Command

```powershell
python integration/scripts/evaluation/run_knowledge_eval.py --config integration/evals/knowledge_units/eval_v1.yaml --full --render --gate --dry-run
# live retrieval (needs Chroma + embed):
python integration/scripts/evaluation/run_knowledge_eval.py --config integration/evals/knowledge_units/eval_v1.yaml --full --render --gate
```

## Checklist

| Step | Expected | Actual | Pass? |
|------|----------|--------|-------|
| Active pointer before | record | `knowledge_units_ir_4cd8af4ad_20260716020508` | PASS |
| Active checksum proxy before | record | recorded in immutable summary | PASS |
| Dataset audit | ok / documented warnings | 178 cases; 20/20 real refs; 4 documented no-gold warnings | PASS |
| L2 lineage | 768+47=815 explained | `ok=True`, DB unchanged | PASS |
| Five modes | raw/l1/l2_only/l1_l2/hybrid (l2_only may block) | four live; L2-only explicitly blocked pending purified collection | PARTIAL |
| Answer eval | present or skip reason | present for four live modes; real context kept ephemeral | PASS |
| HTML report | under `var/reports/analysis/evaluations/` | `ee36a1f178c17020/report.html` | PASS |
| Gate verdict | PASS or FAIL with reasons | FAIL with explicit policy checks | PASS (correct fail) |
| Active after | **unchanged** on dry-run / FAIL | unchanged | PASS |
| Promote refuse without PASS | `--require-eval-pass` | contract tests pass; no promotion attempted | PASS |
| Rollback | previous collection restore | not executed because gate is FAIL | PENDING |

## Notes

- Human gold labeling for full private suite (cross-turn ≥30 with real evidence) is a checkpoint; CI uses synthetic fixtures.
- Judge calibration (`judge_calibration_v1.jsonl`) must reach κ/ρ ≥ 0.7 before judge enters gate.
- Grounded review packet prepared at `var/runtime/private_evals/grounded_l2_review_v1.jsonl` (50 rows; private; labels pending).
- Latest full live run is intentionally FAIL; rollback UAT must wait for a genuine PASS candidate.
