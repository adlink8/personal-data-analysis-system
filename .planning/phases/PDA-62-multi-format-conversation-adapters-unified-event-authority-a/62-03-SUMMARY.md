---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 03
type: execute
subsystem: conversation adapters
tags: [adapters, sqlite, privacy, fidelity, phase62]
dependency-graph: depends_on [62-01]
tech-stack: [python, pytest, sqlite3]
key-files:
  - src/personal_knowledge/adapters/conversation_sources/zcode.py
  - src/personal_knowledge/adapters/conversation_sources/mimo_opencode.py
  - src/personal_knowledge/adapters/conversation_sources/antigravity.py
  - src/personal_knowledge/adapters/conversation_sources/grok.py
  - src/personal_knowledge/adapters/conversation_sources/chatgpt.py
  - src/personal_knowledge/adapters/conversation_sources/cursor.py
  - src/personal_knowledge/adapters/conversation_sources/snapshots.py
  - tests/contract/test_conversation_store_adapters.py
  - tests/security/test_conversation_source_privacy.py
decisions:
  - "SQLite adapters read ONLY the allowlisted filtered artifact; credential/account/token/auth tables are dropped before publish and additionally VACUUMed so excluded bytes are not recoverable (D-08 byte-level)."
  - "Grok directory capture uses an explicit file allowlist; summary-only fidelity is honest partial, never complete."
  - "ChatGPT exposes a compatibility-observation result bound to the AgentsView snapshot with native reconstruction unavailable (D-14); never fabricates a transcript."
  - "Cursor versioned schema probe distinguishes supported thread/message stores from attribution-only databases; unsafe/ambiguous stores fail closed."
  - "Families mimo/opencode share parser primitives but keep separate capability contracts."
metrics:
  tests: "34 passed (store adapters + privacy) + 12 (snapshots regression) — all green"
  families: "zcode, mimo, opencode, antigravity, grok, chatgpt, cursor"
---

# 62-03 SUMMARY — SQLite / directory / partial-source adapters + privacy negatives

## 完成情况

实现了 Phase 62 剩余七个会话源家族的适配器：ZCode、MimoCode、OpenCode、Antigravity（SQLite），Grok（多文件目录），ChatGPT（部分源兼容观察），Cursor（版本化发现）。所有适配器消费 62-01 的 `AdaptationResult`/`TypedEvent`/`FidelityProfile` 契约，并新增隐私负面测试套件。

### 适配器行为要点

| 家族 | 原生形态 | 关键语义 |
|---|---|---|
| zcode | SQLite virtual locator | trace/turn/part/usage 保留；trace id 仅作会话身份（D-20）；text/reasoning/tool/step/compaction → 类型化事件 + `TURN_MEMBERSHIP` |
| mimo / opencode | SQLite（含敏感相邻表） | session/message/part 关系；reasoning → `reasoning`；共享解析原语但独立 capability 契约 |
| antigravity | SQLite trajectory store | trajectory/step/subtrajectory 层级 → `PARENT_CHILD`/`SUBAGENT` 关系；非散文 step → 显式 partial transcript fidelity |
| grok | 多文件会话目录 | summary/chat_history/compaction/subagents 跨文件关系 → `SOURCE_SESSION_CROSSWALK`；仅 summary 时 fidelity=partial |
| chatgpt | AgentsView rows（无原生路径） | 兼容观察结果，native reconstruction=unavailable，fidelity 永不全满（D-14） |
| cursor | 机器本地 project/database | 版本化 schema probe（v1: threads,messages）；仅归因库/歧义 store fail-closed blocked |

## Deviations

- **`snapshots.py` VACUUM（隐私正确性修复，Rule 2）**：`_filtered_backup` 只 DROP 非 allowlist 表，freed pages 残留原始凭据字节（canary 测试字节级检出）。在 DROP 后加 `VACUUM` 重写数据库，使排除的凭据数据从发布 artifact 中不可恢复（D-08 字节级）。62-01 快照测试 12/12 回归通过。

## Auth Gates

无。零付费：无 LLM/provider/网络调用，未运行 `pk-ku extract`（D-31 保持）。

## Known Stubs

- `registry.py` 尚未注册 62-03 的七家族（由 62-04 统一注册）。
- cursor 仅支持 v1 probe（threads/messages）；其他版本检测到但不支持 → fail-closed blocked（诚实部分/阻塞语义，非 stub）。

## Threat Flags

- 无。隐私负面测试证实：forbidden tables/columns 的 canary 值在事件、manifest、artifact 字节中均不可达；声明 forbidden 表即失败关闭；路径逃逸被拒；WAL 库经 online backup 一致捕获。

## Self-Check: PASSED

- [x] `python -m pytest -q tests/contract/test_conversation_store_adapters.py tests/security/test_conversation_source_privacy.py` → 34 passed
- [x] `python -m pytest -q tests/integration/test_conversation_source_snapshots.py`（回归）→ 12 passed
- [x] `git diff --check` → clean
- [x] D-31 零付费：无 `pk-ku extract`、无 provider/网络代码
