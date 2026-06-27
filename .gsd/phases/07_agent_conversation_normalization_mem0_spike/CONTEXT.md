# Phase 07 Context: Agent Conversation Normalization + Mem0 Spike

**Gathered:** 2026-06-27
**Status:** Wave 1-5 已执行,Wave 6(Prompt Lab) + Wave 7(回流)待规划执行
**Decision:** 用户选择 `Agent 清洗 + LLM 叙述压缩 + 回流检索`。
**Update (2026-06-27):** mem0 方案降级为可选实验(压缩度太狠/细节丢失),主线转为 mimo/OpenAI-compatible API + prompt 可控压缩 + turn 叙述回流。详见 REVIEW_feedback_2026-06-27.md。

<domain>
Phase 07 先把 Agent 原始会话日志从摘录索引升级为可追溯的结构化对话层，再用 mimo/OpenAI-compatible API 配合项目提示词做可控叙述压缩。

当前事实：

- GPT `messages.content` 最接近完整对话全文。
- Agent `session_messages.text_excerpt` 是摘录，不是全文真相层。
- Agent 原始真相在 `Agent/原始数据/**/sessions/**/*.jsonl`。
- Codex session 顶层常见类型：`session_meta`、`turn_context`、`response_item`、`event_msg`、`compacted`。
- 可分析内容主要在 `response_item.payload.type=message` 和 `event_msg.payload.type=user_message/agent_message`。
</domain>

<decisions>
## Locked Decisions

- 保留现有 `sessions` / `session_messages`，新增 v2 旁路表。
- 结构化粒度至少包含 `session -> turn -> message/tool/event`。
- 每条规范化记录必须保留 `raw_file`、`line_no`、`timestamp`、`raw_type`、`payload_type`。
- `developer`、权限说明、环境上下文、token 统计、纯工具输出不进入用户想法抽取输入。
- mem0 只保留为可选实验，不进入 Phase 07 主路径。
- 主压缩器直接调用 mimo/OpenAI-compatible API，提示词必须版本化。
- 每轮 prompt 输出必须用固定样本集评测，未通过前不能写入正式检索层。
- 压缩产物必须保留 `source_refs` 或 `raw_file + line_no`，否则不得入库。
</decisions>

<canonical_refs>
- `Agent/结构化数据/脚本/build_agent_dataset.py`
- `Agent/结构化数据/SQLite数据库/agent_data.sqlite`
- `Agent/原始数据/`
- `统合模块/脚本/enrich_unified_events.py`
- `统合模块/脚本/build_integrated_system.py`
- `.gsd/phases/06_deep_memory_graph_mining/SUMMARY_两个Demo反馈总结.md`
- `.gsd/phases/06_deep_memory_graph_mining/EXECUTION.md`
</canonical_refs>

<deferred>
- 不把 normalized Agent messages 全量写进 `unified_events`。
- 不把 mem0 输出直接写进 `memory_items`。
- 不引入 mem0 cloud 或外部托管服务。
- 不做 dashboard。
- (2026-06-27 更新) mem0 原子事实压缩方案不适合本项目,降级为可选实验。
  主线改为 mimo prompt-controlled turn 叙述摘要回流到向量库(保留主干+分支+细节,而非压缩成离散 claim)。
</deferred>

---

*Phase: 07-agent-conversation-normalization-mem0-spike*






