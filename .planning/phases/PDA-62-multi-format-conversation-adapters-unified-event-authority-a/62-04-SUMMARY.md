---
phase: 62-multi-format-conversation-adapters-unified-event-authority-and-replaceable-extraction-views
plan: 04
type: execute
subsystem: conversation adapters
tags: [compatibility-projection, generation-lifecycle, activation, rollback, v2-sync, phase62]
dependency-graph: depends_on [62-02, 62-03]
tech-stack: [python, pytest, sqlite3]
key-files:
  created:
    - src/personal_knowledge/application/conversation/compatibility_projection.py
    - src/personal_knowledge/application/conversation/event_generations.py
    - src/personal_knowledge/application/conversation/v2_sync.py
    - tests/contract/test_conversation_v2_compatibility.py
    - tests/integration/test_conversation_event_generations.py
    - tests/integration/test_conversation_v2_sync.py
  modified:
    - src/personal_knowledge/core/conversation_repository.py
    - src/personal_knowledge/application/conversation/event_repository.py
    - src/personal_knowledge/application/run_pipeline.py
    - src/personal_knowledge/application/sync.py
    - src/personal_knowledge/adapters/conversation_sources/registry.py
    - tests/contract/test_conversation_stream_adapters.py
decisions:
  - "Legacy canonical_sessions/messages/tool_events become a deterministic projection of exactly one active v2 generation; projected message rows come only from message-kind events (reasoning/usage/compaction/boundary/unknown events are reported as excluded, never flattened into user facts)."
  - "GenerationLifecycle is the sole activation owner: stage/validate/activate/rollback; the EventRepository keeps no activation surface (read-only authority) and the new activation-support tables are additive."
  - "Authority pointer holds exactly one active row (demote-then-insert) so a second activation cannot be shadowed by a same-timestamp tie."
  - "Every injected post-authority failure (projection/pointer/version) rolls back the whole transaction and restores the exact prior authority rows, compatibility tables, version/watermark/fingerprint."
  - "pk-sync conversations gains additive --v2-dry-run/--v2-shadow/--v2-activate flags; default behavior is unchanged until Plan 62-08; shadow/activation write only to a caller-supplied shadow DB (default data/staging/v2)."
  - "The 17-family adapter registry is completed (62-03 handoff): zcode/mimo/opencode/antigravity/grok/chatgpt/cursor registered in registry.py."
  - "v2 orchestration was extracted to conversation/v2_sync.py (split before adding a second change reason to the retired run_pipeline.py), keeping the run_pipeline import path as a re-export."
metrics:
  tests: "41 new (10 compatibility + 17 generations + 14 v2 sync); full regression 162 passed across 11 suites; diff --check clean; compileall OK"
---

# 62-04 SUMMARY — deterministic compatibility projections + generation lifecycle + v2 sync orchestration

## 完成情况

把 Phase 62 全部 17 家族适配器接入 `pk-sync conversations` 的 v2 影子编排，建成"确定性兼容投影 seam"（legacy canonical 表 = active v2 generation 的确定性投影）与"唯一 generation 生命周期 owner"（stage→validate→activate→rollback，任一注入故障精确恢复先前权威状态），且默认命令行为与 live canonical 数据完全不变。

## Task 1 — Red → Green：确定性兼容投影 + provider/consumer parity

- `compatibility_projection.py`：`compute_projection`/`build_compatibility_projection`/`write_compatibility_projection`/`clear_compatibility_projection` + `ProjectionFingerprint`（generation lineage digest）。只做 event→legacy 映射，从不激活 generation。
- 投影语义：只有 `user/assistant/developer/system` 事件 → `canonical_messages`；`tool_call/result` → `canonical_tool_events`；reasoning/usage/compaction/boundary/file_context/unknown_native 全部 `excluded`（绝不当用户事实）。每事件至多一行（无双计数）；source ref 稳定指向 native locator；fingerprint 跨 generation 确定性不同。
- `conversation_repository.py`：新增只读 `EventAwareConversationRepository`（typed 事件/关系/dispositions、native-locator 回查、active 投影），旧 `ConversationRepository` 方法继续读 legacy 契约，二者并列不双计数。
- **RED 证据**：`ModuleNotFoundError: ... compatibility_projection` → **GREEN**：Task1 verify 25 passed。

