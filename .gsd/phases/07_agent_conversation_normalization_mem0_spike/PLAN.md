---
phase: 07
name: agent_conversation_normalization_mem0_spike
title: Agent 对话规范化与 LLM 叙述压缩回流
status: Planned
created: 2026-06-27
depends_on:
  - .gsd/phases/06_deep_memory_graph_mining/EXECUTION.md
  - Agent/结构化数据/脚本/build_agent_dataset.py
  - .gsd/phases/06_deep_memory_graph_mining/SUMMARY_两个Demo反馈总结.md
autonomous: false
---

# Phase 07: Agent 对话规范化与 LLM 叙述压缩回流

## Objective

把 Agent 原始会话日志从“摘录索引”升级为可追溯的结构化对话层，并在该清洗层上直接调用 mimo/OpenAI-compatible API 做可控叙述压缩。Phase 07 的主输出是可评测、可回溯、可检索的 conversation turn/context 层；mem0 仅保留为可选实验，不进入主路径。

## Non-goals

- 不替换现有 `memory_items` / `memory_links` / `memory_relations`。
- 不让 mem0 直接写入正式 memory store。
- 不把未通过 prompt 评测的 LLM 压缩结果写入正式检索层。
- 不把 Agent 细粒度消息全量并入 `unified_events`。
- 不引入 mem0 cloud 或外部托管服务。
- 不重构 Google/GPT 源库。
- 不做 dashboard。

## Wave 1: Agent Log Taxonomy and Parser Contract

### Goal

明确 Agent 原始 jsonl 的类型体系，建立稳定解析 contract。

### Tasks

1. 新增 `Agent/结构化数据/脚本/normalize_agent_conversations.py`。
2. 支持读取 `Agent/原始数据/**/sessions/**/*.jsonl`。
3. 识别顶层类型：`session_meta`、`turn_context`、`response_item`、`event_msg`、`compacted`。
4. 识别 `response_item.payload.type` 和 `event_msg.payload.type`。
5. 每条解析结果保留 `source`、`family`、`session_id`、`turn_id`、`event_index`、`timestamp`、`raw_type`、`payload_type`、`role`、`raw_file`、`line_no`。

### Verification

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --dry-run --limit-files 5
```

### Acceptance Criteria

- dry-run 输出 raw type 和 payload type 统计。
- 至少能解析 Codex session 文件。
- 解析失败的行有计数和原因，不中断整个文件。

## Wave 2: Normalized Agent Conversation Tables

### Goal

在不破坏旧表的前提下，把 Agent 会话拆成可查询的 turn/message/tool/event 层。

### Tasks

1. 在 `agent_data.sqlite` 中新增旁路表：`agent_turns`、`agent_messages`、`agent_tool_calls`、`agent_tool_outputs`、`agent_lifecycle_events`、`agent_usage_metrics`。
2. 不删除、不改名现有 `sessions` / `session_messages`。
3. 给 `session_id`、`turn_id`、`role`、`call_id`、`timestamp` 加索引。
4. 只把可解释文本写入 `agent_messages.text`。
5. `developer`、permissions、environment_context、纯 timestamp、token_count 不进入用户想法候选输入。

### Verification

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --write
```

### Acceptance Criteria

- 新表可重复生成，结果幂等。
- `agent_messages` 中 `role=user` 和 `role=assistant` 的文本明显少于旧 `session_messages` 噪声。
- 每条 `agent_messages` 都能回溯到 `raw_file + line_no`。

## Wave 3: User Thought Segment Layer

### Goal

从清洗后的 Agent/GPT 对话中抽出“用户想法片段”，解决一个对话多方向的问题。

### Tasks

1. 新增 `统合模块/脚本/build_conversation_segments.py`。
2. GPT 输入来自 `GPT/结构化数据/SQLite数据库/chatgpt_data.db.messages` 的 `role=user`。
3. Agent 输入来自新 `agent_messages` 的 `role=user`。
4. segment 字段至少包含 `segment_id`、`source`、`conversation_id/session_id`、`turn_id`、`message_id`、`segment_index`、`text`、`topic_hint`、`intent_type`、`source_ref`。
5. 切分先用确定性规则：换行、列表、明显话题切换、长度上限。

### Verification

```powershell
python 统合模块\脚本\build_conversation_segments.py --dry-run --source Agent --limit 20
python 统合模块\脚本\build_conversation_segments.py --dry-run --source GPT --limit 20
```

### Acceptance Criteria

- 同一条长用户消息可切成多个 segment。
- segment 保留源消息 ID 和原始引用。
- 不把 assistant 回答当成用户想法输入。

## Wave 4: Mem0 Candidate Compression Spike (⚠️ 已降级为可选实验,详见 REVIEW_feedback_2026-06-27.md)

