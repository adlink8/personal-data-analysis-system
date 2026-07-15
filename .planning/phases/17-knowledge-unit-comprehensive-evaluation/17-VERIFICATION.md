---
phase: 17
status: code_complete_human_residuals
verified: 2026-07-13
---

# Phase 17 Verification

## Automated

```text
python -m pytest -q tests/test_knowledge_eval_*.py   # PASS
python integration/scripts/evaluation/reconcile_l2_lineage.py --check  # ok=True 768+47=815
python integration/scripts/evaluation/run_knowledge_eval.py --full --render --gate --dry-run --offline  # active_unchanged
```

## Requirements map

| ID | Status |
|----|--------|
| EVAL-01/02 | Implemented (five-mode + paired bootstrap) |
| EVAL-03/04 | Lineage PASS; private gold needs human fill |
| EVAL-05/06 | Rule answer metrics PASS; judge calibration pending |
| EVAL-07 | Immutable registry PASS |
| EVAL-08 | HTML under analysis/evaluations PASS |
| EVAL-09 | Gate fail-closed + promote refuse path PASS |
| EVAL-10 | Single CLI PASS |

## Not closed

- Operator-labeled cross-turn gold
- Judge calibration artifact
- Signed `17-UAT.md` promote/rollback
