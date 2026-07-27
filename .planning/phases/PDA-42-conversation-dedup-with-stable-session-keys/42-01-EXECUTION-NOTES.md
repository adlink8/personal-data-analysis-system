# Phase 42-01 Execution Notes

## Pre-key-change baseline

- `pk-sync conversations --write`: exit 0; normalized snapshot 1,159 sessions / 102,881 messages; canonical old-code rebuild 1,165 sessions / 97,762 messages; `duplicate_source_links=0`。
- `pk-ku inspect`: `source_changed=True`, `new_refs=1,994`, `deleted_refs=12,429`, `affected_subjects=8,860`。
- `pk-ku prepare`: validation passed, `fresh_run_id=ir_ac26ce496b48f398`, `extract_item_count=1,994`, `production_llm_calls=0`。
- Read-only baseline is stored at `var/reports/phase42_baseline.json`; it contains counts and checksums only。

## External quota blocker

- The authenticated executable is `C:\Users\li\google-cloud-sdk\gcloud.bat`; token probe succeeded without recording the token。
- A single minimal Vertex request returned HTTP `429 RESOURCE_EXHAUSTED` with `"Resource exhausted. Please try again later."`。
- The batch was started with four workers and then stopped after no successful items and repeated retryable responses; no candidate units, Chroma writes, active-pointer changes or watermark writes were made by the failed attempt。
- Run remains resumable as `ir_ac26ce496b48f398`; current ledger status was `abstained=4`, `pending=1976`, `in_flight=4`, `retryable=10` when paused。
- `pk-ku doctor --skip-ports` currently fails only at `source_watermarks` because the conversation source watermark is ahead of the committed knowledge watermark. The plan requires the delta to be consumed before the stable-key rebuild, so builder code changes are intentionally not started yet。

## Model switch and resume

- 用户明确授权将模型从 `gemini-3.5-flash-lite` 切换为 `gemini-3.5-flash`，以复用同一 `ir_ac26ce496b48f398` run；未重新 prepare、未改变 provider。
- `gemini-3.5-flash` 最小请求探针返回 HTTP 200；已用 2 workers / 3 秒最小请求间隔恢复批次。
- 恢复后首轮状态检查：`succeeded=15`、`pending=1960`、`retryable=6`、`in_flight=8`；日志已出现成功 units，当前进程仍在运行。

## Resume condition

The lite-model quota blocker was resolved by an explicit user-authorized switch to `gemini-3.5-flash`; the same run was resumed without a second prepare or provider change. Extraction finished with `processed=1,985`, `succeeded=1,641`, `abstained=344` in the final batch log, plus the earlier 4 abstentions in the run ledger, and `terminal_failed=5`. There are no pending, retryable, or in-flight items. `pk-ku extract-gate --run ir_ac26ce496b48f398 --min-yield 0.7` passed snapshot completeness, nonzero output, schema validity, evidence integrity, speaker attribution, privacy, and failure-rate checks, but remains `awaiting_pilot_threshold` because 3 terminal API-error slots and the configured pilot threshold were not satisfied. No promote or watermark write was performed.

## Stable-key implementation and fixture verification

- Commit `a5a93f3` (`feat(42-01): use stable canonical session keys`) adds `(source, source_session_id)` crosswalk matching, deterministic ordering, lifecycle/superseded metadata, and the five stable-key regression fixtures.
- `pytest tests/integration/test_canonical_dedup_stable_keys.py tests/integration/test_agentsview_normalization.py -q`: 20 passed.
- The real dry-run reported `stable_key_matched=281`, `file_hash_confirmed=275`, `file_hash_divergent=6`, `superseded_marked=0`, `unexpected_duplicate_stable_key=0`, `duplicate_source_links=0`.

## First real stable-key rebuild

- `pk-sync conversations --write`: exit 0; normalized snapshot 1,159 sessions / 102,881 messages; canonical output 1,159 sessions / 95,428 messages / 110,456 tool events; `duplicate_source_links=0`.
- Canonical stats: `merged_by_source_mapping=281`, `stable_key_matched=281`, `file_hash_confirmed=275`, `file_hash_divergent=6`, `superseded_marked=0`, `unexpected_duplicate_stable_key=0`, `review_required=0`.
- Immediately after the rebuild, the pre-key canonical generation was fixed at `D:\ADLINK\数据分析\var\backups\agent_conversations_pre42_20260727_154215.sqlite`; read-only counts are 1,165 canonical sessions / 97,762 canonical messages, matching `var/reports/phase42_baseline.json`.
- Zero-duplicate acceptance on `data/canonical/agent/structured/db/agent_conversations.sqlite`:
  - SQL A source-session-to-canonical multiplicity: `0`
  - SQL B active stable-key multiplicity: `0`
  - SQL C duplicate `(canonical_session_id, ordinal)`: `0`
  - SQL D legacy-primary eligible embedded UUID found in AgentsView links: `0` (population: `0`)
- Per 42-01 scope, no post-rebuild `pk-ku prepare`, promote, or watermark write was performed. The expected first-generation source-watermark delta remains for the controlled 42-03 flow.

## 42-02 migration dry-run

- Added `tools/migrations/remap_superseded_session_refs.py` and five isolated unit fixtures; `pytest tests/unit/test_remap_superseded_session_refs.py tests/integration/test_canonical_dedup_stable_keys.py -q`: 10 passed.
- Safety checks passed: `--help` exposes `--write`, `--dry-run`, and `--old-canonical-db`; a missing old DB exits 2 with an explicit precondition error; source scan confirms no literal source-prefix classification, no row deletion SQL, and canonical URI uses `mode=ro`.
- Command: `python tools/migrations/remap_superseded_session_refs.py --old-canonical-db var/backups/agent_conversations_pre42_20260727_154215.sqlite` (default dry-run). Old DB precondition passed with `legacy_sessions=11`, baseline minimum `6`.
- Unified DB SHA-256 before and after dry-run: `FD7471A1CE213DECE8D209285A7C577C856A68A7A061E89D61744ED1AC2C1343` (identical).
- Dry-run machine summary: `remapped_evidence=5`, `remapped_source_ref=5`, `remapped_inventory=0`, `remap_orphans=69`; by table, migration orphans were evidence `35`, source refs `35`, inventory `67`.
- Preexisting orphan reconciliation: evidence-ref population `preexisting_orphans=809`, exactly equal to `phase42_baseline.json` `evidence_refs_unresolved_baseline=809`; other table views were source refs `629` and inventory `995`.
