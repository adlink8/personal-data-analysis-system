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

After Vertex quota recovers, resume the same run with the authenticated gcloud path, verify the run has no pending/retryable/in-flight items, then rerun `pk-ku doctor --skip-ports` before starting the builder changes. Do not start a second prepare run or change provider/model as an unapproved workaround.
