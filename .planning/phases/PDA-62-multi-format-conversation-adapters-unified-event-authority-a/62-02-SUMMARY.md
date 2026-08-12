---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 02
type: execute
subsystem: conversation adapters
tags: [adapters, jsonl, registry, fidelity, phase62]
dependency-graph: depends_on [62-01]
tech-stack: [python, pytest, sqlite3]
key-files:
  - src/personal_knowledge/adapters/conversation_sources/registry.py
  - src/personal_knowledge/adapters/conversation_sources/jsonl_stream.py
  - src/personal_knowledge/adapters/conversation_sources/codex.py
  - src/personal_knowledge/adapters/conversation_sources/claude_qoder.py
  - src/personal_knowledge/adapters/conversation_sources/pi.py
  - src/personal_knowledge/adapters/conversation_sources/workbuddy_kimi.py
  - src/personal_knowledge/adapters/conversation_sources/copilot.py
  - src/personal_knowledge/adapters/conversation_sources/gemini.py
  - tests/contract/test_conversation_stream_adapters.py
  - tests/fixtures/conversation_sources/
decisions:
  - "Each family keeps its own detector/schema gate and capability/fidelity outcomes (D-02)."
  - "Native turn/DAG/loop/call-result/compaction structure becomes typed relations, never text heuristics (D-12)."
  - "Codex call_id is shared by call and output; make_event_id omits kind when a native id exists, so outputs carry a `#output` disambiguation suffix in their native id."
  - "Copilot tool start/complete share tool_id; completions carry a `#complete` suffix for the same reason."
  - "Registry select_adapter returns the first detector match and never falls back to a generic message parser; vscode-copilot is an alias of the copilot family."
metrics:
  tests: "44 passed (stream adapters) + 15 (unit event contracts) + 24 (snapshots/repository regression) — all green"
  fixtures: "8 redacted synthetic fixtures, one per stream family"
---

# 62-02 SUMMARY — JSON/JSONL/DAG/loop family adapters + registry

## 完成情况

实现并注册了 Phase 62 全部十个 JSON/JSONL/DAG/loop 流式会话家族适配器：
Codex、Claude、Qoder、Pi、Workbuddy、Kimi、Kimi-work、Copilot（+vscode-copilot 别名）、Gemini。
每个家族通过 62-01 的 `AdaptationResult`/`CapabilityDescriptor`/`TypedEvent`/`EventRelation`/`FidelityProfile` 契约产出类型化事件与关系。

### 适配器行为要点

| 家族 | 原生形态 | 关键语义保留 |
|---|---|---|
| codex | JSONL 事件流 | turn ID → `turn_boundary` + `TURN_MEMBERSHIP` 关系；call/output 按 `call_id` 配对为 `CALL_RESULT`；`context_compacted` → `compaction_summary`（非用户消息） |
| claude | JSONL UUID DAG | `parentUuid` → `PARENT_CHILD`；`isSidechain` → `SIDECHAIN`（文件顺序不作为关系依据） |
| qoder | Claude 式 DAG | 复用 DAG 原语；`isCompactSummary` → `compaction_summary` + `COMPACTED_RANGE` |
| pi | JSONL 事件流 | 独立 `compaction` 记录（summary/firstKeptEntryId/tokensBefore）→ `compaction_summary` + `COMPACTED_RANGE` |
| workbuddy | JSONL | reasoning → `reasoning`；call/result 按 `call_id` 配对 |
| kimi/kimi-work | JSONL 循环协议 | turn/loop/task 生命周期 → `turn_boundary`/`loop_boundary`/`file_context`（first-class 剧情提示） |
| copilot/vscode-copilot | JSONL trace | turn start/end + tool 生命周期按 `tool_id` 配对；缺失 complete → 有界 partial fidelity |
| gemini | 单 JSON | 有序 messages → user/assistant 事件；未建模字段经 `native_payload_ref` 按引用保留 |

## Deviations

- **make_event_id 消歧后缀（自环修复）**：62-01 的 `make_event_id` 在存在 native_event_id 时不把 kind 纳入身份；Codex call/output 与 Copilot tool start/complete 共享原生 id，直接构造关系会触发 `self-loop relations are invalid`。在适配器层给 result/complete 事件原生 id 加 `#output`/`#complete` 后缀并配对时剥离。这是适配层正确性修复，未改动 62-01 契约。
- **`_fidelity` override 键类型**：最初 `levels.update(overrides)` 用字符串键与枚举键不匹配导致 override 静默失效；改为 `FidelityDimension[key]` 归一化。
- **detect 扫描全行**：workbuddy marker 位于第 5 行，初版 detect 只探首行；改为扫描全部行。
- **claude/qoder 检测歧义**：两家族结构相同，给 claude 加 `stop_reason`/`isSidechain` marker、qoder 加 `isCompactSummary` marker；kimi/copilot 同改（`loop_iteration`/`context_append`/`task_complete` 区分）。

## Auth Gates

无。本计划零付费：无 LLM/provider/网络调用，未运行 `pk-ku extract`（D-31 保持）。

## Known Stubs

- `registry.py` 只注册 62-02 的十个流式家族；SQLite/目录/部分源家族（zcode/mimo_opencode/antigravity/grok/chatgpt/cursor）由 62-03 实现、62-04 统一注册（计划内依赖，非 stub）。
- gemini 适配器当前无 typed 关系（单 JSON 无原生关系语义），capability 明确声明空关系集。

## Threat Flags

- 无。新增模块零网络端点；fixture 全部手写合成（无真实会话正文）；不触碰 var/data/spikes/tmp。

## Self-Check: PASSED

- [x] `python -m pytest -q tests/contract/test_conversation_stream_adapters.py` → 44 passed
- [x] `python -m pytest -q tests/contract/test_conversation_stream_adapters.py tests/unit/test_conversation_event_contracts.py` → 59 passed
- [x] `python -m pytest -q tests/integration/test_conversation_source_snapshots.py tests/integration/test_conversation_event_repository.py`（相邻回归）→ 24 passed
- [x] `git diff --check` → clean
- [x] D-31 零付费：无 `pk-ku extract`、无 provider/网络代码
