---
phase: 13.5
status: Complete
researched: 2026-07-10
mode: local-read-only
---

# Phase 13.5 Research：AgentView 数据源审计

## 数据库事实

审计时 `C:\Users\li\.agentsview\sessions.db`：

- SQLite integrity check：`ok`
- 文件约 513 MB，journal mode：WAL，`user_version=59`
- 数据库持续写入；两次查询之间 session/message 计数发生增长，所以导入必须使用单一事务或 backup snapshot
- 620 sessions、57,701 messages、35,663 tool calls、19,991 tool result events
- 235 个 parent/subagent 关系记录，消息 ordinal 无重复，外键检查未发现孤儿
- 3 个 session 带 secret signal，共 6 条 secret findings
- 154 条消息缺 timestamp，必须允许缺失并保留可追溯 ordinal

这些数字是规划基线，不应硬编码为永久验收值；实现验收应以同一 snapshot manifest 的计数为准。

## 与旧 Agent 数据的关系

旧 `Agent/structured/db/agent_data.sqlite` 当前包含：

- 831 条 `agent_sessions_meta`
- 37,884 条 `agent_messages`
- 30,595 条 `agent_tool_calls`
- 30,547 条 `agent_tool_outputs`

AgentView session ID 与旧 session ID 不直接相等，但 lineage 有明显重叠：

- AgentView 非空 file hashes：498
- 与旧 `source_files.sha256` 精确重叠：404
- AgentView file basename 与旧 raw file basename 重叠：281

因此把 AgentView 当成第四个顶级 source 直接写入 `unified_events` 会产生大规模重复。正确边界是：AgentView 与 legacy Agent 都是 canonical conversation store 的输入。

## 方案比较

| 方案 | 优点 | 主要问题 | 结论 |
|---|---|---|---|
| 下游直接查询 `sessions.db` | 改动少 | 运行时依赖 live WAL、不可复现、隐私 gate 分散 | 拒绝 |
| AgentView 直接覆盖 `agent_data.sqlite` | 单库 | 可能丢失旧数据；旧 normalizer 会重建表；回滚困难 | 拒绝 |
| AgentView 作为第四 source | 接入快 | 404 个已知 file-hash 重叠会重复 | 拒绝 |
| 安全 normalized snapshot + canonical union store | 可审计、可回滚、下游单入口 | 多一个生成型 SQLite | 采用 |

## 可复用代码模式

- `core/project_paths.py`：统一路径常量。
- `source_adapters/base.py`：source adapter 边界。
- `normalize_agent_conversations.py`：turn/message/tool 的旧 schema 与解析语义。
- `run_import_pipeline.py`：import run、hash、quarantine、dry-run 模式。
- `build_conversation_summary.py`：session/turn 消费契约。
- `build_memory_evidence_bundles.py`：source refs 和 evidence gate。

## 关键风险

1. live WAL 导致跨查询快照不一致。
2. thinking、tool arguments/results 和 secret-bearing sessions 进入长期检索面。
3. AgentView 与 legacy 双写造成重复会话和重复个人结论。
4. subagent/assistant 内容被错误解释为用户本人观点。
5. 源库 schema 升级后静默错读。
6. deleted/excluded session 在下游继续残留。

## RESEARCH COMPLETE
