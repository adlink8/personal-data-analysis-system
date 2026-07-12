---
phase: 14-knowledge-unit-layer
plan: "04"
type: execute
wave: 3
status: complete
requirements: [KU-04, KU-05, KU-06]
completed: 2026-07-11
---

# Phase 14 Plan 04 Summary: Full Backfill + Canonical + Candidate

**Full 2,159-item inventory backfill completed (1,270 succeeded, 2,507 units). Extraction gate PASS (all 9 checks). Canonicalization: 2,507 → 2,393 canonical units. Candidate vector store: 2,393 items, exact reconcile PASS.**

## Accomplishments

### Full backfill
- 2,159 items processed from frozen inventory
- 1,270 succeeded (58.8% yield), 884 abstained, 5 terminal_failed
- 2,507 knowledge units: personal_fact 1,038 / project_decision 491 / preference 371 / capability 203 / habit 176 / tool_usage 131
- 3s/item rate, ~20 RPM, Vertex AI
- Item ledger: 8+ kill→resume cycles, 0 duplicate calls

### Extraction gate (all PASS)
- snapshot_completeness: 0 incomplete ✓
- api_completion: 0 terminal_api_errors ✓
- nonzero_output: 2,507 units ✓
- minimum_yield: 58.8% > 25% ✓
- schema_validity: 99.77% ✓
- overall_failure: 0.23% ✓
- evidence_ref_integrity: 0 foreign/missing ✓
- speaker_attribution: 0 misattribution ✓
- privacy_scan: 0 secret/deleted/excluded hit ✓

### Canonicalization
- 2,507 units → 2,393 canonical (53 merged, 2,357 singletons, 0 conflicts)
- Hard negative false merge: 0 ✓

### Candidate vector store
- Collection: knowledge_units_731a6a8a0994_20260710165905
- 2,393 canonical units indexed
- Exact reconcile: missing=0, orphan=0, duplicate=0 ✓
- Gate PASS

## Verification Evidence

| Evidence | Result |
|---|---|
| Full inventory processed | 2,159/2,159 (100%) |
| Extraction gate | PASS (9/9) |
| Canonical units | 2,393 |
| Candidate index | 2,393 items, gate PASS |
| Active pointer unchanged | knowledge_units_a89ebe470357 |

## Issues

- 5 terminal_failed (persistent schema errors, not API)
- Frozen A/B not comparable (5/20 gold refs in collection, semantic search dilution at 2,393 items)
- Candidate NOT promoted (Plan 14-05 human checkpoint required)