> **方向调整(2026-06-27)**: 经实测,mem0 的原子事实压缩方案**不适合本项目需求**。
> 用户反馈:"压缩度太狠了,我需要的是信息密度大但是细节不能丢失,而是整理上下文逻辑主干和分支"。
> 实证:mem0 把一次性操作指令误判为稳定偏好(如"重构 PPT"被当成偏好),且完全丢失因果链和时序。
> 相比之下,`build_conversation_summary.py` 的 turn 级叙述摘要(保留 问题→分析→结论→建议)
> 才是用户认可的高密度形态。
> **决策**:Wave 4 保留脚本和候选文件作为实验记录,但移出 Phase Verification 主路径;
> 主线产出转为 Wave 6 Prompt Lab + Wave 7 conversation_context 回流。mem0 的隔离纪律(不污染 memory_items)仍有效。

### Goal

用 mem0 对清洗后的 segment 做高密度候选记忆提炼，并评估质量。

### Tasks

1. 新增 `统合模块/脚本/build_mem0_candidate_memory.py`。
2. 默认只跑小样本：Agent 20 个 segment，GPT 20 个 segment。
3. mem0 依赖和 LLM 配置必须可选：缺依赖时给出清晰错误，不影响前三波验证。
4. 输出 `统合模块/分析数据/ai_context/mem0_candidate_memories.json` 和 `mem0_candidate_evaluation.md`。
5. 候选结构必须包含 `candidate_id`、`candidate_type`、`subject`、`claim`、`confidence`、`source_segment_ids`、`source_refs`、`acceptance_status`、`reject_reason`。

### Verification

```powershell
python 统合模块\脚本\build_mem0_candidate_memory.py --dry-run --limit 10
python 统合模块\脚本\build_mem0_candidate_memory.py --sample --limit 40
```

### Acceptance Criteria

- mem0 输出不写入 `memory_items`。
- 每条候选都有 source segment 或被标记为 rejected。
- 评估报告统计候选数、有证据链比例、噪音比例和可晋级比例。

## Wave 5: Integration Notes and Regression Tests

### Goal

锁住新层边界，避免后续执行误把候选记忆当正式记忆。

### Tasks

1. 新增 `tests/test_agent_conversation_normalization.py`。
2. 测试 sample jsonl 解析、role 过滤、`raw_file + line_no` 回溯字段、mem0 candidate 不写入 `memory_items`。
3. 更新 `README.md`、`Agent/README.md`、`统合模块/README.md`、`.planning/codebase/ARCHITECTURE.md`、`.planning/codebase/TESTING.md`。
4. 说明 Phase 06 负责深层洞察，Phase 07 负责更可靠输入和候选压缩。

### Verification

```powershell
python tests\test_memory_contracts.py
python tests\test_agent_conversation_normalization.py
python 统合模块\脚本\run_pipeline.py --dry-run
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1
git diff --check
```

### Acceptance Criteria

- 旧 memory contract 测试通过。
- 新 Agent normalization 测试通过。
- README 明确 mem0 是可选实验层，不是正式记忆层；主线是 mimo prompt-controlled 叙述压缩。
- `run_pipeline.py --dry-run` 不因可选 mem0 依赖失败。

## Wave 6: Prompt Lab and Compression Evaluation Gate (★ Phase 07 新主线)

### 背景

用户明确反馈:mem0 原子事实压缩太狠,不匹配本项目需要。新的主线不是引入更重的 memory 框架,而是大道至简:直接调用 mimo/OpenAI-compatible API,用项目提示词把清洗后的对话压缩成高密度叙述。

这个 Wave 是回流入库前的质量门:prompt 没有经过固定样本反复测试,不能把结果写进 SQLite 或向量库。

### Goal

建立可重复的 prompt 版本化和效果评测机制,让压缩结果稳定保留:

- 对话主干:用户要解决什么问题,助手如何推进。
- 分支:中途出现的子问题、错误、替代方案、工具路径。
- 关键细节:文件路径、命令、错误栈、函数名、配置项、结论边界。
- 简短上下文:可注入后续 AI 的 200-500 字 context brief。
- 回溯证据:`session_id + turn_id + source_refs`。

### Tasks

1. 新增 prompt 目录:`统合模块/prompts/conversation_compression/`。
   - `v1_main.md`:主提示词,目标是 turn 级叙述压缩。
   - `v1_schema.md`:输出 JSON schema 约束。
   - `eval_rubric.md`:人工/半自动评分标准。

2. 新增 `统合模块/脚本/evaluate_conversation_prompt.py`。
   - 输入固定样本集,默认 5-10 个有代表性的 session/turn。
   - 调用 mimo/OpenAI-compatible API。
   - 输出 `统合模块/分析数据/ai_context/prompt_eval_results.json/md`。
   - 每轮记录 `prompt_version`、`model`、`temperature`、`sample_ids`、`score`、`known_failures`。

