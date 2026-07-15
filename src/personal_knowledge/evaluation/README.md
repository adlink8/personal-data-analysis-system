# Evaluation

## Responsibility

Frozen suites, ablations, metrics, reports, and promotion gates.
**After Phase 21, subdomain and vector eval scripts live here.**

## Layout

```
evaluation/
  conversation/   # cutover, prompt/quality eval, compare_summaries, eval-set
  graph/          # relation judgment eval
  knowledge/      # canary, extraction, RAG eval
  memory/         # depth / promotion / relation / experiment suites
  vector/         # evaluate_vector_*, compare_*_generations (from retrieval/)
  run_knowledge_eval.py, gate_knowledge_candidate.py, …
```

## Boundaries

Reads public contracts/candidates; cannot silently mutate active generations.

## Entry points

```powershell
python -m personal_knowledge.evaluation.run_knowledge_eval --help
python -m personal_knowledge.evaluation.vector.evaluate_vector_collections
python -m personal_knowledge.evaluation.knowledge.evaluate_knowledge_canary
```

Legacy imports via `domains.*` / `retrieval.evaluate_*` facades remain until
**2026-08-13**.

## Tests

```powershell
python -m pytest -q tests/test_knowledge_eval_*.py
python -m pytest -q tests/unit/test_vector_collection_eval.py
```

## Ownership

Owner: evaluation. Status: supported. Last layout review: Phase 21 (2026-07-15).
