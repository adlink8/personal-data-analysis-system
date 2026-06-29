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

<decisions_wave8>
## Wave 8 决策 (2026-06-28 discuss)

**触发**:Wave 7 完成后执行超前于规划,在压缩质量未定型时落地了三库统一灌库
(SQLite + Chroma + DuckDB),并引入图数据库。回顾发现三个问题,补 Wave 8 收口。

### 决策1: 数据库相关全部暂定
- **问题**:图库存的是伪关系(`e_next_turn` 时序编号、`e_session_topic` 1对1属性),
  向量库无分类策略(`personal_events` 7723条 + `conversation_turns` 563条 粒度不一)。
- **决策**:压缩质量未定型前,不再向任何库灌新数据。已建的 `conversation_graph.duckdb`
  标记为废弃(伪关系),不作为下游依据。
- **rationale**:把存疑数据固化进图/向量库,后续难清理。地基不稳不盖楼。

### 决策2: Wave 8 范围只管压缩质量
- **决策**:Wave 8 只做质量收口(评估+根因修复+重跑)。图库真关系重做放 Wave 9,
  向量库分类放 Wave 10。职责单一,避免范围蔓延。
- **rationale**:质量是下游一切的地基。图库/向量库都依赖质量达标的 turn 叙述。

### 决策3: ** 瑕疵用根因修复,不做事后补抽
- **根因调查结论(2026-06-28)**:
  - 瑕疵 14 个/583 turn(2.4%),正常率 96.6%,距入库门槛 98% 差 1.4 个百分点。
  - **不是模型问题**:同一 chunk(turn 4-5)连调 6 次全正常;单 turn 调用完美。
  - **不是约束太浅**:单 turn 测试 prompt 约束够用。
  - **是脚本防御不足(根因)**:
    1. `parse_turn_summaries` 不校验返回段数 == 输入 turn 数,段数对就回填,内容错位无感知。
    2. prompt 没强制要求"段数必须等于输入,严格用 Turn {N}: 绝对编号"。
    3. 统计铁证:14 个瑕疵 turn 编号 `[4,6,2,2,1,6,2,2,6,4,8,2,3,3]`,
       14 个里 9 个是 turn 1/2/3(小编号);6/14 下一个 turn 以 `**` 开头(内容被吞)。
- **决策**:从根上修 `summarize_chunk` 返回后校验段数+重试、强化 prompt 约束、正则再加固。
  不写 `fix_conversation_flaws.py` 补抽脚本(治标不治本,后续重跑仍会产生)。
- **rationale**:模型是触发器,脚本没做防御才是根因。好脚本应:校验段数、不匹配重试、
  正则覆盖所有 markdown 变体。

### 决策4: 修复后全量重跑 113 session
- **问题**:现有产物是分两批跑的(前 15 个新正则 + 后 98 个 resume 跳过=旧正则),
  逻辑不一致,且 14 个瑕疵是旧正则+旧 prompt 产物。
- **决策**:根因修复后,对全部 113 session 全量重跑(幂等覆盖),保证产物逻辑一致。
- **rationale**:全量重跑 ~40 分钟(3 路并发),换来产物一致性,值。
</decisions_wave8>

<gray_areas_closed_wave8>
- [x] ** 瑕疵是模型/约束/脚本哪个问题 → 脚本防御不足(根因调查 2026-06-28 确认)
- [x] 修复用补抽还是根因修复 → 根因修复
- [x] 图库重做和向量库分类是否纳入 Wave 8 → 否,Wave 9/10 单独做
- [x] 修复后重跑范围 → 全量 113 session
</gray_areas_closed_wave8>

<gray_areas_remaining_wave8>
- [x] 质量门槛已定并通过 → 正常率 ≥ 98%,source_refs 覆盖率 = 100%;当前报告 PASS(正常率 100%,覆盖率 100%)
- [x] 根因修复后瑕疵已清零 → `conversation_quality_report.md` 显示真瑕疵数 0/583
- [x] 图库真关系抽取的具体方法 → Wave 9 采用 `向量召回候选 + LLM 判定关系 + evidence gate`,不再靠脚本启发式直接建边
- [x] 向量库分类策略 → Wave 10 先保留 `conversation_turns` 独立 collection,补质量/召回评估和候选生成接口,不合并进 `personal_events`
</gray_areas_remaining_wave8>

<decisions_wave9_wave10>
## Wave 9 / Wave 10 重新设计决策 (2026-06-28)

### 决策1: 三库职责重新锁定
- SQLite 是真相层:保存结构化摘要、source_refs、候选关系、LLM 判边结果和审核状态。
- Chroma 是候选召回层:只负责找可能相关的 turn/document pair,不得直接生成图边。
- Graph/DuckDB 是推理层:只接收通过 LLM 判定和 evidence gate 的可信边。

### 决策2: 向量库进入图库前必须经过 LLM 判边
- 先用 `conversation_turns` collection 做 topK 召回,生成候选 pair。
- 再把候选 pair 的 narrative、metadata、source_refs 交给 LLM。
- LLM 只输出固定 schema:relation_type、confidence、evidence_refs、reason。
- 关系类型不在白名单、confidence 不足、证据为空的候选不得入图。

### 决策3: 不把 semantic similarity 当成 graph relation
- 向量相似只能说明"值得检查",不能说明"有真实关系"。
- 图边必须表达清楚关系语义,例如 `same_problem`、`subproblem_of`、`follow_up`、`tool_used_for`、`preference_signal`、`contradiction`。
- `no_relation` 是合法输出,且应大量存在,用来抵抗向量召回噪声。

### 决策4: 执行顺序按依赖重排,但保留 Wave 9/10 职责边界
- 先执行 Wave 10.1/10.2:向量 collection 健康检查、recall/precision 评估、固定 eval set。
- 再执行 Wave 9:候选 pair 生成、LLM relation judge、候选/判定表、graph gate、DuckDB 真关系重建。
- 最后执行 Wave 10.3:跨 collection 检索排序和面向用户的展示优化。
- 不在 Wave 9 同时大改 `personal_events`,避免影响旧检索主线。
</decisions_wave9_wave10>

---

*Phase: 07-agent-conversation-normalization-mem0-spike*
