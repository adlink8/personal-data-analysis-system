---
phase: 17
plan: "01"
status: complete
completed: 2026-07-13
---

# Plan 17-01 Summary: Eval Foundation and Frozen Gold Suite

## Delivered

| Item | Path / result |
|------|----------------|
| Contracts | `integration/scripts/evaluation/eval_contracts.py` |
| L2 lineage | `reconcile_l2_lineage.py` → **ok=True**, full **768** + pilot **47** = **815** |
| Extraction quality | `extraction_quality_eval.py` → privacy sample hard-fail ready |
| Synthetic suite | `comprehensive_v1.synthetic.jsonl` (**150** cases) |
| Private builder | `build_private_suite.py` → 178 cases (frozen+holdout+synthetic) |
| Manifest | `eval_v1.yaml` |
| Tests | `tests/test_knowledge_eval_dataset.py`, `test_knowledge_eval_extraction.py` |

## L2 discrepancy

Explained: pilot run `2a63b7…` (47) + full run `205bff…` (768) = 815 current L2 units. Terminal failures: 24 sessions. DB hash unchanged (read-only).

## Human checkpoint residual

- Full private gold with resolvable cross-turn evidence ≥30 real cases still needs operator labeling beyond synthetic shells (`17-01-03`).
- CI uses synthetic; private path is gitignored.
