# PDA-5a: L2 Knowledge Extraction Duplication — Root Cause Analysis

Date: 2026-08-11
Author: gsd-executor (data quality agent)
Scope: L2 (session-window) knowledge unit extraction duplication

## Summary

`extraction_quality_v1.json` (var/reports/analysis/ai_context/extraction_quality_v1.json)
reports L2 duplication rate = **6.01% (49/815)**, vs L1 = **1.76% (569/32398)**.
Duplication metric definition (from `src/personal_knowledge/evaluation/extraction_quality_eval.py`):

```python
key = f"{unit_type}|{subject.strip().lower()}|{answer.strip().lower()[:120]}"
```

i.e. exact collision on unit_type + normalized subject + answer prefix (120 chars).
This analysis re-computed the metric against the live DB (`var/db/personal_system.sqlite`)
and reproduced exactly 49 duplicate L2 units (unit_id `l2|…`).

## Root Cause: All 49 duplicates are within the SAME session

Classification of all 49 duplicate pairs (by first-seen vs second-seen unit):

| Class | Count | % |
|---|---|---|
| Same session, **different run** | 47 | 96% |
| Same session, **same run** | 2 | 4% |
| Cross-session (L2 vs L2) | 0 | 0% |
| Cross-layer (L1 vs L2) | 0 | 0% |

Key finding: **0 cross-session and 0 L1↔L2 collisions**. L2 does not duplicate L1;
the duplication is entirely an L2-internal same-session phenomenon.

## Primary cause (47/49, 96%): Same session re-extracted in a second L2 run

Two L2 extraction runs exist in `knowledge_build_runs` (both `v1_session_window`,
model `gemini-2.5-flash`):

| run_id | generated_at | L2 units | sessions |
|---|---|---|---|
| `2a63b7e98fd3454c1aae3deedcdf038d` (pilot) | 2026-07-12T13:56:16Z | 47 | 14 |
| `205bff9560b915508f343aebc0fe4b0b` (full) | 2026-07-12T13:58:56Z | 768 | 192 |

The 14 pilot sessions are a strict subset of the 192 full-run sessions (overlap = 14).
Both runs built the same user-message window per session and called the LLM with the
same prompt, so the same cross-turn knowledge units were produced twice.

Why does the DB then hold two rows instead of one? Because `unit_id` is derived from
`run_id`:

```python
unit_id = "l2|" + sha256(f"{run_id}|{session_id}|{ordinal}|{subject}|{answer}")[:28]
```

A different `run_id` → different `unit_id` → `INSERT OR REPLACE` inserts a **new row**
instead of replacing. There is no content-level de-dup at insert time: nothing checks
"does an identical (session, unit_type, subject, answer-prefix) row already exist?".

Evidence: all 47 cross-run pairs share the same `source_session_id`, and the two
runs' session sets overlap exactly on those 14 sessions.

## Secondary cause (2/49, 4%): LLM repeats the same conclusion inside one window

Session `cs|793b51091ab7dec35a91fa751c6ae45b` (run `205bff…`) produced **three** units
with identical `subject='项目三'` and identical `answer='需要新建一个issue来记录和跟踪'`
in a single window response, each backed by a different evidence quote from the same
window. Because `unit_id` includes the ordinal, each occurrence gets a different id and
all three are inserted. This is LLM output duplication within one window.

## Why the existing `duplicate_of` mechanism did not prevent this

- The two runs used `v1_session_window` prompt, which has **no injection block** and
  no `duplicate_of` field in its schema (v2 only).
- Even under v2, `validate_duplicate_of` only accepts ids that appear in the injected
  "已有知识清单" (built from canonical `SubjectIndex`). Same-run, same-window duplicates
  are never in that list, so nothing de-dups them.
- The eval metric counts all rows with `status IN ('current','staging','validated')`
  regardless of `lifecycle`, so marking rows `lifecycle='deprecated'` does NOT remove
  them from the duplication numerator (see 5a.3 notes).

## L1 vs L2 rate comparison

- L1 (1 message = 1 LLM call) duplicates are overwhelmingly **cross-message /
  cross-session** restatements of the same subject; the 1.76% rate is considered
  acceptable and is largely inherent to the per-message design.
- L2's 6% is **not** an L1 problem; it is the same-session double-insert described
  above. A same-session exact duplicate adds zero new knowledge.

## Recommended Fix (chosen: 落库去重, option b)

Insert-time content dedup in `extract_knowledge_units_l2_session.py::_commit`:
before inserting each unit, check whether an identical
`(source_session_id, unit_type, normalized subject, normalized answer-prefix)` row
already exists among active L2 units (any run). If yes → **skip insert** (do not
create the new row), count in `stats["units_dropped_duplicate"]`.

This is:
- **Idempotent** — same input window + same DB state → same outcome (window hash,
  cache, unit_id derivation all unchanged).
- **Fail-safe** — never deletes, never mutates existing rows; only refuses to insert
  a new exact duplicate.
- **Evidence-chain preserving** — quote verification (`_evidence_supported`,
  `_best_message_for_quote`) is untouched; evidence rows only written for kept units.
- Minimal — no prompt text change (prompt hash stays stable → response cache intact),
  no schema change, no dependency on LLM compliance.

The 49 existing duplicates are handled separately in 5a.3 (mark, never delete).

## Scope Boundary

- Only `extract_knowledge_units_l2_session.py` (+ its tests) are modified.
- `extraction_quality_eval.py`, prompt files, canonical merge, vector store are
  untouched.
- No git commit is made.
