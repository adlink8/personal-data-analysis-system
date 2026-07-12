# Phase 05 Execution Record

Date: 2026-06-17
Status: Completed

## What shipped

- Wave 3: `tests/test_memory_contracts.py`
  验证 core / CLI / REST / MCP 四层记忆查询契约。
- Wave 1: `integration/scripts/source_adapters/`
  新增 contract、`base.py`、`google_activities.py` 样例 adapter。
- Wave 2: `integration/scripts/memory_governance.py`
  统一 `evidence_ids` / `confidence` / `last_seen` / `source_hash` / `merge_key` metadata。
- Wave 2: `build_memory_store.py` / `build_capability_memory.py` / `build_context_memory.py` / `build_preference_memory.py`
  全部接入 governance metadata。
- Wave 2: `unified_search.py` / `build_profile_from_memory.py`
  增加记忆证据摘要输出。
- Wave 5: `integration/scripts/evaluate_memory_depth.py`
  生成 `integration/analysis/ai_context/memory_depth_readiness.md`。
- Wave 4: README、`integration/README.md`、`.planning/codebase/ARCHITECTURE.md`、`INTEGRATIONS.md`、`TESTING.md`
  已同步到真实代码状态。

## Verification

Executed successfully:

```powershell
python tests\test_memory_contracts.py
python integration\scripts\source_adapters\google_activities.py --limit 2
python integration\scripts\run_pipeline.py --dry-run
python integration\scripts\run_pipeline.py --only 5,6,7,8,9,11,12
python integration\scripts\run_pipeline.py --only 12
python integration\scripts\unified_search.py memory --subject Codex --neighbors 1
python integration\scripts\evaluate_memory_depth.py
git diff --check
```

Observed outputs:

- `tests/test_memory_contracts.py`: 4 tests passed
- `person_profile_v2.md`: includes evidence summaries
- `memory_depth_readiness.md`: generated with candidate / shallow split
- `memory_items.metadata`: governance fields present

## Notes

- Windows GBK console crashed on Unicode checkmark output during execution.
  Fixed by replacing console-only status markers with ASCII `[OK]` / `[ERROR]`.
- Phase 06 should consume `memory_depth_readiness.md` instead of assuming all memory graph edges are deep-ready.
