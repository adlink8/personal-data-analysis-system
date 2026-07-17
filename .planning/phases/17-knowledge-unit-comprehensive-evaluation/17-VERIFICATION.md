---
phase: 17
status: code_complete_human_residuals
verified: 2026-07-17
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

## 2026-07-17 re-audit

- Live full run `ee36a1f178c17020` used the relocated 178-case private suite and current Active collection.
- Dataset audit PASS: 20/20 real gold evidence refs resolve; no split leakage.
- Active pointer/checksum proxy remained unchanged.
- Gate correctly FAILS: +8.90pp primary delta is below +10pp; cross-turn delta is 0; no-answer FP is 90.625%; privacy/secret hits remain; grounded human labels are absent.
- Policy implementation now checks citation, no-answer, reconcile, MRR, cross-turn, latency and grounded-human thresholds rather than merely declaring them in YAML.
- See `17-EVAL-REVIEW.md` for scored coverage and remediation order.