3. 建立固定评测样本集 `conversation_prompt_eval_set.json`。
   - 至少覆盖:短问答、代码排障、多分支任务、工具调用密集、上下文很长、一次性任务 vs 稳定偏好易混淆。
   - 每个样本保留源引用,不得手写 synthetic sample 代替真实本地数据。

4. 定义评分维度。
   - `trunk_preservation`:主线是否完整。
   - `branch_preservation`:分支是否保留。
   - `detail_retention`:路径/命令/错误/配置是否保留。
   - `compression_ratio`:是否足够短,但不过度压缩。
   - `retrieval_usefulness`:摘要能否支持后续检索判断。
   - `faithfulness`:是否引入原文没有的结论。
   - `context_brief_quality`:短上下文是否可直接注入 AI。

5. 只有通过 gate 后,才允许 Wave 7 回流。
   - 最低门槛:平均分 >= 4/5。
   - `faithfulness` 必须 >= 4/5。
   - 至少 90% 样本有 `source_refs`。
   - 不能把一次性任务误压缩成稳定偏好。

### Verification

```powershell
python 统合模块\脚本\evaluate_conversation_prompt.py --dry-run --limit 3
python 统合模块\脚本\evaluate_conversation_prompt.py --write --limit 10
```

### Acceptance Criteria

- prompt 版本、模型参数和样本集可复现。
- 每轮输出有分项评分和失败样例。
- 评测报告能明确说明:当前 prompt 是否允许进入 Wave 7。
- 未通过 gate 时,脚本退出非 0 或显式标记 `gate_passed=false`。
- 压缩产物是可回溯叙述上下文,不是 mem0 风格离散 claim。

## Wave 7: 清洗产物回流主流水线 (★ Phase 07 主线,2026-06-27 新增)

### 背景

REVIEW_feedback_2026-06-27.md 诊断:Wave 1-4 的清洗产物全部成了"展览品",
没有回流到 unified_events / 向量库,违背了"清洗是为了下游检索更好用"的初心。
本 Wave 补上缺失的回流步骤,把 turn 级叙述摘要作为可检索单元灌回主流水线。

### Goal

让通过 Prompt Lab gate 的 conversation_summary / conversation_context turn 叙述(主干+分支+细节)成为可检索内容,
闭环 `清洗 → 入库 → 检索` 的初心。同时修复向量库按单条 message 切割导致的因果断裂。

### Tasks

0. 前置条件:Wave 6 Prompt Lab `gate_passed=true`。

1. 回流去向已改为 B 方案:不新增 `build_conversation_event_layer.py`,不把 turn 叙述写入 `unified_events`。
   - 实际落地脚本:`统合模块/脚本/build_conversation_vector_store.py`。
   - 输入:`conversation_summaries.json`(已生成的 turn 叙述)。
   - 输出:独立 Chroma collection `conversation_turns`。
   - event_type 取 `conversation_turn`,source 取 `Agent`/`GPT`(按 summary 的 source 字段)。
   - 每条向量 metadata 保留 `session_id` / `turn_id` / `main_topic` / `source`。
   - 幂等:重复运行重建 `conversation_turns`,不污染 `personal_events`。

2. 扩展 `build_vector_store.py`(或新增 `build_conversation_vector_store.py`)。
   - 把 turn 叙述作为向量检索单元(单元 = turn 叙述,含 user+assistant+tool 因果),不是单条 message。
   - 元数据带 `session_id`/`turn_id`/`main_topic`,检索时可聚合还原整个 session 的逻辑脉络。
   - 与现有 `personal_events` collection 隔离或共存(决策点,见 Decision Needed)。

3. 修复 GPT 对话在向量库的因果断裂(阶段二遗留问题)。
   - 现状:GPT 的 `message:user`/`message:assistant` 各自独立成向量,因果链断。
   - 方案:按 conversation+turn 聚合后再向量化(与 Agent turn 叙述同构)。

4. 更新 `run_pipeline.py`,在 step 10(build_vector_store)前插入新步骤。

### Decision Needed (需用户拍板)

- **回流去向 A**:turn 叙述写入 `unified_events` 统一表,与 GPT message 混在同一 collection。
  优点:检索一站式;缺点:与旧 message 事件粒度不一,聚合逻辑复杂。
- **回流去向 B**:turn 叙述写入独立 collection `conversation_turns`。
  优点:粒度清晰,不污染旧数据;缺点:检索需跨 collection 合并。
- **倾向 B**(隔离风险低,符合"叠加不破坏原数据"的项目惯例)。

### Verification