## Task 2 — Red → Green：staging / validation / atomic activation / exact rollback

- `event_generations.py`：`GenerationLifecycle`（prepare/validate/activate/rollback_to）+ `ActivationHooks`（projection_builder/consumer_parity/authority_writer/projection_writer/version_binder 五个注入缝）+ `GenerationActivationError`。
- `event_repository.py`：新增只读 authority/binding 快照与事务绑定的 `write_bindings`/`record_attempt_log`，以及 `ce_activation_bindings`/`ce_activation_log` 两张增量表；仓库本身仍无任何 activation 面（62-01 的"无 activ* 公共方法"回归保持）。
- 故障注入全覆盖：commit 前失败（checksum/stale manifest/unknown adapter/consumer parity）、authority commit 后失败（projection writer/authority writer/version binder 注入抛错）——每次都以单事务回滚恢复先前 authority 行/兼容表/version/watermark/fingerprint 完全一致（`_snapshot` 精确比对）。旧 generation 行与激活审计日志保留不删。
- **RED 证据**：`ModuleNotFoundError: ... event_generations` → **GREEN**：Task2 verify 17 passed。
- 修了 1 个自研 bug（Rule 1）：两代同秒 `active=1` 导致 authority 返回旧代，改为"先 demote 所有 active 再插入"。

## Task 3 — Red → Green：pk-sync conversations v2 dry-run / shadow / activation

- `v2_sync.py`（按 AGENTS.md 规则 6 拆分的新模块）：`probe_conversation_sources`（dry-run 探测全部已注册家族 capability/事件估算，metadata-only）、`shadow_conversation_generation`（捕获→适配→stage 非激活 generation + metadata-only 报告）、`activate_conversation_generation`（仅委托 `event_generations`；uncovered/隐私门禁/unknown family/缺覆盖/stale manifest/checksum 全部 fail-closed；成功后才发无正文 delta）。
- `run_pipeline.py`：仅 re-export 三个公开 seam（保持测试/命令导入路径稳定）。
- `sync.py`：conversations 子命令新增 `--v2-dry-run/--v2-shadow/--v2-activate/--v2-source/--v2-db/--v2-artifact-store/--v2-report/--v2-families`（默认指向 `data/staging/v2`，绝不指向 live canonical）；默认 `pk-sync conversations [--write]` 行为未改（新增 `test_default_flag_surface_unchanged` 断言）。
- **RED 证据**：`ImportError: cannot import name 'activate_conversation_generation'` → **GREEN**：Task3 verify 20 passed（14 新 + 6 rollback 回归）。

## Deviations from Plan

### Auto-fixed Issues

1. **[Rule 1 - Bug] authority 双 active 行遮蔽（Task 2）**
   - `_write_authority` 初版 `INSERT OR REPLACE` 保留旧 `active=1` 行，同秒时间戳下 `authority_generation_id()` 稳定返回旧代；改为"先 `UPDATE ... SET active=0 WHERE active=1` 再插入"。
   - 验证：成功激活/回滚用例转绿；快照恢复测试仍精确通过。

2. **[Rule 1 - Bug] 自研测试断言错误（Task 1/3）**
   - legacy 投影 session 用派生 canonical id 而非 raw v2 session id（`iter_turns` 无返回）；`_make_source` 在部分用例被调用两次导致 `FileExistsError`（`exist_ok=True`）。
   - 属测试自身缺陷，修正测试而非硬改实现。

3. **[Rule 3 - Blocking / 规划交接] 注册 62-03 的七个家族 + 更新过时断言（Task 3 前置）**
   - `registry.py` 只注册了 62-02 的 10 个流式家族，62-03 SUMMARY 明示"62-04 统一注册"；而 Task 3 要求探测全部家族能力。已把 zcode/mimo/opencode/antigravity/grok/chatgpt/cursor 注册进 `registry.py`（`known_families()` 10→17），并把 `test_every_family_has_versioned_capability` 的硬编码家族清单改为 `resolve_family(name) == cap.family`（意图保留、断言泛化）。

4. **[Rule 2 - 架构契约] run_pipeline.py/sync.py 超 500 行 → 拆分 v2_sync.py（Task 3）**
   - `run_pipeline.py`（retired 取证模块）与 `sync.py` 因新增 v2 编排超过 500 行/函数 80 行评审阈值。按 AGENTS.md 规则 6 与工程契约把编排拆到新模块 `conversation/v2_sync.py`（499 行，全函数 ≤80），`run_pipeline.py` 仅 re-export 三个公开 seam，`sync.py` 引用 `add_conversations_v2_args`/`cmd_conversations_v2`。未改任何既有生产逻辑。

