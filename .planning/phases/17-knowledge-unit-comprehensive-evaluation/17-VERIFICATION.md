---
phase: 17
status: code_complete_human_residuals
verified: 2026-07-17
---

# Phase 17 Verification

## Automated

```text
python -m pytest -q tests/integration/test_knowledge_eval_*.py
python -m personal_knowledge.evaluation.reconcile_l2_lineage
python -m personal_knowledge.evaluation.run_knowledge_eval --config assets/evals/knowledge_units/eval_v1.yaml --full --render --gate --dry-run
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

- Earlier live full run `ee36a1f178c17020` established the corrected 22-case retrieval denominator against the current Active collection.
- Superseding five-mode run `dc71b5d38813ce66` added an exact L2-only evaluation collection while retaining the same private suite and Active source.
- Dataset audit correctly FAILS coverage: 22 real scoreable gold cases (<30), 0 real cross-turn gold (<30); 20/20 real evidence refs resolve and no split leakage.
- Active pointer/checksum proxy remained unchanged.
- Synthetic safety shells and unlabelled non-abstain cases are excluded from retrieval metrics; the authoritative denominator is 22, not 178 or 26.
- L2-only exact audit PASS: expected=764, actual=764, missing=0, orphan=0, source binding PASS; mode is no longer blocked and R@5=18.18%.
- On those 22 cases L1+L2 Recall@5 is 59.09% and the delta vs raw is +59.09pp (CI low +36.36pp), but this cannot authorize promotion while dataset coverage fails.
- Gate correctly FAILS: cross-turn is N/A at real n=0; no-answer FP is 90.625%; privacy/secret hits remain; grounded human labels are absent.
- Policy implementation now checks citation, no-answer, reconcile, MRR, cross-turn, latency and grounded-human thresholds rather than merely declaring them in YAML.
- See `17-EVAL-REVIEW.md` for scored coverage and remediation order.
