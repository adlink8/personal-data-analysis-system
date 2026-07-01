# Phase 07 Review: 方向调整反馈 (2026-06-27)

**状态**: Wave 1-4 已落地执行,执行结果与初心对齐度复盘
**触发**: 用户在检查叙述摘要质量时,发现数据流跑偏 + mem0 方案不适配需求
**结论**: Wave 1-3 的清洗本身正确,但产物没有回流到检索主流水线;Wave 4 的 mem0 压缩方案不适合本项目需求

---

## 1. 初心复述(用户原话)

> "我引入 mem0 就是因为之前的数据太乱,所以之后的检索判断很难,所以将杂乱的数据先整理好结构化再存入数据库和向量库保证后续的过程"

翻译成数据流目标(一条直线):

```
杂乱raw → [结构化清洗] → 干净的 event/memory → 入库(SQLite + 向量库) → 检索判断
```

核心诉求:**清洗是为了让下游检索更好用**,不是为清洗而清洗。

---

## 2. 跑偏诊断:清洗产物成了"展览品",没有回流

Wave 1-4 执行后,实际数据流长成了树状旁路,4 个清洗产物**互不交汇、都没回到主流水线**:

```
raw
  ├─ Agent jsonl ──→ normalize_agent_conversations ──→ agent_data.sqlite (v2 旁路表)
  │     ✗ 没进 unified_events / 没进向量库
  ├─ GPT/Agent user 消息 ──→ build_conversation_segments ──→ conversation_segments.json (8.4MB)
  │     ✗ 没进 unified_events / 没进向量库
  ├─ segments ──→ build_conversation_summary ──→ conversation_summaries.json/md
  │     ✗ 没进 unified_events / 没进向量库
  └─ segments ──→ build_mem0_candidate_memory ──→ mem0_candidate_memories.json
        ✗ PLAN 强制不进 memory_items / 没进向量库
```

### 证据(unified_events 实测)

| 事件类型 | 数量 | 说明 |
| --- | --- | --- |
| agent_file | 2932 | 文件清单,非对话内容 |
| activity | 1696 | Google 活动流 |
| message:user | 757 | **全部来自 GPT,Agent 对话一条都没有** |
| message:assistant | 769 | **全部来自 GPT,Agent 对话一条都没有** |
| skill / agent_session / memory | 527/518/347 | 元数据/索引,非对话内容 |

**Agent 的逐条对话(GPT 之外第二大对话源)根本没进检索库**。Phase 07 清洗 Agent 数据后,清洗结果躺在旁路表/旁路 json 里,没回到 unified_events,也没进 chroma。

### PLAN 的"隔离原则"被误执行成"永久旁路"

PLAN.md 的隔离原则本身正确(防止候选污染正式记忆),但执行时缺少了**最后的回流步骤**:把 review 通过的候选 / turn 摘要,灌回 unified_events 或单独建检索 collection。隔离做成了断流。

---

## 3. mem0 方案不适配需求:压缩度太狠,细节丢失

用户原话:
> "mem0 方案不是很适合我的需求,压缩度太狠了,我需要的是信息密度大但是细节不能丢失,而是整理上下文逻辑主干和分支"

### 实证对比(mem0 候选 vs conversation_summary)

同一份对话,两种处理结果对比:

**mem0 候选**(压缩到原子事实,丢失上下文逻辑):
- `[topic] 用户对PPT制作有明确的排版和设计偏好:注重排版、动画效果、简约风格...`
- `[topic] 用户要求重构《Linux操作系统》课程的PPT,按照技能方向重新组织内容...`

问题:
1. **一次性操作指令被当成稳定偏好**(重构 PPT 是一次任务,不是偏好)
2. **因果链和时序完全丢失**(看不到"用户先做了什么→助手怎么回应→得出什么结论")
3. **细节被压缩到无法回溯决策过程**(只剩干瘪的 claim)

**conversation_summary**(保留主干和分支,用户认可的方向):
- `Turn 4: 用户提供了 MQTT+线性回归代码...助手分析理论上应该持续运行在 client.loop_forever(),但可能因 Code Runner 的 Output 面板行为导致进程瞬间结束;建议用终端运行...`
- `Turn 7: 用户提供了完整的错误栈...助手分析 payload 是浮点数而非字典...提供两种修法...建议先打印原始消息内容确认实际格式。`

优势:
1. **信息密度大**(一个 turn 包含 问题→分析→结论→建议)
2. **细节不丢失**(具体函数名、错误行号、修法都保留)
3. **主干和分支清晰**(能看到对话演进和决策路径)

### 方向结论

用户要的是 **conversation_summary 的形态**(主干+分支+细节),不是 mem0 的**原子事实压缩**。两者目标不同:

| 维度 | mem0 (原子事实) | conversation_summary (叙述主干) |
| --- | --- | --- |
| 目标 | 高压缩,提炼稳定事实 | 高密度,保留逻辑脉络 |
| 信息形态 | 离散 claim | turn 级叙述段 |
| 因果链 | ✗ 丢失 | ✓ 保留 |
| 细节 | ✗ 大量丢失 | ✓ 保留 |
| 适配检索 | 适合"用户喜欢什么"类查询 | 适合"用户做过什么/怎么做的"类查询 |

**决策:Wave 4 的 mem0 压缩方案降级为可选实验,主线转向 conversation_summary 形态的回流。**

---

## 4. 附带发现:向量库按 event_id 一条一向量,对话因果链断裂

检查 `build_vector_store.py` 发现:每条 `event_id` → 一个向量。对 GPT 已入向量库的 1526 条 `message:user/assistant`,user 问句和 assistant 回答**各自独立成向量**,检索时因果链断了。

这不是 Phase 07 引入的(是阶段二的老设计),但属于"清洗后入库"这个初心的一部分,应纳入本次方向调整一并解决。

---

## 5. 方向调整:新增 Wave 6 (回流) + Wave 4 降级

### Wave 4 调整:mem0 从主线降为可选

- 保留 `build_mem0_candidate_memory.py` 和已生成的候选文件(不删,作为实验记录)
- PLAN 的 acceptance criteria 不变(候选不污染 memory_items 的纪律仍有效)
- **不再作为 Phase 07 的主线产出**,移出 Phase Verification 主路径

### Wave 6 新增:清洗产物回流主流水线

目标:把 conversation_summary 的 turn 叙述作为**新的可检索单元**回流到主流水线,闭环初心。

候选实现方向(待 PLAN 细化):

| 子问题 | 候选方案 |
| --- | --- |
| Agent 对话缺席检索 | 把 turn 级叙述摘要作为新 event_type 灌入 unified_events |
| GPT 对话因果断裂 | 向量库按 conversation+turn 聚合后再向量化,而非逐条 message |
| 向量库切块粒度 | 单元=turn 摘要(含 user+assistant+tool 因果),不是单条 message |

详细 PLAN 见 `PLAN.md` 的 Wave 6 章节。

---

## 6. 不变项(Wave 1-3 的清洗仍然有效)

- Agent jsonl → v2 旁路表的解析和回溯链(raw_file + line_no)正确,保留
- conversation_segments 的 user 想法切分逻辑正确,保留
- conversation_summary 的 per-turn 去重 + turn 组装 + 叙述生成(本次已修 bug)正确,保留
- mem0 候选层的隔离纪律(不污染 memory_items)正确,保留

**这次调整不是推翻 Wave 1-3,是补上缺失的回流这一步。**

---

*Phase: 07-agent-conversation-normalization-mem0-spike*
