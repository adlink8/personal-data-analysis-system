# PDA-5a: L2 Dedup — Verification Results

Date: 2026-08-11

## 1. Fix applied (5a.2) — 落库去重 (insert-time dedup)

File changed: `src/personal_knowledge/application/knowledge/extract_knowledge_units_l2_session.py`

- New `_dedup_key(unit_type, subject, answer)`: exact-duplicate key identical to
  `extraction_quality_eval.duplication()` (`unit_type|subject.strip().lower()|answer[:120]`).
- New `_load_session_l2_keys(con, source_session_id)`: loads active L2 dedup keys
  already stored for the real session (any run, status staging/current/validated).
- In `_commit`, before each insert: if the unit's dedup key already exists for the
  same source session → skip insert, count `units_dropped_duplicate`. After a kept
  insert, the key is added to the local set so within-window LLM repetition is also
  caught.
- Job status: when all units are dropped as exact duplicates, job is marked
  `succeeded` with `unit_count=0` and last_error explaining the drop (not
  `abstained`), preserving accurate run stats.
- New stats counter `units_dropped_duplicate`.

Idempotency: window hash, cache key, and unit_id derivation are unchanged; the dedup
is a pure function of (input window, current DB state) → re-running the same input
yields the same stored rows.

## 2. Existing duplicates (5a.3) — mark, never delete

New `mark_l2_duplicates(db_path, write=False)` + CLI `--mark-duplicates [--write]`.

Reproduces the extraction_quality duplication scan over active L2 units
(ORDER BY unit_id) and marks the second+ occurrence of each exact
`unit_type|subject|answer[:120]` key as `lifecycle='deprecated'`, with
`supersedes_id` pointing to the first-seen representative. No rows deleted;
evidence_quote / source_message_ref / source_session_id / canonical member links
all preserved.

Applied to live DB (`var/db/personal_system.sqlite`):

| Metric | Before | After |
|---|---|---|
| L2 units lifecycle=deprecated | 3 | 51 |
| L2 units lifecycle=current (active) | 812 | 764 |
| Duplicate units found | 49 | 49 |
| Active (lifecycle=current) exact duplicates | 49 | **0** |

Re-running the marking is idempotent: `already_deprecated=49, to_mark=0, writes=0`.

Note on the extraction_quality_v1 metric: `extraction_quality_eval.py` computes
duplication over all units with `status IN ('current','staging','validated')`
regardless of lifecycle, so the raw report number stays 49/815 for the deprecated
rows. Active knowledge (lifecycle=current) now has **0 exact duplicates**; and any
future L2 run (same or new session window) will not insert new exact duplicates
thanks to 5a.2. The eval file was intentionally not modified (out of scope:
"只改 L2 抽取相关文件").

## 3. Test results

Command: `python -m pytest tests/ -q -k "l2 or knowledge or eligibility" --tb=no`

Result: **375 passed, 5 failed (all pre-existing infrastructure/dependency failures)**

The 5 failures are unrelated to this change (verified via `git diff --stat` — the
files involved are untouched):

1. `tests/contract/test_knowledge_search_contracts.py` (4 tests): require a live
   Chroma server at `127.0.0.1:8001`; the server is not running in this environment
   (ConnectionError, connection refused). Offline golden dependency unavailable.
2. `tests/governance/test_knowledge_sqlite_policy.py::test_knowledge_write_paths_use_fk_connection_factory`:
   pre-existing violation flagged on `promote_units.py:64-65` (`sqlite3.connect`),
   a file not touched by this work.

Focused suites, all green:
- `tests/unit/test_knowledge_l2_session_extract.py` (incl. new tests for
  `_dedup_key`, `_load_session_l2_keys`, `mark_l2_duplicates` dry-run + write +
  idempotency)
- `tests/unit/test_l2_injection_dedup.py`
- `tests/unit/test_knowledge_eligibility.py`
- `tests/unit/test_knowledge_unit_extraction.py`
- `tests/unit/test_knowledge_unit_rag_eval.py`
- `tests/unit/test_knowledge_unit_eval_dataset.py`
- `tests/integration/test_knowledge_eval_extraction.py` (live reconcile invariant
  `total_l2_status_current == sum_run_units` still holds — marking used lifecycle,
  not status)

## 4. End-to-end dedup simulation

Simulated the exact root-cause scenarios against isolated temp DBs with a stubbed
LLM returning the identical unit per run:

- **Cross-run (pilot+full)**: run 1 inserts 1 unit; run 2 over the same session
  → `units_dropped_duplicate=1`, zero new rows inserted. Total L2 rows stays 1.
- **Within-window LLM repetition**: one window whose LLM output contains the same
  unit twice → 1 kept, 1 dropped as duplicate. Total L2 rows stays 1.

## 5. File changes

- `src/personal_knowledge/application/knowledge/extract_knowledge_units_l2_session.py`
  (+134/-6)
- `tests/unit/test_knowledge_l2_session_extract.py` (+134)
- `.planning/phases/PDA-5-quality-close/PDA-5a-l2-dedup-root-cause.md` (analysis)
- `.planning/phases/PDA-5-quality-close/PDA-5a-verification.md` (this file)

No git commit made (per constraints). No prompt files or eval files changed.
