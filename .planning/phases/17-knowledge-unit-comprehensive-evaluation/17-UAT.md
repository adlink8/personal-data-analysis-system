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
| Active pointer before | record | | |
| Active checksum proxy before | record | | |
| Dataset audit | ok / documented warnings | | |
| L2 lineage | 768+47=815 explained | | |
| Five modes | raw/l1/l2_only/l1_l2/hybrid (l2_only may block) | | |
| Answer eval | present or skip reason | | |
| HTML report | under integration/analysis/evaluations/ | | |
| Gate verdict | PASS or FAIL with reasons | | |
| Active after | **unchanged** on dry-run / FAIL | | |
| Promote refuse without PASS | `--require-eval-pass` | | |
| Rollback | previous collection restore | | |

## Notes

- Human gold labeling for full private suite (cross-turn ≥30 with real evidence) is a checkpoint; CI uses synthetic fixtures.
- Judge calibration (`judge_calibration_v1.jsonl`) must reach κ/ρ ≥ 0.7 before judge enters gate.
