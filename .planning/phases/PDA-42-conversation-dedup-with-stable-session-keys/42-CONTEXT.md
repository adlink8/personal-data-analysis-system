# Phase 42: Conversation Dedup with Stable Session Keys - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

把 canonical 会话去重的身份键从**文件内容 hash**（会话 jsonl 追加增长 → hash 变 → 匹配失败 → 同一会话新旧双份并存、永不淘汰）改为**会话级稳定键**，并清理现存双份。目标：同一会话的内容增长被识别为"同一 canonical session 的更新"，全量重建幂等且跨运行确定性。

不做的：不改消息内容清洗/注入剥离逻辑；不动 evidence_eligible 语义（Phase 41 的 eligible 统一先行）；KU 抽取侧口径不在本 phase。

</domain>

<decisions>
## Implementation Decisions

### 身份键设计
- **D-01:** 会话身份 = **(source, source_session_id) 复合稳定键**（agentsview 的 session id、legacy 的原生会话标识），file_hash 降级为**变更检测信号**（变了 = 需要增量合并），不再承担身份职能。[auto] Q: "稳定键用什么？" → Selected: "(source, source_session_id) 复合键，file_hash 仅作变更检测"（recommended：原生 id 在上游生命周期内稳定，hash 天然随内容漂移）
- **D-02:** 消息级身份 = (session_key, ordinal/原生 message id) 稳定键；内容增长时**增量追加新消息 + 更新会话元数据**，不整份复制。[auto] Q: "更新时全量替换还是增量合并？" → Selected: "消息级增量合并"（recommended：保留 message 级去重与 evidence ref 稳定性——KU 的 source_message_ref 不能因重同步而失效）

### 存量双份清理
- **D-03:** 迁移脚本按稳定键分组识别现存双份 canonical session：**保留消息最全/最新的一份，其余标 superseded 而非硬删**（遵守"标 lifecycle 不硬删"规则）；被 supersede 会话的 evidence ref 映射到保留会话的同消息（ordinal 对齐），映射不了的记入孤儿报告。[auto] Q: "双份直接删还是标 superseded？" → Selected: "标 superseded + ref 映射"（recommended：KU evidence ref 引用着这些会话的消息，硬删会制造孤儿）

### 确定性
- **D-04:** legacy `agent_sessions_meta` 代表行选择加**确定性 ORDER BY**（started_at ASC, 文件路径 ASC），消除"无 ORDER BY 代表行漂移"导致的跨运行 merge 结果不稳定（审计 M3）。
- **D-05:** hash 匹配失败、双份合并、ref 映射失败全部**计数进 stats/报告**——延续"失败不静默"原则（本轮修复的统一主题）。

### the agent's Discretion
- 稳定键的具体列落法（新列 vs 复用 source_session_id）、迁移脚本形态（参照 tools/migrations/ 既有两个脚本的 dry-run/--write 模式）、重建期间的 KU 索引影响评估方式。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 入库链路现状
- `src/personal_knowledge/application/conversation/build_canonical_agent_conversations.py` — 去重键现状（:277-305 file_hash merge；:175-190 legacy 代表行无 ORDER BY；:580-582 legacy eligible 过滤；F-08 已补 AV 侧对称过滤）
- `src/personal_knowledge/application/conversation/build_agentsview_normalized.py` — normalized 层（F-08 修复后：secret/excluded/deleted 三类消息不写入 + 排除零匹配 fail-closed）
- `src/personal_knowledge/application/conversation/import_agentsview_sessions.py` — inventory 的 orphan/重复 ordinal gate

### 流程与约束
- `docs/runbooks/product-sync.md` — 对话同步流程
- `AGENTS.md` — 对话 SSOT 与 AgentsView live 只读约束

### 迁移模式参照
- `tools/migrations/backfill_ku_data_debts.py`、`tools/migrations/salvage_v1_backlog.py` — dry-run 默认 + --write 备份 + 单事务 + 统计报告的标准迁移形态

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `canonical_unit_members` 式"折叠不删除"的叠加表思想（merge layer）：superseded 会话可用同款叠加表记录替代关系
- `build_canonical_agent_conversations.py` 现有的 staging + os.replace 原子发布机制（M4 崩溃窗口已知，可顺带评估）
- 审计已量化的现状：canonical 同会话双份的成因链（legacy source_files.sha256 旧快照 vs AV file_hash 当前值）

### Established Patterns
- evidence ref 稳定性是硬约束：KU 的 source_message_ref / knowledge_unit_evidence 引用 canonical_message_id，任何消息 id 重铸都要有映射表
- "失败不静默"：F-01~F-14 修复的统一主题，本 phase 所有降级/跳过路径必须带计数

### Integration Points
- `pk-sync conversations`（sync.py）——去重键替换的生效点
- KU evidence 链（knowledge_units.source_message_ref / knowledge_unit_evidence）——存量 ref 映射的消费方
- `pk-ku doctor`——双份率可作为新检查项（与 Phase 41 覆盖矩阵同批接入）

</code_context>

<specifics>
## Specific Ideas

- 审计实测：去重键只有 file_hash（build_canonical_agent_conversations.py:277-305）；同 session 在 AgentView 库多行共享 file_hash 时 `av_by_hash[fh] = s` 后写覆盖先写；legacy 快照 hash 与 AV 当前 hash 不同 → merge 失败 → 双份均 evidence_eligible=1。
- 用户意图：Phase 42 在 ROADMAP 中依赖 Phase 41（eligible/证据口径稳定后改去重键才安全）。

</specifics>

<deferred>
## Deferred Ideas

- canonical 发布的崩溃窗口（两步 os.replace 之间 dest 缺失，审计 M4）与备份磨损——属发布原子性，可在本 phase 顺带或单列
- `parent_canonical_id` 永不回填、legacy 无 session_relations（审计 L3）
- timestamp 格式混存（legacy vs AV）导致字典序比较不可靠（审计 L2）

</deferred>

---

*Phase: 42-conversation-dedup-with-stable-session-keys*
*Context gathered: 2026-07-26*
