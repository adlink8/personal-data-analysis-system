---
phase: 14-knowledge-unit-layer
plan: "08-l2-session"
status: complete
completed: 2026-07-12
type: dual_pass_extraction
---

# L2 Session-Window Dual-Pass Extraction Summary

## What ran

**L2** = second pass over multi-message sessions (not whole-history dump; chronological user window, max 12k chars).

| Item | Value |
|------|-------|
| Script | `integration/scripts/knowledge/extract_knowledge_units_l2_session.py` |
| Prompt | `prompts/knowledge_unit_extractor/v1_session_window.md` |
| Full run_id | `205bff9560b915508f343aebc0fe4b0b` |
| Pilot run_id | `2a63b7e98fd3454c1aae3deedcdf038d` |
| Model | `gemini-2.5-flash` |
| Eligible sessions (≥2 user msgs) | 228 |
| Succeeded | 192 |
| Abstained | 13 |
| Terminal failed | 23–24 |
| **Units written (staging)** | **768** |
| Evidence drops | 0 |
| Elapsed | ~20 min |
| Report | `integration/analysis/ai_context/knowledge_l2_session_extract_report.json` |

## Design

1. **L1** (existing): 1 message → 1 LLM call → production 30k KU (unchanged).
2. **L2** (this): 1 session window → 1 LLM call; `evidence_quote` must match a `cm|` in the window.
3. Units stored as `unit_id` prefix `l2|…`, `status=staging`, `run_id` = L2 run.
4. **Not yet** merged into `canonical_knowledge_units` / active Chroma (separate promote).

## Commands

```powershell
# dry-run
python integration/scripts/knowledge/extract_knowledge_units_l2_session.py --dry-run

# full write
python integration/scripts/knowledge/extract_knowledge_units_l2_session.py --write --model gemini-2.5-flash --workers 4

# status
python integration/scripts/knowledge/extract_knowledge_units_l2_session.py --status 205bff9560b915508f343aebc0fe4b0b
```

## Next (optional)

- Merge L2 staging into canonical (dedupe vs existing 30k) → candidate reindex → eval → promote.
- Retry terminal_failed jobs with `--resume`.
