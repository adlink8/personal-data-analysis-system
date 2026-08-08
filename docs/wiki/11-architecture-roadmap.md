# 项目架构总览与路线图演进

> **一句话：** 6 层架构 + D/S/R/A 制品分层，从原始对话到可检索知识的完整管道，辅以决策分析与 Web 驾驶舱。

---

## 6 层架构

```
L6  Control       governance/policies/*.yaml — 架构规则、制品注册表、隐私分类(R1-R4)
L5  Delivery      REST API(:8000) / MCP Server(:8001) / GPT App(:8789+SSE Tunnel)
L4  Application   conversation/ → knowledge/ → memory/ → graph/ → serving/
                  产出 D/S/R/A 四类制品
L3  Domain        规则/模型/常量 — 纯业务语义，不含 IO
L2  Infrastructure adapters/(多源接入) + retrieval/(统一检索层)
L1  Foundation    sqlite / chroma_client / local_embed(512d) / llm / privacy_guard
```

## D/S/R/A 制品分层

```
D 层 — 数据权威（不可变源数据，90 天保留）
  d.canonical_conversation → d.canonical_message
  d.google_normalized

S 层 — 语义解读（LLM/NLP 从 D 衍生）
  s.turn_summary      对话 turn 叙述
  s.knowledge_unit    知识单元（L1/L2 抽取结果）
  s.google_assertion  Google 轻量断言

R 层 — 可重建的检索投影
  r.knowledge_index   Chroma 向量索引（512d, bge-small-zh）
  r.turn_vector       Chroma turn 向量索引
  r.layered_search    知识优先 + 分层退路检索契约

A 层 — 分析/评估输出（只读）
  a.knowledge_evaluation    Eval gate 报告
  a.personal_change         个人状态变化分析
  a.decision_analysis       决策分析
  a.proactive_intelligence  主动情报
```

---

## 数据流水线

```
原始对话（Agent / GPT / Google）
        │
        ▼  source_adapters/
  canonical_messages — 去重、剥离 system 注入、标记 evidence_eligible
        │
        ├──→ L1 抽取（单条消息 → LLM → 知识单元）
        │         ↓
        │    canonicalization（分桶 + Jaccard 去重 → canonical_knowledge_units）
        │
        └──→ L2 抽取（session 窗口 → LLM → 跨轮知识）
                  ↓
             merge into canonical（相似度匹配 → 挂到已有 canonical 或新建）
        │
        ▼
  Chroma 向量索引（bge-small-zh 512d 嵌入）
        │
        ▼
  promote（eval gate → serving snapshot → active pointer 原子切换）
        │
        ▼
  混合检索（knowledge-first + 4 层退路）
```

---

## 项目内分类系统一览

### 知识单元（6 种 unit_type）
| 类型 | 含义 | 示例 |
|------|------|------|
| preference | 偏好 | "我喜欢用 Markdown" |
| habit | 习惯 | "每天早上先看邮件" |
| personal_fact | 个人事实 | "我住在北京" |
| project_decision | 项目决策 | "决定用 FastAPI 做后端" |
| capability | 能力 | "我会 PPT 排版" |
| tool_usage | 工具使用 | "常用 Chrome DevTools" |

### 长期记忆（6 种 memory_type）
tooling / preference / capability / fact / project / habit

### 图谱关系（8 种）
same_problem / subproblem_of / follow_up / tool_used_for / preference_signal / contradiction / temporal_next / no_relation

### Google 断言（4 种）
interest_topic / frequent_service / frequent_channel / domain_affinity

### 合并层
L1_duplicate（三重校验） / L2_topic（余弦近邻） / L3（不合并）

---

## 项目内三套图谱

### 1. 记忆图谱（Memory Graph）
- **节点**：memory_items（工具/偏好/能力/事实/项目/习惯）
- **边**：规则边（memory_relations）+ LLM 判定边（judge_graph_relations）
- **查询**：get_memory_by_subject / neighbors / path / hub / visualize

### 2. 对话轮次图（Conversation Turn Graph）
- **节点**：conversation turn
- **边**：语义近邻 + 时序相邻 + LLM 判定（8 种关系类型）

### 3. 合并层（Merge Layer）
- **不是知识图谱**，是事件去重聚类
- L1：余弦 ≥ 0.97 + Jaccard ≥ 0.80 + 语义骨架唯一值 < 0.5
- L2：余弦 0.88~0.97 + 簇大小 ≤ 50
- L3：超大簇保护，不入合并表

---

## 检索逻辑

**knowledge-first + layered fallback**：

