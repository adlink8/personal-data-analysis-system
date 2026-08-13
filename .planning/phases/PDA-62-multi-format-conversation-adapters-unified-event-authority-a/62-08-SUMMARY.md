---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 08
type: execute
subsystem: canonical v2 activation and rollback
tags: [activation, rollback, legacy-preservation, live, phase62]
dependency-graph: depends_on [62-07]
tech-stack: [python, sqlite3, pk-sync]
key-files:
  - data/canonical/agent/structured/db/agent_conversations.sqlite
  - var/db/personal_system.sqlite
  - src/personal_knowledge/application/conversation/compatibility_projection.py
  - src/personal_knowledge/adapters/conversation_sources/{codex,workbuddy_kimi,gemini}.py
  - .planning/phases/PDA-62-multi-format-conversation-adapters-unified-event-authority-a/62-ACTIVATION-REPORT.json
  - docs/runbooks/product-sync.md
decisions:
  - "Activation preserves pre-existing legacy canonical rows and replaces only the v2 projection of the switched generation (D-18/D-19)."
  - "v2 projection rows carry a `v2|` id prefix (canonical_session_id `v2|cs|…`, message `v2|cm|…`, tool `v2|cte|…`) and `source/primary_source='legacy'` (the live CHECK constraint admits only agentsview|legacy)."
  - "Live export adapters (codex/workbuddy/gemini) map the real nested/epoch shapes; unknown kinds stay unknown_native with honest partial fidelity."
metrics:
  tests: "48 passed (compatibility + sync + generations + agent rollback); doctor 10/10 critical; rag-search 11,370 events"
  activation: "claude generation active; legacy preserved 1159/95428/110456; v2 projection 1/3/0"
  paid_calls: 0
---

# 62-08 SUMMARY — Canonical v2 activation and rollback drill

## 执行结果

在用户 2026-08-13 显式批准（“批准 Phase 62 canonical v2 激活与回滚演练”，仅授权演练、不授权付费提取）后完成：
1. **Task 1 恢复清单**：live canonical 在线备份 + 指纹（`data/staging/v2/recovery-20260813T074207/`），停 Kernel/api_server 消费者，激活前核验 62-07 批准记录与 shadow digest。
2. **Task 2 激活**：stage 4 个有源家族（claude/codex/gemini/workbuddy）→ 激活 claude generation → legacy 保留 + v2 投影共存 → 重启 api_server → doctor 10/10、兼容测试 48、rag-search 11,370 events。
3. **Task 3 回滚演练**：清除 v2 投影 + demote authority（legacy 完整）→ 重新激活（v2 恢复、legacy 仍完整）→ 双向证明可恢复。

## 事故与修复（必须披露）

- **inc-62-08-activation-clears-legacy**：首次激活尝试 2 曾把 live legacy 表清空重写（1159→1 / 95428→3 / 110456→0），已从恢复清单**完整恢复**。根因：`clear_compatibility_projection` 无条件 DELETE 三张 legacy 表，且 62-04/62-07 测试全部在空表上运行。
- **修复（commit 5cb6266）**：v2 投影行改用 `v2|` 前缀 + `clear` 仅删除 `v2|%` 行（legacy 保留）；新增回归测试 `test_activation_preserves_legacy_rows`；codex/workbuddy/gemini 适配器支持真实导出格式（嵌套 payload/sessionId/epoch-ms/content blocks），shadow 覆盖从 1 partial 提升到 1 full/3 partial/0 blocked。
- 投影 source 约束修复（commit f7a15b9）：`primary_source/source` 由 `v2` 改 `legacy`（live CHECK 只允许 agentsview|legacy）。
- **inc-62-07-extract-guard-fallthrough**（62-07 遗留）：live 缺 `ce_candidate_audit` 表使 D-30 付费提取 guard 在 live 上失效；32 items 误标已恢复 pending。62-08 未物化该表（D-30 证据收集暂停）；付费提取仍被 62-06 的类型化拒绝（`LegacyRunSupersededError` / `ViewExtractionBlockedError`）与“无批准不付费”纪律双重封锁。

## Deviations

- 计划 Task 1 验证命令 `pk-sync conversations --event-v2-activation-check ...` 不存在（CLI 实际为 `--v2-activate <id>`）；以 `--v2-activate` 完成激活，激活前以只读探针替代 activation-check。
- 无 CLI rollback 入口；回滚通过 `GenerationLifecycle`/`clear_compatibility_projection` 直接调用（与计划“仅用 Task 1 manifest 回滚”一致，legacy 全程保留）。
- 计划 `files_modified` 提及 `var/db/personal_system.sqlite`：本次未写（62-08 不物化 audit 表；var/db 仅 62-07 的 32 行恢复改动，已核验 24,487 pending）。

## Auth Gates

- 人类审批：62-07 Task 4 记录为 `APPROVED`（2026-08-13 用户批准语），仅授权 v2 激活/回滚演练。
- 付费提取：未授权、未发生（paid_calls=0）。

## Known Stubs

- `ce_candidate_audit` 表在 live canonical 缺失 → D-30 guard 在 live 上无效（记录为已知限制，物化需另行授权）。
- 13 家族 `no_source`（真实会话源工件不在 live cohort 中）；4 有源家族全捕获。

## Threat Flags

- 无。报告 metadata-only、paid_calls=0、legacy 数据全程保留、无付费模型输出。

## Self-Check: PASSED

- [x] `python -m pytest -q tests/contract/test_conversation_v2_compatibility.py tests/integration/test_conversation_v2_sync.py tests/integration/test_conversation_event_generations.py tests/integration/test_agent_conversation_rollback.py` → 48 passed
- [x] `pk-ku doctor --json` → ok, critical 10/10
- [x] `rag-search stats --json` → 11,370 events
- [x] 激活→回滚→再激活 drill：legacy 行数 1159/95428/110456 全程不变；authority active 状态往返正确
- [x] `git diff --check` clean
- [x] paid_calls=0；旧 run 拒绝保持；active KU 空（doctor 通过）
