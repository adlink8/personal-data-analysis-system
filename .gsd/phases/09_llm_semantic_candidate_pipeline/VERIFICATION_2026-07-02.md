# Phase 09 Verification - 2026-07-02

## Verdict

**PASS - bounded live LLM verification**

Phase 09 的真实 LLM 分支已用 OpenAI-compatible endpoint 和 `gpt-5.4` 跑通 bounded sample。验证范围是候选生成、候选抽取、repair loop、promotion gate、apply dry-run 和回归测试；不是全量无上限重跑。

## What Was Verified

1. **LLM graph candidate proposal**
   - 命令：
     ```powershell
     python integration\scripts\build_graph_relation_candidates_v2.py --write --limit 2 --top-k 1 --model gpt-5.4 --temperature 0.2
     ```
   - 结果：
     - `llm_status=live_api_key_present`
     - `coarse_packages=1`
     - `llm_proposed=1`
     - `schema_rejected=0`
     - `evidence_rejected=0`
     - `written_candidates=1`
   - 报告：
     - `integration/analysis/ai_context/graph_relation_candidate_proposals_report.json`
     - `integration/analysis/ai_context/graph_relation_candidate_proposals_report.md`

2. **Evidence bundle path**
   - 命令：
     ```powershell
     python integration\scripts\build_memory_evidence_bundles.py --write --limit 100
     ```
   - 结果：
     - `bundle_count=100`
     - `accepted_graph_edge=19`
     - `conversation_turn=41`
     - `unified_event=40`
     - `all_have_evidence_refs=True`
     - `all_have_source_refs=True`

3. **LLM memory candidate extraction**
   - 命令：
     ```powershell
     python integration\scripts\extract_memory_candidates_from_bundles.py --dry-run --limit 2 --model gpt-5.4 --temperature 0.2
     ```
   - 结果：
     - `llm_status=live_api_key_present`
     - `bundle_count=2`
     - `candidate_count=1`
     - `written_count=0`
     - `llm_error_count=0`
     - `schema_rejected_count=0`
     - `evidence_rejected_count=0`
   - 说明：本步骤只 dry-run，不写入 `memory_promotion_candidates`。

4. **Gate repair loop**
   - 命令：
     ```powershell
     python integration\scripts\repair_memory_promotion_candidates.py --dry-run --limit 2 --model gpt-5.4 --temperature 0
     ```
   - 结果：
     - `llm_status=live_api_key_present`
     - `processed_count=2`
     - `reject_count=2`
     - `blocked_count=0`
     - `invalid_output_count=0`
   - 说明：repair loop 只产出审计报告，不写长期记忆表。

5. **Promotion gate and apply dry-run**
   - 命令：
     ```powershell
     python integration\scripts\build_memory_promotion_candidates.py --write
     python integration\scripts\evaluate_memory_promotion_candidates.py --write
     python integration\scripts\apply_memory_promotions.py --dry-run --approved-only
     ```
   - 结果：
     - `memory_promotion_candidates=19`
     - `legacy_evidence_candidate=0`
     - `approved_count=0`
     - `auto_approval_eligible_count=0`
     - `long_term_tables_changed=false`

## Regression Tests

Passed:

```powershell
python -m unittest tests.test_graph_relation_candidates_v2 tests.test_memory_evidence_bundles tests.test_memory_candidate_extraction tests.test_memory_gate_repair_loop tests.test_memory_promotion_candidates tests.test_memory_promotion_review
python tests\test_memory_contracts.py
python integration\scripts\run_pipeline.py --dry-run
git diff --check
```

Observed results:

- Phase 09 unit tests: `32/32 OK`
- Memory contract tests: `4/4 OK`
- `run_pipeline.py --dry-run`: listed the existing 12-step pipeline without executing destructive rebuilds
- `git diff --check`: only Windows LF/CRLF warnings, no whitespace errors

## Database Boundary Check

Final observed counts:

| Table / Check | Count |
| --- | ---: |
| `memory_items` | 194 |
| `memory_links` | 1478 |
| `memory_relations` | 27 |
| `memory_evidence_bundles` | 100 |
| `graph_relation_candidate_proposals` | 101 |
| `graph_relation_candidates` | 4653 |
| `memory_promotion_candidates` | 19 |
| `legacy_evidence_candidate` candidates | 0 |
| `llm_memory_candidate` persisted candidates | 0 |
| live graph proposals | 1 |

Long-term memory tables remained unchanged during apply dry-run:

```text
memory_items: 194
memory_links: 1478
memory_relations: 27
```

## Fixes Made During Verification

Live testing found three reliability gaps that were fixed before the final PASS:

1. `extract_memory_candidates_from_bundles.py` and `repair_memory_promotion_candidates.py` now reuse the same OpenAI-compatible client construction as `build_conversation_summary.py`, including the User-Agent adaptation needed by the configured endpoint.
2. `build_memory_promotion_candidates.py` no longer drops the entire `memory_promotion_candidates` table. It creates the table if needed and only replaces `source_system='graph_relation_candidate'` rows.
3. `extract_memory_candidates_from_bundles.py` no longer clears prior `llm_memory_candidate` rows when live LLM calls or top-level schema gates fail without producing replacement candidates.
4. `repair_memory_promotion_candidates.py` now accepts semantically equivalent allowed refs returned as original ref objects, accepts schema-compatible `candidate_claim`, and permits conservative `final_score` only when it does not increase the original score.
5. `parse_hint_memory_id()` no longer guesses the first allowed memory id when a hint does not explicitly mention one.
6. `apply_memory_promotions.py` now reports the actual input promotion report path when callers pass a custom report file.

Regression coverage was added for each fix.

## Remaining Scope Boundary

- This verification used bounded samples, matching Phase 09's stated non-goal of avoiding a large full rerun.
- No automatic long-term memory apply occurred.
- `llm_memory_candidate` rows were validated in dry-run only; persisting them should remain an explicit follow-up decision.
