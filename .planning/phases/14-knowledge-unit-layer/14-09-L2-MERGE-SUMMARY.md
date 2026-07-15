---
phase: 14-knowledge-unit-layer
plan: "09-l2-merge"
status: complete
completed: 2026-07-12
---

# L2 → Canonical Merge + Index Promote

## Merge

| Metric | Value |
|--------|------:|
| L2 units loaded | 815 |
| Attached to existing canonical | 53 |
| **New canonical rows** | **762** |
| Canonical current after | **30,774** |
| L2 units status=current | 815 |

Script: `integration/scripts/knowledge/merge_l2_into_canonical.py`  
Report: `integration/analysis/ai_context/knowledge_l2_canonical_merge_report.json`

## Vector index

| Field | Value |
|-------|-------|
| Collection | `knowledge_units_205bff9560b9_20260712142938` |
| Indexed | **30,774** |
| Reconcile | missing=0 orphan=0 |
| Gate | **PASS** |
| Embed | bge-small-zh-v1.5 512d |

## Promote

- **Promoted:** `knowledge_units_205bff9560b9_20260712142938` → **active**
- **Previous (rollback):** `knowledge_units_run_76c6259e_20260712062418`
- Live smoke: `get_knowledge_status` unit_count=**30774**; search returns `knowledge_unit` hits

## Live surface (after merge)

| Surface | Count |
|---------|------:|
| canonical current | **30,774** |
| active Chroma | **30,774** |
| L2 units status=current | **815** |
| Net new canonical from L2 | **762** |
| Attached to existing | **53** |

## Commands

```powershell
python integration/scripts/knowledge/merge_l2_into_canonical.py --write
python integration/scripts/knowledge/build_knowledge_unit_vector_store.py --write
python integration/scripts/knowledge/promote_knowledge_index.py --promote knowledge_units_205bff9560b9_20260712142938
```

## Rollback

```powershell
python integration/scripts/knowledge/promote_knowledge_index.py --list
# or rollback_knowledge_checkpoint / promote previous collection
```
