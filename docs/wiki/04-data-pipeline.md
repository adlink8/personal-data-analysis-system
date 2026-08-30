# 数据加工管线

> **一句话：** 原始对话 → 归一化 → 知识提取 → 检索索引 → 智能分析。五层加工，每层产出可以独立验证。

---

## 一开始：原始数据在哪儿

你的数据最初存在三个地方：

```
① AgentsView sessions.db（只读，不碰它）
   每天你用 Claude Code 的对话记录都在这里
   → pk-sync conversations 读取它

② Google Takeout 导出
   Chrome 上网记录、YouTube 观看历史
   → pk-sync google 处理它

③ 外部公开元数据（Python/Node.js 版本信息等）
   → external_context/ingest 处理
```

---

## 第 1 层：归一化（Data, 简称 D 层）

**输入：** 各个数据源的原始格式
**输出：** 统一格式的规范化数据
**是否调 LLM：** ❌ 不调

```
AgentsView 原始对话
     │
     ▼
① import_agentsview_sessions    → 扫出增量清单（只报告，不写）
② build_agentsview_normalized    → 写入 agentsview_normalized.sqlite
③ build_canonical_agent_conversations → 写入 agent_conversations.sqlite（对话 SSOT）

Google Takeout 原始事件
     │
     ▼
④ build_google_normalized_events → 写入 google_data.sqlite
⑤ build_google_light_assertions  → 写入 light_assertions（聚合断言）
```

**这层的结果是"信源"——一旦写入，后续所有处理都基于它。**

---

## 第 2 层：知识提取（Semantic, 简称 S 层）

**输入：** 规范化对话
**输出：** 结构化 Q&A 知识单元
**是否调 LLM：** ✅ 调（extract + canary 阶段）

这是最值钱的一层——把原始对话变成"问题-答案"对。

### 完整流程（pk-ku 一站式管理）

```powershell
① inspect     ← 免费。比较当前对话 vs 上次处理到的位置，列出新增内容
② prepare     ← 免费。冻结增量清单，生成 run_id
③ extract     ← 付费！对每条新内容调 LLM，提取 Q&A
④ extract-gate← 免费。检查 yield 阈值（user 轨 0.7 / assistant 轨 0.3）、隐私通过、schema 有效
⑤ canonical   ← 免费。staging → canonical 表
⑥ publish     ← 免费。增量发布（additive，不覆盖旧的）
⑦ vector      ← 免费。候选向量索引构建
⑧ canary      ← 付费！30 条测试查询 + LLM 标签，检查质量
⑨ promote     ← 免费。候选 → active 索引
⑩ watermark   ← 免费。记录当前进度
```

**关键规则：** 日常只跑增量（delta），不跑全量。全量需要特殊授权 `PK_KU_ALLOW_FULL_INVENTORY_START=1`。

### 这层产出的东西

```
S 层（语义解释）：
  canonical_knowledge_units 表   ← 知识单元 Q&A
  turn_summaries（JSON 文件）    ← 对话轮次摘要
  google_light_assertions        ← Google 聚合断言
```

---

## 第 3 层：检索索引（Retrieval, 简称 R 层）

**输入：** 知识单元 + 原始事件 + 对话轮次
**输出：** 三个 Chroma 向量集合
**是否调 LLM：** ❌ 不调

| Chroma 集合 | 内容 | 维度 | 用途 |
|------------|------|------|------|
| `knowledge_units_ir_*` | 知识 Q&A（版本化，每次 promote 产生新集合） | 512 | 知识层检索 |
| `personal_events` | 原始事件 | 512 | raw fallback |
| `conversation_turns` | 对话轮次叙述 | 512 | dialogue fallback |

**为什么有三个集合？** 搜索策略是 "knowledge-first + layered fallback"——先查知识集合，不够再从对话集合补，再不够从原始事件补。详细机制在 [搜索机制](05-search-mechanism.md)。

---

## 第 4 层：智能分析（Analysis, 简称 A 层）

**输入：** 知识单元 + 个人状态
**输出：** 不可变分析 run
**是否调 LLM：** ❌ 不调（temperature=0，本地确定性计算）

| 分析类型 | 做什么 | 产出 |
|---------|--------|------|
| 个人状态 | 从知识单元推断当前目标/约束/观察 | `a.personal_change`（不可变 run） |
| 决策推荐 | 基于状态变化 + 外部事实给出建议 | `a.decision_feedback`（不可变 run） |
| 主动情报 | 按重要性/新颖性排名 inbox 候选 | `a.proactive_intelligence`（不可变 run） |
| 决策分析 | 结构性分析 run（claims/evidence refs） | `a.decision_analysis` |
| 项目 Pilot | 低风险项目 case/outcome | `a.project_pilot` |
| 校准 | 校准 protocol/verdict | `a.recommendation_calibration` |

**这类产出的特点：**
- 不可变：每个 run 有 manifest checksum，内容不能改
- 元数据优先：默认不返回私有正文
- 可弃权（abstention）：证据不足时 fail-closed，不编造

---

## 完整加工路径图

```
外部输入
   │
   ├── AgentsView 对话 ──→ pk-sync conversations
   ├── Google Takeout  ──→ pk-sync google
   └── 公开元数据      ──→ external_context
            │
            ▼
    ┌───────────────────────────────┐
    │ D 层：归一化规范库              │
    │ agent_conversations.sqlite     │
    │ google_data.sqlite             │
    │ external_context.sqlite        │
    └───────────────┬───────────────┘
            │
            │ pk-ku inspect → prepare → extract(LLM)
            ▼
    ┌───────────────────────────────┐
    │ S 层：知识单元                 │
    │ canonical_knowledge_units     │
    │ turn_summaries                │
    │ google_light_assertions       │
    └───────────────┬───────────────┘
            │
            │ promote → active Chroma
            ▼
    ┌───────────────────────────────┐
    │ R 层：检索索引                 │
    │ knowledge_units_ir_*          │
    │ personal_events               │
    │ conversation_turns            │
    └───────────────┬───────────────┘
            │
            │ intelligence/ 读取
            ▼
    ┌───────────────────────────────┐
    │ A 层：智能分析                 │
    │ personal_state → decision     │
    │ → proactive → analysis        │
    │ → pilot → calibration         │
    │ (全部不可变 run)               │
    └───────────────┬───────────────┘
            │
            ▼
    REST/MCP 服务 / Decision Cockpit
```

---

## 三条独立流水线

实际运行时并行跑三条互不影响的流程：

| 流水线 | 频率 | 入口 | 贵不贵 |
|--------|------|------|--------|
| **对话同步** | 每天 | `pk-sync conversations --write` | 免费 |
| **知识提取** | 对话同步后 | `pk-ku inspect → extract → promote` | extract 阶段花钱（LLM） |
| **智能分析** | 知识更新后 | `intelligence/` 内部自动编排 | 免费（本地计算） |