```powershell
# 1. turn 叙述回流到向量库
python 统合模块\脚本\build_conversation_summary.py --limit 20 --write
python 统合模块\脚本\build_conversation_vector_store.py --dry-run
python 统合模块\脚本\build_conversation_vector_store.py --write

# 2. 检索验证:能按话题找到完整 turn 叙述(含因果链)
python 统合模块\脚本\unified_search.py memory --subject MQTT --neighbors 1

# 3. 回归
python tests\test_agent_conversation_normalization.py
python tests\test_memory_contracts.py
git diff --check
```

### Acceptance Criteria

- Agent 对话(GPT 之外第二大对话源)在向量库中**可检索**(不再缺席)。
- 检索单元是 turn 叙述(含因果链),不是单条 message(不再断裂)。
- 每条 turn 叙述向量可回溯到 `session_id + turn_id + source_refs`。
- 回流幂等,重复运行不产生重复向量。
- 不破坏现有 `personal_events` collection 和 memory_items 契约。

## Execution Order

1. Wave 1：解析 taxonomy 和 dry-run 统计。✅ 已完成
2. Wave 2：写入 Agent v2 旁路表。✅ 已完成
3. Wave 3：生成 user thought segments。✅ 已完成
4. Wave 4：接 mem0 小样本候选压缩。**(⚠️ 已降级为可选实验)** ✅ 完成(降级)
5. Wave 5：补测试和文档。✅ 已完成
6. **Wave 6:Prompt Lab 与压缩效果评测(★ 入库前硬门槛)**。✅ 已完成 gate 通过(7/7 样本 faithfulness 全 5)
7. **Wave 7:清洗产物回流主流水线(★ Phase 07 主线,2026-06-27 新增)**。✅ 已完成(独立 collection `conversation_turns` 已入库并接入统一检索)

## Wave 7 实施记录(2026-06-27)

- **回流去向**:用户拍板 B 方案(独立 collection `conversation_turns`,不碰 `personal_events`)。
- **代码完成**:
  - `build_conversation_vector_store.py`:turn 叙述向量化入库,独立 collection,幂等。
  - `search_vectors.py` 改造:新增 `search_conversation_turns` + `search_all`(跨 collection 合并检索)。
  - `unified_search.py` 改造:`search_semantic` 默认 `include_turns=True`,CLI/MCP/Agent 全接入。
  - `run_pipeline.py` 新增步骤 13(turn 叙述回流)。
- **已验证完成**:
  - `build_conversation_summary.py --write` 已生成全量 turn 叙述。
  - `build_conversation_vector_store.py --write` 已写入 `conversation_turns` collection。
  - `unified_search.py semantic ...` 默认支持跨 `personal_events` + `conversation_turns` 检索。
- **Wave 7-4 降级**:GPT 对话因果断裂修复需先建 GPT turn 切分层,且会改动 `personal_events`,违背"不破坏原数据"惯例。降级为后续增强,主线(Agent 回流)已闭环。

