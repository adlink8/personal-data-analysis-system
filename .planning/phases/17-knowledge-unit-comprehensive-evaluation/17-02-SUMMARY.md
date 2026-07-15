---
phase: 17
plan: "02"
status: complete
completed: 2026-07-13
---

# Plan 17-02 Summary: Unified Five-Mode Retrieval Benchmark

## Delivered

| Item | Path |
|------|------|
| Adapters | `retrieval_adapters.py` (no hard-coded collections; L2-only blocked unless purified) |
| Metrics | `knowledge_eval_metrics.py` (primary ID match; snippet diagnostic; bootstrap seed 1701 B=10000) |
| Registry | `eval_registry.py` + `integration/db/evaluation_registry.sqlite` |
| Entrypoint | `run_knowledge_eval.py --retrieval-only` |
| Tests | `tests/test_knowledge_eval_retrieval.py` |

## Live smoke (private suite n=178)

| Mode | R@5 | Notes |
|------|----:|-------|
| raw | 0.00 | personal_events primary-ID miss on mixed suite |
| l1 | 0.089 | |
| l1_l2 | 0.082 | slight drop vs L1 on this mixed set |
| l2_only | blocked | shared canonical index not purified |
| hybrid | 0.116 | |

L1+L2 vs Raw Δ ≈ **+8.2pp** (CI low > 0) but **&lt; +10pp** primary claim → **未证明提升**. Privacy forbid hits on suite also fail hard gate (expected until gold refined).

Active pointer **unchanged**.
