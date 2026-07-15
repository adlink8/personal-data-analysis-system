---
phase: 17
status: planned
nyquist: enabled
---

# Phase 17 Validation Matrix

| Requirement | Verification |
|---|---|
| EVAL-01/02 | fixture 五路 run；同 dataset hash/top-k/scorer；指标快照测试 |
| EVAL-03/04 | L2 lineage SQL reconcile；人工 gold schema；重复/冲突/privacy fixtures |
| EVAL-05/06 | deterministic answer fixtures + calibrated judge contract tests |
| EVAL-07 | registry idempotency、immutable run、dataset/config hash tests |
| EVAL-08 | HTML/PNG build smoke、无原文/secret scan、关键图表存在 |
| EVAL-09 | gate pass/fail、active unchanged、promote/rollback sandbox E2E |
| EVAL-10 | single CLI exit-code tests、只读 active checksum before/after |

## Required final runs

```powershell
python -m pytest -q tests/test_knowledge_eval_*.py
python integration/scripts/evaluation/run_knowledge_eval.py --config integration/evals/knowledge_units/eval_v1.yaml --full --render --gate --dry-run
```

单入口必须依次执行 dataset audit → extraction quality → 五路 retrieval → answer eval → render → gate；candidate 从 config/manifest 解析。任一步失败返回非零，并证明 active checksum 前后不变。