```
Phase 1:  knowledge_unit        ← 知识单元向量检索（Chroma）
Phase 2a: canonical_messages    ← 对话原文（退路）
Phase 2b: conversation_turns    ← turn 叙述（退路）
Phase 3:  non_dialogue_raw      ← Google 非对话事件（退路）
Phase 4:  legacy_pad            ← 其他来源填充（退路）
```

- 单次 embedding 复用到所有层
- 每条结果过 evidence gate（6 项检查），不通过则标记 `evidence_supported=false`
- top_k 钳制到 [1, 20]

---

## 全网关一览

| 关卡 | 位置 | 检查内容 |
|------|------|----------|
| evidence gate (6项) | relevance.py | 证据引用存在、原文匹配、confidence≥0.6、lifecycle≠stale、非abstain、来源有效 |
| schema gate | build_knowledge_units.py | JSON 解析 + Pydantic 校验 → schema_invalid/total < 5% |
| reconcile gate | build_knowledge_unit_vector_store.py | missing=0 AND orphan=0 AND duplicate=0 |
| eval gate | promote_knowledge_index.py | 评测必须是 PASS 才允许 promote（fail-closed） |
| 多源门禁 | search_knowledge_units.py | serving snapshot 版本一致性检查 |
| 隐私门禁 | privacy_guard.py | 明文密钥/凭据自动封存 |
| 决策门禁 | gates.py | 无证据、过期、冲突、注入、高风险输出全部拒绝 |

---

## 路线图演进

```
v1.1 (Ph 01-27)  管道搭建 — 29 phases, 76 plans ✅
  ├─ 建基础：抽取 → 存储 → 检索 → 评估
  └─ 搭上层：状态 → 决策 → 主动情报

v1.2 (Ph 28-31)  外部引入 — 4 phases, 14 plans ✅
  └─ External Context + LLM 决策分析 + 低风险试飞 + 校准

v1.3 (Ph 32-35)  产品包装 — 4 phases, 12 plans ✅
  └─ MCP 工具(44个) + Tunnel + 受控决策编排

v1.4 (Ph 36-40)  Web 驾驶舱 — 5 phases, 18 requirements 🚧
  ├─ 36 安全基线 ✅ / 37 状态展示 ✅ / 38 决策工作区 ✅
  ├─ 39 反馈/主动情报 ✅ / 40 产品硬化 ⏳（pending_human_uat）
  └─ 总进度 4/5 完成

v1.4.1 (Ph 41-43) 数据治理修补 — 3 phases 🚧
  ├─ 41 知识抽取疆域重定义（assistant 轨） ✅
  ├─ 42 会话级去重键 ⏳ 部分完成
  └─ 43 L2 重定义（跨轮状态 + 增量去重） ⏳ 部分完成

v1.5 (预规划)  Personal Knowledge Wiki — 未激活
  ├─ 原设计：确定性投影（已暂停，见 notes）
  └─ 重新设计方案：[12-wiki-redesign-proposal.md](12-wiki-redesign-proposal.md)
      └─ 核心改动：LLM 驱动的全源摘要缓存层，接入检索层
```

---

## Web 驾驶舱（Cockpit）页面一览

| 路由 | 页面 | 展示内容 |
|------|------|----------|
| `/` | 总览 | 目标/约束/变化/决策队列/风险 |
| `/state` | 个人状态 | 按 domain 分组，Fact/Observation/Inference 区分 |
| `/decisions` | 决策中心 | 推荐列表 |
| `/decisions/:id` | 决策工作区 | 方案比较 → 预览 → 确认（唯一可写页面） |
| `/actions` | 行动/结果 | 决策链追溯 |
| `/external` | 外部上下文 | Python/Node.js 版本信息 |
| `/proactive` | 主动情报 | 系统主动提醒 |
| `/evidence` | 证据下钻 | 状态/决策的证据链详情 |
| `/system` | 系统状态 | 服务健康、snapshot 版本、freshness |

设计铁律：
- **只读为主**：浏览器不直连 DB，不调 LLM，不改 authority
- **降级不崩溃**：单权威不可用时该节置 null，不整页白
- **唯一写入口**：决策工作区必须走 prepare → preview → confirm 三步

---

## 外部数据来源

目前只允许两个源，手动导入，非自动爬取：

| 来源 | 类型 | 端点 |
|------|------|------|
| ext.python_releases | official_release_index | python.org/downloads/ |
| ext.nodejs_releases | official_release_index | nodejs.org/dist/index.json |

只存结构化元数据（版本号/发布时间），不存页面正文。加新源需要改代码白名单。
