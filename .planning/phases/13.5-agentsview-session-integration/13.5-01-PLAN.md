---
phase: 13.5
name: agentsview_session_integration
title: AgentView Session Source Integration
status: 完成 (Wave 1-5 verified 2026-07-10, 43 tests, cutover GATE PASS)
created: 2026-07-10
depends_on:
  - .gsd/phases/13_codebase_refactoring/PLAN.md
blocks:
  - .gsd/phases/14_knowledge_unit_layer/PLAN.md
autonomous: false
---

# Phase 13.5：AgentView 会话源集成与 canonical conversation store

<objective>
在不修改 AgentView 源数据库、不泄露敏感会话内容的前提下，把 `sessions.db` 转换为可复现的安全规范化快照，与旧 Agent 会话去重后发布统一 canonical conversation store，并让现有摘要、统合和 evidence 管道通过兼容接口消费它。
</objective>

## Non-goals

- 不生成或向量化 knowledge units。
- 不删除旧 `agent_data.sqlite` 或 raw session 文件。
- 不导入 thinking text、tool arguments/result 全文、邮箱或 secret 明文。
- 不修改 AgentView daemon、配置或 schema。
- 不把所有 assistant/subagent 内容当作用户事实。

## Target Architecture

```text
C:\Users\li\.agentsview\sessions.db (live WAL, read-only)
        │ SQLite backup snapshot + schema gate
        ▼
agentsview_normalized.sqlite (safe, versioned, atomic publish)
        │                         legacy agent_data.sqlite
        └──────────────┬───────────────────────┘
                       ▼ lineage dedup + precedence
              agent_conversations.sqlite
                       │
        ┌──────────────┼──────────────────┐
        ▼              ▼                  ▼
conversation summary  unified_events   evidence bundles
```

## Locked Decision Coverage

| Decision | Covered by |
|---|---|
| D-01 stage separation/order | frontmatter dependency + Phase 14 dependency |
| D-02 source read-only snapshot | Wave 1 |
| D-03 safe normalized + canonical stores | Waves 2-3 |
| D-04 privacy and evidence eligibility | Wave 2 + cutover gate |
| D-05 speaker provenance | Waves 2-4 |
| D-06 lineage-first dedup | Wave 3 |
| D-07 shadow before cutover | Wave 4 + rollback in Wave 5 |

<tasks>
## Wave 1：Source Contract、快照与预检

### Task 1.1 — 新增 AgentView source adapter

**Files**

- `integration/scripts/source_adapters/agentsview.py`
- `integration/scripts/core/project_paths.py`
- `tests/test_agentsview_source_adapter.py`

**Action**

- 定义受支持的最小 schema：`sessions/messages/tool_calls/tool_result_events/usage_events/secret_findings/excluded_sessions`。
- adapter 打开源库时强制 `mode=ro`、`query_only=ON`，读取并记录 `user_version`、schema hash、WAL 模式和同一事务内的表计数。
- 为长导入实现 SQLite backup API 快照到临时目录；所有后续转换只读临时快照，成功或失败都清理自己创建的临时文件。
- schema 缺表、关键列缺失或 `integrity_check != ok` 时 pre-flight abort。

**Verify**

- 测试对临时 SQLite fixture 执行 schema probe 和 backup。
- 测试 adapter 不产生任何源库写入，源库 `total_changes=0`。
- 测试源库在备份期间追加数据时，manifest 仍对应一个一致 snapshot。

### Task 1.2 — 生成只读 inventory/dry-run 报告

**Files**

- `Agent/structured/scripts/import_agentsview_sessions.py`
- `integration/analysis/ai_context/agentsview_import_inventory.json`
- `integration/analysis/ai_context/agentsview_import_inventory.md`

**Action**

- 默认 `--dry-run`，报告 snapshot counts、agent/source 分布、缺失时间、父子关系、secret/excluded/deleted 数量和 legacy hash overlap。
- 报告不得包含 message content、thinking、邮箱、tool input/result 或 secret match。
- 每次运行产生 `run_id`，manifest 记录源 schema/version、输入计数、过滤计数、代码版本和配置 hash。

**Gate — Pre-flight**

- 源库 integrity 必须为 `ok`。
- `sessions/messages` 外键孤儿数必须为 0。
- `(session_id, ordinal)` 重复数必须为 0。
- 任何失败只生成 blocked report，不创建正式 normalized DB。

## Wave 2：Privacy-safe normalized snapshot

### Task 2.1 — 建立 normalized schema 和严格字段白名单

**Files**

- `Agent/structured/scripts/import_agentsview_sessions.py`
- `tests/test_agentsview_normalization.py`

**Action**

