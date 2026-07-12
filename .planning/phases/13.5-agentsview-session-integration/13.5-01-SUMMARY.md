---
phase: 13.5
name: agentsview_session_integration
status: Complete
verified: 2026-07-10
---

# Phase 13.5 执行摘要

## 目标

把 `C:\Users\li\.agentsview\sessions.db`（AgentView live WAL，513MB）接入个人数据系统，形成可复现、隐私安全、与旧 Agent 数据去重的 canonical conversation evidence 层。

## 交付

### Wave 1：Source adapter + inventory
- `source_adapters/agentsview.py`：只读 adapter（mode=ro + query_only + backup API 快照 + schema gate）
- `import_agentsview_sessions.py`：dry-run inventory 报告（620 sessions, 57731 messages, 3 secret sessions, 403 legacy hash 重叠）

### Wave 2：Normalized snapshot
- `build_agentsview_normalized.py`：6 表脱敏 schema + 字段白名单 + 本地二次 secret 扫描 + staging 原子发布
- 107 条被本地扫描隔离（77 邮箱 + 26 bearer + 4 openai-key），正文均为 NULL
- 3 个 secret session 正文完全不写

### Wave 3：Canonical conversation store
- `build_canonical_agent_conversations.py`：file_hash crosswalk + 623 canonical sessions（278 merged + 342 AV-only + 3 legacy-only）
- legacy session_id 去重（831→281），路径后缀匹配避免 basename 碰撞
- merged session AV 空壳时 fallback legacy message（ineligible 除外）

### Wave 4：Repository + cutover
- `conversation_repository.py`：统一会话查询收口，legacy|canonical 显式模式
- `evaluate_agent_conversation_cutover.py`：parity 277/278（99.64%），secret searchable=0，GATE PASS
- `build_conversation_summary.py` 接入 `--source` 参数，canonical shadow dry-run 验证通过

### Wave 5：Pipeline + rollback
- `run_pipeline.py --agentsview`：3 步串行可选前置阶段
- `rollback_agent_conversation_source.py`：source 指针原子切换 + backup 恢复 + JSONL 日志
- canonical source 指针已激活（`integration/db/conversation_source.txt` = canonical）
- 回滚演练：canonical → legacy → canonical 全流程 OK

## 消费者迁移状态

| 消费者 | 状态 | 说明 |
|--------|------|------|
| `build_conversation_summary.py` | ✅ 已接入 | `--source` 参数 + repository，canonical shadow dry-run 通过 |
| `build_integrated_system.py` | deferred | Agent 数据来自 Phase 02 结构化 dataset（非 canonical store），接入复杂度高，留后续阶段 |

## 测试

- 43 新增测试全通过（6 adapter + 10 normalization + 6 crosswalk + 9 repository + 6 cutover + 6 rollback）
- 源库 mtime 全程未变（只读约束验证通过）

## 未修改

- AgentView 源库（`sessions.db`）——永远只读
- legacy `agent_data.sqlite` ——保留为 fallback
- `build_integrated_system.py` 的 Agent 数据源 —— deferred
