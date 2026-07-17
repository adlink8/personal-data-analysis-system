# Plan 21-02 Summary: Graph Domain Migration + Delete v2 Dead Code

**Completed:** 2026-07-15  
**Status:** done  
**Wave:** 2

## What shipped

1. **D-05:** Deleted `domains/graph/build_graph_relation_candidates_v2.py` and registry entries in `tools/forensics/_audit_test_gaps.py` (tools/_reorganize_scripts.py already absent).
2. **5 build scripts → `application/graph/`** with sys.modules alias facades.
3. **1 eval script → `evaluation/graph/`** with facade.
4. **judge_graph_relations** peer-imports `application.graph.build_graph_relation_candidates`.
5. **run_pipeline** + retrieval hint strings updated to `application.graph.*`.
6. **Deferred:** `retrieval/memory.py` 3× `domains.graph.query_graph` lazy imports left intact (CONTEXT deferred).

## Gate

- pytest FAILED set = 13 baseline (no new fails)
- architecture-boundary PASS
- v2 references gone from live tree (excluding planning docs)

## Self-Check: PASSED