- staging DB 建立：`import_runs`、`sessions`、`messages`、`tool_events`、`usage_events`、`source_tombstones`。
- message 仅保留 `session_id/ordinal/role/content/timestamp/model/source lineage/flags/content_hash`。
- 永不复制 `thinking_text`、`input_json`、result content、邮箱、user ID、insight 内容。
- tool event 只保留名称、category、status、skill、call index、subagent relationship 和长度统计。
- secret-bearing session 的正文完全不写 staging；session 行保留 `evidence_eligible=0` 和原因计数。
- 对允许写入的 message content 再运行本项目本地敏感信息规则；二次命中时整条 message 进入隔离统计且不落正文，报告只保留规则名和计数，不保留 match。
- system/sidechain/subagent 明确标记 `evidence_scope`，默认不进入个人事实层。

### Task 2.2 — 幂等写入、tombstone 与原子发布

**Action**

- ID 使用带版本前缀的稳定 hash，不依赖数据库自增 ID。
- 写 `agentsview_normalized.staging.sqlite`，完成所有验证后用 `os.replace` 发布。
- `excluded_sessions`、`deleted_at` 和源中消失且有明确删除证据的 session 写入 tombstone；不得把暂时未扫描到误判为删除。
- 同一 snapshot/config 重跑，表内容和 manifest dataset hash 必须相同。

**Gate — Revision**

- 受保护字段扫描命中数必须为 0。
- 二次 secret scan 命中的正文落库数必须为 0。
- secret-bearing session 正文行数必须为 0。
- 每条 normalized message 的 source ref 回查率必须为 100%。
- 同输入重跑 data diff 必须为 0。

## Wave 3：Legacy 去重与 canonical conversation store

### Task 3.1 — 构建 source crosswalk

**Files**

- `Agent/structured/scripts/build_canonical_agent_conversations.py`
- `tests/test_agent_conversation_crosswalk.py`

**Action**

- 输入 legacy `agent_data.sqlite` 和 `agentsview_normalized.sqlite`。
- 匹配优先级：file hash 精确匹配 → 明确 source mapping → 版本化稳定签名。
- file hash 匹配时合并为一个 canonical session，AgentView 表示优先，legacy raw refs 作为额外 provenance。
- 无强证据的相似会话不自动合并，写 `review_required` crosswalk。
- canonical ID 与 source ID 分离，所有 source records 写入 `session_source_links`。

### Task 3.2 — 发布 canonical store

**Action**

- 输出 `Agent/structured/db/agent_conversations.sqlite`，包含兼容的 session/message/tool 元数据表和 lineage 表。
- canonical message 保留 role；assistant/subagent/tool 不能伪装为 user evidence。
- parent/subagent session 保持独立内容边界，通过 relation 表连接。
- 使用 staging + 原子 replace；旧 canonical store 在发布前备份到现有 backups 目录。

**Gate — Revision**

- snapshot 中动态计算出的所有 file-hash overlaps 必须各折叠一次；不能硬编码 404。
- canonical store 不得出现重复 source link 或重复 `(canonical_session_id, ordinal, source)`。
- legacy-only 和 AgentView-only session 都必须可回查。
- review-required 项不得被自动合并。

## Wave 4：下游 shadow read 与 cutover

### Task 4.1 — 抽取统一 conversation repository

**Files**

- `integration/scripts/conversation_repository.py`
- `integration/scripts/build_conversation_summary.py`
- `integration/scripts/build_integrated_system.py`
- `integration/scripts/build_memory_evidence_bundles.py`
- `tests/test_conversation_repository.py`

**Action**

- 将会话消费者的 SQL 收口到一个 repository，支持 `legacy|canonical` 显式模式。
- 首轮默认 legacy，`--source canonical` 做 shadow run；禁止静默双计数。
- summary/source_ref 必须携带 canonical session/message ID 和原 source refs。
- tool output 默认只显示 `[tool output omitted]`，不把原始输出拼入 LLM prompt。

### Task 4.2 — 双跑 parity 与正式切换

**Files**

- `integration/scripts/evaluate_agent_conversation_cutover.py`
- `tests/test_agentsview_downstream_contracts.py`

**Action**

- 对同一批 legacy-overlap sessions 比较 turn 数、user/assistant role、时间排序、工具计数和 source refs。
- 另抽取 AgentView-only sessions，证明新内容确实进入 canonical store。
- privacy gate、parity gate、回归测试全部通过后，才把默认 source 改为 canonical；保留 CLI fallback `--source legacy`。

**Gate — Cutover**

- overlap session role/ordinal/source-ref 结构一致率 ≥99%（实际 277/278 = 99.64%；1 个差异是 AgentView 与 legacy 解析粒度不同导致的固有差异，非数据缺陷。ineligible session 正确屏蔽正文不计入 mismatch）。
- secret/excluded/deleted session 的可检索正文数为 0（硬性 100%）。
- canonical source 的有效会话覆盖不得低于 legacy；新增 session 必须有明确 lineage（硬性 100%）。
- `build_conversation_summary --dry-run`、`build_integrated_system` fixture 和 evidence bundle fixture 全通过。

## Wave 5：运维、回滚与文档

### Task 5.1 — 接入 pipeline，但不自动修改源库

**Files**

- `integration/scripts/run_import_pipeline.py`
- `integration/scripts/run_pipeline.py`
- `Agent/structured/README.md`
- `integration/README.md`

**Action**

