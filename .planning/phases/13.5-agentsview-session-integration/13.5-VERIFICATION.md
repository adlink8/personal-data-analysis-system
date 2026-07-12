---
phase: 13.5
name: agentsview_session_integration
verified_at: 2026-07-10T15:00:00+08:00
verifier: adlink + ZCode
result: PASS
---

# Phase 13.5 验证记录

## 验证环境

- 平台：Windows 10.0.22631 x64
- Python：3.14
- 分支：codex/llm-memory-mcp-integration
- 源库：`C:\Users\li\.agentsview\sessions.db`（513MB，WAL，user_version=59）

## 验证命令与结果

### 1. 源库只读约束

```
源库 mtime 全程未变（2026-07-10 11:01，早于所有操作）
integrity_check: ok
连接方式: mode=ro + PRAGMA query_only=ON
```

### 2. Schema gate + pre-flight

```
probe ok: True
required_tables_missing: []
missing_columns: {}
integrity_check: ok
messages_orphan_session_id: 0
duplicate_session_ordinal: 0
```

### 3. Normalized Revision gate

```
protected_field_copies: 0 (thinking/input_json/result_content 未复制)
messages_quarantined_local: 0 (本地扫描命中正文未落库)
secret_session_messages_written: 0 (secret session 正文未写)
local_rule_hits: {email: 77, bearer: 26, openai-key: 4} → 正文均为 NULL
idempotent: 同输入重跑 dataset_hash 相同
```

### 4. Canonical store integrity

```
canonical_sessions: 623 (278 merged + 342 AV-only + 3 legacy-only)
canonical_messages: 57,765
canonical_tool_events: 55,674
duplicate source links: 0
duplicate (csid, ordinal, source): 0
AV-linked: 620, legacy-linked: 281 (全部可回查)
ineligible sessions: 3 (secret, 正文 = 0)
```

### 5. Cutover gate

```
overlap checked: 278
structure match: 277 (99.64%)
secret searchable: 0
canonical coverage >= legacy: True (623 >= 281)
AV-only all lineage: True
GATE: PASS
```

parity 99.64% 说明：1/278 的差异是 AgentView 与 legacy 解析粒度不同导致的固有差异（AV 把 tool output 放独立表，legacy 塞进 messages；AV 无 developer role），非数据缺陷。ineligible session 正确屏蔽正文不计入 mismatch。

### 6. 消费者迁移

```
build_conversation_summary.py --source canonical --dry-run: PASS (623 sessions loaded)
build_conversation_summary.py --source legacy --dry-run: PASS (原有行为不变)
build_conversation_summary.py (无 --source, 指针=canonical): PASS (默认 canonical)
build_integrated_system.py: deferred（Agent 数据来自 Phase 02 dataset，非 canonical store）
```

### 7. 回滚演练

```
canonical → legacy: smoke ok (281 sessions)
legacy → canonical: smoke ok (623 sessions, secret_searchable=0)
rollback log: 4 条切换记录，全部 ok
最终状态: canonical (已激活)
```

### 8. 测试

```
python -m pytest tests/test_agentsview_source_adapter.py tests/test_agentsview_normalization.py tests/test_agent_conversation_crosswalk.py tests/test_conversation_repository.py tests/test_agentsview_downstream_contracts.py tests/test_agent_conversation_rollback.py -q
→ 43 passed
```

### 9. Pipeline

```
python integration/scripts/run_pipeline.py --agentsview --dry-run
→ snapshot → normalized → canonical 三步串行成功
→ 后续 12 步正常解析

python integration/scripts/run_pipeline.py --dry-run
→ 12 步正常（未受影响）
```

## 遗留

- `build_integrated_system.py` 的 canonical 接入 deferred（Agent 数据源是 Phase 02 结构化 dataset，不是 canonical conversation store）
- Phase 14 knowledge unit 将直接消费 canonical evidence，不依赖 build_integrated_system 的 canonical 接入

## 结论

Phase 13.5 验证通过。canonical conversation store 已成为 `build_conversation_summary.py` 的默认数据源，legacy fallback 和 rollback 经演练验证。AgentView 源库只读不变。
