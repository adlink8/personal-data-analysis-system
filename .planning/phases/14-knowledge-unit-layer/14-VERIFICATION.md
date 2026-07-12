---
phase: 14-knowledge-unit-layer
verified: 2026-07-12
status: partial
score: wrap-up automated PASS; KU-08 production delta open
---

# Phase 14 Verification Report

## Scope

Verify Phase 14 after expanded production extraction, merge canonicalization, active promote, and wrap-up test suite.

## Verified facts

| Check | Status | Evidence |
|-------|--------|----------|
| Plans 14-01..06 delivered | Pass | `14-0x-SUMMARY.md` |
| Expanded inventory | Pass | 16,743 authoritative |
| Run ledger drain | Pass | rem=0 on `run_76c6259e9ed09d5b` |
| Extraction gate | **Pass** | yield 91.4%, failure 0.41%, api_completion=0 |
| Missing 2,159 positions | Pass | covered by prior run `731a6a8a0994…` |
| Canonical hard-neg false merge | Pass | 0 |
| Canonical positive recall (old pair IDs) | N/A | 0.0 — pilot pair IDs not in expanded members |
| Candidate index exact reconcile | **Pass** | 30,012 = eligible; checksum match（分页 ID 校验） |
| Active promote | Pass | `knowledge_units_run_76c6259e_20260712062418` |
| Rollback available | Pass | previous `knowledge_units_v2_20260712` |
| Pure-KU frozen Recall@5 | Partial | **0.65** (secret 0) |
| Hybrid frozen Recall@5 | Partial | **0.65** (below prior 0.85 baseline) |
| Canary smoke | Pass | 10–20 queries; labels pending |
| Knowledge pytest | **Pass** | **151** passed (`-k knowledge`) |
| Full pytest suite | **Pass** | **307** passed（结构重整后） |
| Test coverage audit | Partial | 强引用 40/88；P0 缺 reconcile/rag-eval/rollback/mcp — `test_coverage_gaps.md` |
| Wrap-up production smoke | **Pass** | `phase14_wrapup_smoke.json` OVERALL PASS |
| 14-07 production non-empty delta | Open | prepare no_op |

## Active production surface

- Active: `knowledge_units_run_76c6259e_20260712062418` (**30,012** units)
- Composition: expanded run canonical 27,655 + Plan-04 canonical 2,357
- Reason for merge: expanded-only index covered **0/20** frozen gold evidence refs; merge restored **18/20**
- Extraction run: `run_76c6259e9ed09d5b` validated / gate passed

## Wrap-up test summary

| Layer | Result |
|-------|--------|
| `pytest tests -q`（全量） | **307** passed |
| `pytest tests/ -k knowledge` | 151 passed |
| Focused promotion/vector/incremental/gate | 44 passed |
| Ledger + extraction gate | PASS |
| Reconcile active | PASS (30012/30012) |
| Active canary | OK, active_unchanged |
| Automated gap audit | 40/88 strong-ref；11 high gaps |

Reports:
- `integration/analysis/ai_context/phase14_wrapup_test_report.md`
- `integration/analysis/ai_context/phase14_wrapup_smoke.json`
- `integration/analysis/ai_context/phase14_expanded_final_report.json`
- `integration/analysis/ai_context/test_coverage_gaps.md`

## Code fixes during wrap-up (documented)

- `reconcile_knowledge_index.py`: page Chroma IDs (fix limit=10000 false FAIL); eligible = all current canonical
- `promote_knowledge_index.py`: page IDs for checksum on large collections
- `build_knowledge_unit_vector_store.py`: batch Chroma writes (500)
- `build_canonical_knowledge_units.py`: include `current` units in load for full-run canonicalization

## Human verification still needed

1. Optional canary labeling + `--strict`
2. Hybrid quality follow-up toward 0.85 baseline
3. 14-07 real-delta UAT when source changes → close KU-08

## Rollback

```text
python integration/scripts/promote_knowledge_index.py rollback --to previous
```