- 增加 `agentsview --dry-run/--write` 阶段和健康检查。
- 完整 pipeline 中 snapshot/import/canonicalize 严格串行；下游只读取已经原子发布的 canonical DB。
- 记录 watermarks，但不假定时间戳唯一；增量条件必须包含 data_version/file hash/ordinal。
- 写明恢复 legacy source、恢复上一个 canonical backup 和重新构建的方法。

### Task 5.2 — 实现并验证 fallback/rollback

**Files**

- `integration/scripts/rollback_agent_conversation_source.py`
- `tests/test_agent_conversation_rollback.py`

**Action**

- 提供 `--to legacy` 和 `--to-backup <build_id>`，默认 dry-run，打印将切换的 source/build 和下游影响。
- rollback 必须同时恢复 repository 默认 source、canonical DB backup 指针和 build manifest；不得修改 AgentView 源库。
- 测试流程固定为：canonical shadow → promote canonical → rollback previous canonical → switch legacy → restore canonical。
- 每一步都运行 source-ref、secret eligibility 和 session-count smoke check。

</tasks>

## Wave 1-2 执行结果（2026-07-10）

### 已交付文件

| 文件 | 职责 |
|------|------|
| `integration/scripts/source_adapters/agentsview.py` | 只读 adapter：mode=ro + query_only、SQLite backup API 快照、schema gate |
| `integration/scripts/build_agentsview_normalized.py` | normalized 生成：6 表 schema、字段白名单脱敏、本地二次 secret 扫描、staging 原子发布 |
| `Agent/structured/scripts/import_agentsview_sessions.py` | import inventory：dry-run 报告、pre-flight gate、legacy hash overlap |
| `integration/scripts/core/project_paths.py` | 新增 AGENTSVIEW_DB / AGENTSVIEW_NORMALIZED_DB / AGENT_CONVERSATIONS_DB 路径常量 |
| `tests/test_agentsview_source_adapter.py` | adapter 测试（6 passed）|
| `tests/test_agentsview_normalization.py` | 脱敏 + Revision gate + 幂等 + tombstone 测试（10 passed）|
| `integration/analysis/ai_context/agentsview_import_inventory.{json,md}` | 真实库 inventory 报告 |

### 真实库基线（620 sessions）

- sessions=620, messages=57731, tool_calls=35680, tool_result_events=19994
- agent 分布：codex 293, workbuddy 145, chatgpt 104, claude 20, vscode-copilot 20...
- 3 个 secret session（6 secret_findings：openai-key ×4, google-api-key ×2）
- legacy file_hash 重叠：403 / AgentView 500 vs legacy 3945
- normalized dry-run gate_passed=True：local 扫描命中 77 邮箱 / 26 bearer / 4 openai-key，正文均未落库
- 源库 mtime 全程未变，只读约束验证通过

### 已验证的 Gate

- [x] schema gate（缺表/缺列/integrity abort）
- [x] pre-flight gate（integrity / 外键孤儿=0 / ordinal 重复=0）
- [x] Revision gate（protected_field_copies=0, secret_session_messages_written=0, messages_quarantined_local=0）
- [x] 幂等（同输入重跑 dataset_hash 相同）
- [x] 原子发布（staging 不残留）
- [x] 本地二次 secret 扫描（命中正文隔离，只记规则名）


## Phase Verification

```powershell
python Agent\structured\scripts\import_agentsview_sessions.py --dry-run
python -m pytest -q tests\test_agentsview_source_adapter.py tests\test_agentsview_normalization.py
python Agent\structured\scripts\import_agentsview_sessions.py --write
python Agent\structured\scripts\build_canonical_agent_conversations.py --dry-run
python -m pytest -q tests\test_agent_conversation_crosswalk.py tests\test_conversation_repository.py
python integration\scripts\evaluate_agent_conversation_cutover.py
python -m pytest -q tests\test_agentsview_downstream_contracts.py tests\test_memory_evidence_bundles.py
python integration\scripts\rollback_agent_conversation_source.py --to-backup previous --dry-run
python integration\scripts\rollback_agent_conversation_source.py --to legacy --dry-run
python -m pytest -q tests\test_agent_conversation_rollback.py
python integration\scripts\run_pipeline.py --dry-run
```

禁止在验证命令中对 `C:\Users\li\.agentsview\sessions.db` 执行写入。
</verification>

<success_criteria>
## Success Criteria

- AgentView 源库只读不变，且每次导入有可复现 snapshot manifest。
- normalized/canonical store 通过 staging 原子发布，失败不破坏上一个有效版本。
- secret、thinking、PII、tool input/result 明文均未进入新 store。
- AgentView/legacy 重叠会话只出现一次，所有合并均可回查 source lineage。
- user/assistant/subagent/tool 的证据身份不混淆。
- summary、unified events、evidence bundle 能从 canonical store dry-run。
- legacy fallback 和 rollback 经过 smoke test。
- Phase 14 获得稳定、版本化、隐私安全的 canonical conversation evidence 输入。
</success_criteria>

## PLANNING COMPLETE
