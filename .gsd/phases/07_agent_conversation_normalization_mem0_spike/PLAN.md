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

1. 新增 `统合模块/脚本/build_conversation_event_layer.py`。
   - 输入:`conversation_summaries.json`(已生成的 turn 叙述)
   - 输出:把每个 turn 叙述作为新 event 写入 `unified_events` + `unified_events_rich`。
   - event_type 取 `conversation_turn`,source 取 `Agent`/`GPT`(按 summary 的 source 字段)。
   - 每条 event 保留 `source_refs`(回溯到原始 jsonl 行)和 `session_id`/`turn_id` 元数据。
   - 幂等:重复运行不产生重复 event(用 `session_id + turn_id` 做去重键)。

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
python 统合模块\脚本\build_conversation_event_layer.py --write
python 统合模块\脚本\build_vector_store.py --resume  # 或新 collection 脚本

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
7. **Wave 7:清洗产物回流主流水线(★ Phase 07 主线,2026-06-27 新增)**。🔄 代码完成,入库待 chroma 服务

## Wave 7 实施记录(2026-06-27)

- **回流去向**:用户拍板 B 方案(独立 collection `conversation_turns`,不碰 `personal_events`)。
- **代码完成**:
  - `build_conversation_vector_store.py`:turn 叙述向量化入库,独立 collection,幂等。
  - `search_vectors.py` 改造:新增 `search_conversation_turns` + `search_all`(跨 collection 合并检索)。
  - `unified_search.py` 改造:`search_semantic` 默认 `include_turns=True`,CLI/MCP/Agent 全接入。
  - `run_pipeline.py` 新增步骤 13(turn 叙述回流)。
- **待执行**(需 chroma 服务在线):
  - Wave 7-2: `build_conversation_summary.py --write` 生成全量 turn 叙述(105 个 session,约 200-400 次 LLM 调用)。
  - 步骤 13 实际入库验证。
- **Wave 7-4 降级**:GPT 对话因果断裂修复需先建 GPT turn 切分层,且会改动 `personal_events`,违背"不破坏原数据"惯例。降级为后续增强,主线(Agent 回流)已闭环。

## Phase Verification

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --dry-run --limit-files 5
python Agent\结构化数据\脚本\normalize_agent_conversations.py --write
python 统合模块\脚本\build_conversation_segments.py --dry-run --source Agent --limit 20
python 统合模块\脚本\build_conversation_segments.py --dry-run --source GPT --limit 20
python 统合模块\脚本\build_conversation_summary.py --limit 10 --write
python 统合模块\脚本\evaluate_conversation_prompt.py --write --limit 10
python 统合模块\脚本\build_conversation_event_layer.py --write
python 统合模块\脚本\build_vector_store.py --resume
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

## PLANNING COMPLETE