## Phase Verification

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --dry-run --limit-files 5
python Agent\结构化数据\脚本\normalize_agent_conversations.py --write
python 统合模块\脚本\build_conversation_segments.py --dry-run --source Agent --limit 20
python 统合模块\脚本\build_conversation_segments.py --dry-run --source GPT --limit 20
python 统合模块\脚本\build_conversation_summary.py --limit 10 --write
python 统合模块\脚本\evaluate_conversation_prompt.py --write --limit 10
python 统合模块\脚本\build_conversation_vector_store.py --dry-run
python 统合模块\脚本\build_conversation_vector_store.py --write
python tests\test_memory_contracts.py
python tests\test_agent_conversation_normalization.py
python 统合模块\脚本\run_pipeline.py --dry-run
git diff --check
# mem0 可选实验(非主路径):
# python 统合模块\脚本\build_mem0_candidate_memory.py --dry-run --limit 10
```

## Success Criteria

- Agent 原始日志能被稳定拆成 session / turn / message / tool / lifecycle / usage。
- 用户想法提炼输入只来自清洗后的 user message segments。
- mem0 仅保留为可选实验,不污染正式 `memory_items`。
- mimo/prompt 压缩结果必须通过固定样本评测后才允许回流。
- 每条压缩产物都能回溯到 `session_id + turn_id + source_refs`。
- 可选 mem0 依赖缺失时,核心 Agent normalization、Prompt Lab 和回流链路仍可验证。
- **★ prompt 版本化并通过固定样本评测,压缩效果可反复比较(2026-06-27 新增主线)**。
- **★ turn 级叙述摘要回流到向量库,Agent 对话可检索(2026-06-27 新增主线)**。
- **★ 检索单元是 turn 叙述(含因果链),不是单条 message(2026-06-27 新增主线)**。

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| Agent 日志格式变化 | 解析失败或漏数据 | 保留 raw type/payload type，失败计数，先支持 Codex |
| 噪声进入用户想法层 | 候选记忆污染 | developer/env/token/tool 输出默认排除 |
| mem0 依赖安装失败 | 阶段卡住 | mem0 作为可选 Wave 4，前三波不依赖 |
| LLM 输出不可复现 | 测试不稳定 | 固定 prompt_version/model/temperature/sample_set,测试 gate 结构和评分阈值 |
| 候选无证据链 | 无法晋级 | source refs 为空直接 rejected |
| prompt 看起来顺但检索变差 | 错误摘要入库污染检索 | Prompt Lab gate 先评测再回流,失败样例进入回归集 |
| 数据库膨胀 | 查询变慢 | v2 表只保存结构化字段和摘要，原文回源文件 |

---



## Wave 8: 压缩质量收口 (★ 2026-06-28,执行超前反思后按 GSD 补规划)

> **GSD 元数据**
> - 触发:Wave 7 完成后执行超前于规划,在压缩质量未定型时落地三库统一灌库 + 图数据库。
> - 决策依据:见 `CONTEXT.md` `<decisions_wave8>`(2026-06-28 discuss)。
> - 范围:**只管压缩质量收口**。图库重做 → Wave 9,向量库分类 → Wave 10。
> - 质量门槛:本 Wave 达标后才允许启动 Wave 9/10。

### Wave 8 目标
1. 建立压缩质量客观评估基线,定义"可入库"硬门槛。
2. 从根因修复 `**` 瑕疵产生机制(脚本防御不足,非模型问题)。
3. 全量重跑 113 session,验证瑕疵清零、产物逻辑一致。

### Wave 8 任务分解(GSD 原子任务)

#### Wave 8.1: 压缩质量评估基线

- **任务 8.1.1** (id: `8.1.1`)
  - description: 新增 `统合模块/脚本/evaluate_conversation_quality.py`,对 `conversation_summaries.json` 做客观质量评估
  - 评估维度:完整度(瑕疵 turn 占比)、信息密度(长度分布)、回溯链完整率(source_refs 覆盖率)、因果完整性(瑕疵是否造成 turn 链断裂)
  - acceptance: dry-run 输出各维度统计;能识别并列举所有 `**`/过短/空瑕疵 turn 及其 session/turn_no;生成 `conversation_quality_report.{json,md}`
  - commit_type: feat

- **任务 8.1.2** (id: `8.1.2`)
  - description: 在评估报告中定义并写入质量门槛:正常率 ≥ 98%、回溯链覆盖率 100%
  - acceptance: 报告含明确的 PASS/FAIL 判定;当前 96.6% 正常率判为 FAIL 并列出差距
  - commit_type: feat

#### Wave 8.2: 瑕疵根因修复(决策3:不补抽,改根因)

- **任务 8.2.1** (id: `8.2.1`)
  - description: 修复 `summarize_chunk` 返回后增加段数校验——解析段数 ≠ 输入 turn 数时自动重试(最多 2 次)
  - 根因:`parse_turn_summaries` 不校验段数,LLM 偶发合并/错位输出时内容静默错位
  - acceptance: 加单元测试覆盖"LLM 返回段数不足""段数过多""段数匹配"三种场景;校验失败触发重试而非静默回填
  - commit_type: fix

- **任务 8.2.2** (id: `8.2.2`)
  - description: 强化 `SUMMARY_USER_PROMPT_TEMPLATE` 约束——明确要求"输出段数必须等于输入 turn 数,严格用 `Turn {N}:` 绝对编号(不用相对编号),每个 turn 独立成段不合并"
  - acceptance: 改动可追溯(有 before/after prompt 文本对比);prompt_version 自增
  - commit_type: fix

- **任务 8.2.3** (id: `8.2.3`)
  - description: 加固 `parse_turn_summaries` 正则——处理 LLM 单段内含多个 Turn 标记的合并叙述(检测并拆分),并保留上一轮已修的 markdown 加粗兼容
  - acceptance: 单元测试覆盖"标准/加粗/标题/合并叙述"4 类 LLM 输出;全部正确切分
  - commit_type: fix

#### Wave 8.3: 全量重跑验证(决策4:全量 113 session)

- **任务 8.3.1** (id: `8.3.1`)
  - description: 备份现有 `conversation_summaries.{json,md}`,然后用修复后的脚本全量重跑 113 session(`--limit 0 --workers 3`,不用 resume 保证逻辑一致)
  - acceptance: 重跑无报错;新产物 turn 总数与旧产物一致(583 ± 容差);`**` 瑕疵数 < 3(理想 0)
  - commit_type: chore

- **任务 8.3.2** (id: `8.3.2`)
  - description: 重跑 `evaluate_conversation_quality.py`,确认正常率 ≥ 98% 门槛通过
  - acceptance: 评估报告判 PASS;若仍 FAIL,列出剩余瑕疵交回 discuss(可能需 Wave 8.2 方案 B 兜底)
  - commit_type: test

- **任务 8.3.3** (id: `8.3.3`)
  - description: 标记 `conversation_graph.duckdb` 为废弃(伪关系),写入说明文件;`build_triple_store.py` 的图部分暂挂,等 Wave 9 重做
  - acceptance: DuckDB 目录有 DEPRECATED 说明;build_triple_store.py 图部分加注释标暂停
  - commit_type: docs

### Wave 8 验收标准(Acceptance Criteria)
- [x] `evaluate_conversation_quality.py` 生成报告,客观量化质量
- [x] `summarize_chunk` 段数校验 + 重试机制就位,有单元测试
- [x] prompt 约束强化,prompt_version 自增
- [x] 正则加固,4 类 LLM 输出单元测试全过
- [x] 全量重跑后正常率 ≥ 98%(当前 100%,瑕疵 0)
- [x] 伪关系图库标记废弃
- [x] 质量达标前不向任何库灌新数据

### Wave 8 验证命令
```powershell
python 统合模块\脚本\evaluate_conversation_quality.py --write
python tests\test_conversation_summary_parse.py    # 8.2.1/8.2.3 单元测试
# 全量重跑
python 统合模块\脚本\build_conversation_summary.py --write --limit 0 --workers 3
python 统合模块\脚本\evaluate_conversation_quality.py --write   # 复评
```

### Wave 8 依赖与风险
- **依赖**:Wave 7 已完成(summary 产物存在);MiMo 端点可用(key/base_url)
- **风险1**:根因修复后仍偶发瑕疵 → 兜底方案 B(单 turn 强制分批,`MAX_CHARS_PER_CALL` 降到 3000)
- **风险2**:全量重跑耗时 ~40 分钟 → 用已验证的 3 路并发,后台运行
- **风险3**:重跑可能把原来正常的 turn 搞坏(LLM 非确定性)→ 重跑前必须备份,对比新旧

### Wave 8 执行顺序
1. Wave 8.1 → 8.2(质量评估驱动修复,修复有测试)
2. Wave 8.3(全量重跑验证)
3. **质量门槛**:正常率 ≥ 98% 通过后,解锁 Wave 9(图库真关系)和 Wave 10(向量库分类)

## Wave 9: 向量候选 + LLM 判边的真关系图谱重做 (★ 重新设计)

> **GSD 元数据**
> - 触发:用户明确提出“进入图数据库前引入 LLM,根据向量库判断关联关系而不是靠脚本”。
> - 设计边界:向量库只生成候选 pair,不直接建边;LLM 只做关系判定,不做事实来源;图数据库只接收通过 gate 的边。
> - 外部参照:GraphRAG/LlamaIndex Property Graph 的共同模式是 LLM 抽取结构化 entities/relationships,并结合 embedding/vector store 做检索或候选召回。

### Wave 9 目标

把已废弃的 `conversation_graph.duckdb` 伪关系图库重做为可信图谱流水线:

1. 从 `conversation_turns` 向量库召回疑似相关 turn pair。
2. 用 LLM 判断候选 pair 是否存在真实关系、关系类型和证据。
3. 先把候选和判定结果写入 SQLite 审计表。
4. 只有通过 evidence gate 的关系才写入 DuckDB 图库。
5. 每条边都能回溯到 `session_id + turn_id + source_refs`。

### Wave 9 非目标

- 不直接从向量相似度生成图边。
- 不把 LLM 输出当事实源;事实仍以 SQLite/summary/source_refs 为准。
- 不重写 `personal_events` collection。
- 不一次性抽所有全局实体 ontology;先做 conversation-turn 关系。
- 不启用旧 `conversation_graph.duckdb` 作为下游依据。

### Wave 9.1: 候选关系生成层

- **任务 9.1.1**
  - description: 新增 `统合模块/脚本/build_graph_relation_candidates.py`
  - 输入:`conversation_summaries.json` + `conversation_turns` collection
  - 行为:对每个 turn 用向量库召回 topK 近邻,生成候选 pair
  - 默认参数:`top_k=8`,同 session 相邻 turn 单独标记为 `temporal_candidate`,跨 session 语义相似标记为 `semantic_candidate`
  - 输出 SQLite 表:`graph_relation_candidates`
  - 字段: `candidate_id`,`source_node_id`,`target_node_id`,`source_session_id`,`source_turn_id`,`target_session_id`,`target_turn_id`,`similarity`,`candidate_reason`,`candidate_type`,`source_refs_json`,`created_at`
  - acceptance: dry-run 能显示候选数、平均相似度、同 session/跨 session 分布;不会生成自环和重复 pair

- **任务 9.1.2**
  - description: 加候选质量过滤
  - 规则:去掉 self pair、重复 pair、source_refs 缺失 pair、相似度低于阈值 pair;同 session 相邻 turn 不依赖相似度但必须标记为时序候选
  - acceptance: 报告输出过滤前/后数量和丢弃原因分布

### Wave 9.2: LLM Relation Judge

- **任务 9.2.1**
  - description: 新增 prompt 目录 `统合模块/prompts/graph_relation_judge/`
  - 文件:`v1_main.md`,`v1_schema.md`,`eval_rubric.md`
  - 输出 schema:
    ```json
    {
      "candidate_id": "...",
      "relation_type": "same_problem | subproblem_of | follow_up | tool_used_for | preference_signal | contradiction | temporal_next | no_relation",
      "confidence": 0.0,
      "evidence_refs": [],
      "reason": "...",
      "risk_flags": []
    }
    ```
  - acceptance: prompt 明确要求不能因为语义相似就建边;必须允许 `no_relation`

- **任务 9.2.2**
  - description: 新增 `统合模块/脚本/judge_graph_relations.py`
  - 输入:`graph_relation_candidates`
  - 行为:调用 mimo/OpenAI-compatible API 对候选 pair 判边
  - 输出 SQLite 表:`graph_relation_judgments`
  - 字段: `candidate_id`,`relation_type`,`confidence`,`evidence_refs_json`,`reason`,`risk_flags_json`,`model`,`prompt_version`,`temperature`,`created_at`,`gate_status`
  - acceptance: 支持 `--dry-run --limit N` 预览 prompt;支持 `--write --limit N`;失败可 resume,不会重复扣已完成候选

### Wave 9.3: Evidence Gate 与人工 review 队列

- **任务 9.3.1**
  - description: 新增 `统合模块/脚本/evaluate_graph_relation_judgments.py`
  - gate 规则:
    - `relation_type != no_relation`
    - `relation_type` 在白名单内
    - `confidence >= 0.75`
    - `evidence_refs` 非空且能对应原始 source_refs
    - 同一 pair 不允许多个强关系冲突;冲突进入 review
  - 输出:`统合模块/分析数据/ai_context/graph_relation_eval_report.{json,md}`
  - acceptance: 报告包含通过数、拒绝数、review 数、按关系类型分布、低置信度样例

- **任务 9.3.2**
  - description: 建立 `graph_relation_review_queue` 表
  - 进入条件:confidence 0.55-0.75、证据不足、关系冲突、risk_flags 非空
  - acceptance: review queue 可导出 Markdown 供人工抽查,但不入正式图

### Wave 9.4: DuckDB 真关系图谱重建

- **任务 9.4.1**
  - description: 新增或重写 `统合模块/脚本/build_conversation_graph.py`
  - 输入:只读取 `graph_relation_judgments` 中 `gate_status=accepted` 的边
  - 输出:`conversation_graph.duckdb` 新版本
  - 节点:`g_turn`,`g_session`,`g_topic`,`g_tool`
  - 边:`e_relation` 通用边表,字段含 `relation_type`,`confidence`,`evidence_refs_json`,`candidate_id`
  - acceptance: 旧伪关系边 `e_next_turn` / `e_session_topic` 不再作为主关系依据;如保留时序边,必须标记为 `system_temporal`,和 LLM 语义边分开

- **任务 9.4.2**
  - description: 新增图库 smoke query
  - 查询例:某个 MQTT turn 的相关问题、后续任务、工具路径、矛盾关系
  - acceptance: 至少 5 条 query 能返回边、证据和原始 turn 摘要

### Wave 9 验证命令

```powershell
python 统合模块\脚本\build_conversation_vector_store.py --dry-run
python 统合模块\脚本\build_graph_relation_candidates.py --dry-run --limit 100
python 统合模块\脚本\build_graph_relation_candidates.py --write --limit 500
python 统合模块\脚本\judge_graph_relations.py --dry-run --limit 5
python 统合模块\脚本\judge_graph_relations.py --write --limit 100
python 统合模块\脚本\evaluate_graph_relation_judgments.py --write
python 统合模块\脚本\build_conversation_graph.py --write
python 统合模块\脚本\query_conversation_graph.py --smoke
```

### Wave 9 验收标准

- [x] 向量召回只生成候选,没有任何脚本直接把相似度写成图边
- [x] LLM 判边输出固定 schema,有 prompt_version/model/temperature
- [x] `no_relation` 占比被统计,并作为健康指标之一
- [x] accepted 边 100% 有 evidence_refs
- [x] 低置信度和冲突关系进入 review queue,不入图
- [x] DuckDB 图只读取 accepted judgments
- [x] `conversation_graph.duckdb` 的 DEPRECATED 状态被替换为新版本说明,旧伪关系明确归档

### Wave 9 风险

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 向量相似误导 LLM | 图边误判 | prompt 强制证据判定 + `no_relation` + confidence gate |
| LLM 批量成本高 | 执行慢/费用高 | 先 topK 限流、小样本评估、resume、缓存 judgment |
| 关系类型过多 | 图谱不可维护 | 第一版只允许 8 个 relation_type |
| 证据链断裂 | 图不可审计 | evidence_refs 为空直接 rejected |
| 图边过密 | 查询噪声大 | 每节点限制 max accepted semantic edges,低置信度进 review |

## Wave 10: 向量库分类、召回评估与跨库检索策略

> **GSD 元数据**
> - 触发:Wave 8 发现 `personal_events` 与 `conversation_turns` 粒度不同,且向量库分类策略未定。
> - 范围:只优化向量检索层和候选召回质量,不重做图判边。

### Wave 10 目标

1. 明确 `personal_events` 与 `conversation_turns` 的职责边界。
2. 给向量库建立健康检查和召回评估。
3. 为 Wave 9 候选生成提供稳定 topK 策略。
4. 给 `unified_search.py` 提供可解释的跨 collection 合并排序。

### Wave 10.1: Collection Contract

- **任务 10.1.1**
  - description: 新增 `统合模块/脚本/evaluate_vector_collections.py`
  - 检查项:collection 是否存在、count、embedding 维度、metadata 字段覆盖率、source 分布、空文档/短文档数
  - acceptance: 报告明确显示 `personal_events` 和 `conversation_turns` 是否健康

- **任务 10.1.2**
  - description: 写入 `统合模块/分析数据/ai_context/vector_collection_contract.md`
  - 内容:`personal_events=事件级广覆盖`,`conversation_turns=对话 turn 因果链`,`graph_relation_candidates=图候选输入`
  - acceptance: 文档说明不得混合粒度直接比较,跨 collection 排序必须标注来源

### Wave 10.2: Recall Evaluation Set

- **任务 10.2.1**
  - description: 新增固定评测集 `vector_retrieval_eval_set.json`
  - 样本覆盖:MQTT 排障、PPT 一次性任务、代码环境选型、长期偏好、工具链问题、跨 session 相似问题
  - acceptance: 每个 query 有 expected session_id/turn_id 或 expected source,不是 synthetic sample

- **任务 10.2.2**
  - description: `evaluate_vector_retrieval.py` 支持评估 recall@k / MRR / source_mix
  - acceptance: 输出 `vector_retrieval_eval_report.{json,md}`;能比较 only personal_events / only conversation_turns / search_all 三种模式

### Wave 10.3: Cross-Collection Ranking

- **任务 10.3.1**
  - description: 调整 `search_vectors.py::search_all`
  - 规则:保留原始 score,增加 `collection`、`retrieval_unit`、`rank_reason`;默认优先返回 conversation_turns 但不淹没 personal_events
  - acceptance: CLI 输出能看出结果来自哪个 collection 和为什么排在前面

- **任务 10.3.2**
  - description: 图候选生成使用专门候选接口,不复用面向用户的 `search_all`
  - reason:用户检索要高相关解释,图候选要高 recall + 去重 + pair coverage
  - acceptance:`build_graph_relation_candidates.py` 使用独立 topK 函数,并记录 threshold/topK 参数

### Wave 10 验证命令

```powershell
python 统合模块\脚本\evaluate_vector_collections.py --write
python 统合模块\脚本\evaluate_vector_retrieval.py --write --top-k 10
python 统合模块\脚本\unified_search.py semantic "MQTT 预测代码报错" --top-k 5
python 统合模块\脚本\build_graph_relation_candidates.py --dry-run --limit 100
```

### Wave 9/10 实际执行顺序(冲突消解)

虽然文档编号是 Wave 9=图谱、Wave 10=向量策略,但实现时必须按依赖执行:

1. **先做 Wave 10.1 / 10.2**:确认 `personal_events` / `conversation_turns` collection 健康,建立固定召回评估集。
2. **再做 Wave 9.1**:用经过评估的向量召回策略生成 graph relation candidates。
3. **再做 Wave 9.2 / 9.3 / 9.4**:LLM 判边、evidence gate、DuckDB 真关系图重建。
4. **最后做 Wave 10.3**:把跨 collection 排序和展示接回 `unified_search.py`。

这个顺序避免“未评估向量库就喂给 LLM 判边”的地基问题。
### Wave 10 验收标准

- [x] 每个 collection 有明确职责和 metadata contract
- [x] 固定 eval set 能衡量 conversation_turns 是否真的提升召回
- [x] 跨 collection 检索结果可解释,不会把不同粒度结果混为一谈
- [x] 图候选生成使用高召回候选接口,不是面向用户展示的排序接口
- [x] Wave 9 的候选质量可由 Wave 10 报告支撑

---

## PLANNING COMPLETE