## Auth Gates

无。零付费：全部测试本地确定性（tmp_path），无 LLM/provider/网络调用，未运行 `pk-ku extract`（D-31 保持）。

## Known Stubs

无。`probe` 对多文件/非单一文件家族的事件估算为 0 是诚实语义（shadow 中此类家族为 `blocked:unsupported_artifact_set`，非 stub）；chatgpt 家族天然 partial 由 adapter fidelity 表达（62-03 既有语义）。

## Threat Flags

无。新增模块零网络端点、无 provider 代码（grep 验证）；live `agent_conversations.sqlite`（mtime 2026-07-27）与 `var/db/personal_system.sqlite` 未被本计划代码写（测试全 tmp_path，`data/staging/v2` 未产生）；`ce_activation_log` 仅含 metadata；shadow 报告仅含哈希/计数/fidelity，测试断言不含正文文本。

## Self-Check: PASSED

- [x] Task 1 RED：`ModuleNotFoundError: ... compatibility_projection`；GREEN：`python -m pytest -q tests/contract/test_conversation_v2_compatibility.py tests/unit/test_conversation_repository.py tests/contract/test_agentsview_downstream_contracts.py` → 25 passed
- [x] Task 2 RED：`ModuleNotFoundError: ... event_generations`；GREEN：`python -m pytest -q tests/integration/test_conversation_event_generations.py` → 17 passed
- [x] Task 3 RED：`ImportError: cannot import name 'activate_conversation_generation'`；GREEN：`python -m pytest -q tests/integration/test_conversation_v2_sync.py tests/integration/test_agent_conversation_rollback.py` → 20 passed
- [x] 全量：11 套件共 162 passed（含 62-01 仓库 12、62-02 流式适配器、62-03 存储适配器+隐私负面、rollback、run_pipeline contracts、conversation repository）
- [x] `git diff --check` → clean（CRLF warning 仅为 autocrlf 提示）
- [x] `python -m compileall` 新模块 → OK
- [x] 新生产文件均 ≤500 行、函数 ≤80 行（实测 486/499/503/446/472/375/374/500）
- [x] 无网络/provider/付费调用代码；live canonical 与 var/db 未写；测试全 tmp_path
- [x] 默认 `pk-sync conversations [--write]` 行为未变（flag 全新增，`test_default_flag_surface_unchanged` 验证）

## Verification Command Results

| Command | Status | Result |
|---|---|---|
| Task1: `pytest -q tests/contract/test_conversation_v2_compatibility.py tests/unit/test_conversation_repository.py tests/contract/test_agentsview_downstream_contracts.py` | PASSED | 25 passed |
| Task2: `pytest -q tests/integration/test_conversation_event_generations.py` | PASSED | 17 passed |
| Task3: `pytest -q tests/integration/test_conversation_v2_sync.py tests/integration/test_agent_conversation_rollback.py` | PASSED | 20 passed |
| Adjacent regressions: event_repository + stream/store adapters + privacy + run_pipeline contracts | PASSED | 100 passed |
| `git diff --check` | PASSED | clean |
| `python -m compileall` new modules | PASSED | OK |
| live canonical / var/db untouched; no data/staging/v2 produced; no provider/network code | PASSED | verified |

## 协调者复核点

- **未激活 live**：本计划所有激活只发生在 tmp_path 影子库；`pk-sync conversations` 默认路径、live `agent_conversations.sqlite`、`var/db/personal_system.sqlite` 完全未触碰。
- **默认 sync 行为未变**：v2 flag 全新增且 opt-in，`--write` 默认路径保持原样（62-08 才会改变默认）。
- **旧 generation 保留**：激活/回滚只改 authority 指针、投影表与 bindings；旧 generation 行与 `ce_activation_log` 审计行永不删除。
- **可复查点**：Task 3 把 62-03 七家族注册进 `registry.py` 并泛化了 `test_conversation_stream_adapters.py::TestRegistry` 的一个过时断言；`run_pipeline.py` 只 re-export（`v2_sync.py` 为真实实现）。
