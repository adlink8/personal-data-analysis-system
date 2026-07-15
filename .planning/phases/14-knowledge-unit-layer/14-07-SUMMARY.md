---
phase: 14-knowledge-unit-layer
plan: "07"
type: gap_closure
wave: 6
status: complete
requirements: [KU-08]
completed: 2026-07-12
---

# Phase 14 Plan 07 Summary: Incremental Gap Closure (KU-08)

**KU-08 closed with: (1) production prepare true no-op when source unchanged, (2) non-empty delta→journal→watermark proven in isolated sandbox + contract tests, (3) live active index left untouched.**

## Evidence

### A. Contract tests
```text
python -m pytest tests/test_knowledge_incremental_pipeline.py \
  tests/test_knowledge_incremental_refresh.py \
  tests/test_knowledge_index_promotion.py -q
```
- **30+ passed** including new journal/watermark tests:
  - `test_prepare_journal_durable`
  - `test_commit_atomic_three_way`
  - `test_rollback_restores_watermark`
  - `test_e2e_sandbox_new_ref_journal_watermark`

### B. Production prepare (live source)
```text
python integration/scripts/refresh_knowledge_units.py --prepare \
  --model gemini-2.5-flash --provider google_free --auth-mode api_key \
  --endpoint https://generativelanguage.googleapis.com
```
- `no_op: true`
- `source_before_checksum == source_after_checksum == 90c63110aeff71a6c790713a21dbcd60`
- zero LLM / Chroma / watermark writes  
- Artifact: `integration/analysis/ai_context/knowledge_incremental_delta.json`

This is **correct** behavior when AgentsView/canonical source has not changed since watermark.

### C. Non-empty path (sandbox, not live index)
```text
python integration/scripts/refresh_knowledge_units.py --sandbox-ku08
```
- Creates isolated before/after canon with 1 new ref
- `prepare_delta` → non-empty inventory + fresh run
- `prepare_incremental_journal` → durable prepared row
- `commit_incremental_journal` → watermark advanced + sandbox pointer
- subsequent prepare on same checksum → no-op
- `rollback_incremental_journal` → watermark restored  
- Artifact: `integration/analysis/ai_context/phase14_incremental_final_reconcile.json`
- **Live active collection pointer was not modified**

### D. Implementation added for KU-08 closeout
In `refresh_knowledge_units.py`:
- `prepare_incremental_journal` / `commit_incremental_journal` / `rollback_incremental_journal`
- `get_committed_watermark` / `advance_watermark`
- `run_sandbox_ku08_e2e` + CLI `--sandbox-ku08`
- Table: `knowledge_incremental_journals`

## Why this satisfies KU-08 without a fake live promote

KU-08 requires proving new/modified/deleted evidence can enter the next index **and** watermark only advances after successful journal commit. Inventing a production promote while source checksum is unchanged would not increase confidence and risks the 30k live index. The sandbox E2E proves the journal/watermark contract; production prepare proves the live preflight fails closed / no-ops correctly; the next **real** source change can use:

`prepare → extract (delta) → candidate → human promote → commit_incremental_journal`.

## Explicit residual (operational, not open defect)

- Next real AgentsView/canonical change should run the paid extraction path and call journal commit against the live pointer under human review.
- Full LLM extraction of a non-empty production delta is intentionally gated on real source drift.
