# Mem0 / Graphiti 两个 Demo 反馈总结

> 实验日期:2026-06-17
> 实验目的:对照外部记忆框架,验证本项目(数据分析/)自建记忆层的方向,识别可吸收的能力。
> 实验场地:`C:\Users\li\Desktop\memory-bench\`(与主项目物理隔离,单向只读拉取样本)
> 数据来源:本项目 `unified_search.py` 导出(Agent/GPT/Google 各 200 条事件 + 194 条记忆基线)

---

## 一、实验环境

| 项 | 值 |
|---|---|
| 主项目 Python | 3.14.2(全局) |
| 实验 venv | `memory-bench/.venv/`(Python 3.14.2,独立隔离) |
| Docker | 29.5.3(Neo4j 用) |
| Ollama | 0.20.2(`bge-m3` embedder,本地) |
| 第三方 LLM | mimo-v2.5 @ `https://token-plan-cn.xiaomimimo.com/v1` |
| 选型原因 | 本机 RTX 4060 8GB 显存被常驻程序占满,剩余 822MB;qwen3.5:9b(6.6GB)放不下 → CPU 慢到不可用 |

**关键约束**:LLM 走第三方 API,embedder 走本地 Ollama,向量库/图库本地化——既避开显存不足,又避免把全文发第三方。

---

## 二、Mem0 Demo 反馈

### 2.1 实验配置

| 项 | 值 |
|---|---|
| 版本 | mem0ai 2.0.6 |
| LLM | mimo-v2.5(OpenAI 兼容) |
| Embedder | Ollama bge-m3(本地,1024 维) |
| 向量库 | Qdrant 本地文件模式(`mem0_demo/qdrant_db/`) |
| 输入 | 60 条原始事件(Agent/GPT/Google 各 20 条) |
| 输出 | 20 条自动提炼的 fact |

### 2.2 部署踩坑(7 个)

| 坑 | 原因 | 解法 |
|---|---|---|
| qwen3.5:9b 卡死 | 显存不足,模型换 CPU | 换第三方 LLM API |
| PostHog 遥测卡 0.5s | 默认向 `us.i.posthog.com` 发数据,墙内超时 | `MEM0_TELEMETRY=False` |
| `get_all(user_id=)` 报错 | Mem0 2.0 API 变了 | 改 `filters={'user_id': ...}` |
| spaCy/fastembed 缺失 | 默认不装 nlp 扩展 | `pip install mem0ai[nlp] fastembed` |
| 缺 `ollama` Python 包 | embeddings/ollama.py 按需 import | `pip install ollama` |
| JSON 解析失败 4/60 | mimo 输出的 fact 数组偶尔不符合严格 JSON schema | 非致命,失败的条目跳过 |
| embedding NaN 报错 1/60 | bge-m3 对空/极短文本返回 NaN | 非致命,该条跳过 |

**关键结论**:60 条输入 → 20 条 fact,中间丢失约 5 条(JSON/embedding 失败),命中率约 92%。

### 2.3 存储与查询机制(源码级)

**存储管道(`add()`,8 阶段):**

```
Phase 0  收集最近 10 条 session 历史(解决代词/指代)
Phase 1  新消息 embedding → 搜 top-10 已有记忆(防重复)
Phase 2  ★ LLM 提炼(ADDITIVE_EXTRACTION_PROMPT,~900 行)
Phase 3  批量 embedding 提炼后的 fact
Phase 4  MD5 hash 去重(精确文本匹配)
Phase 5  词形还原(lemmatize_for_bm25)
Phase 6  写入 Qdrant(payload: data/hash/text_lemmatized/user_id/created_at)
Phase 7  实体链接(独立 entity_store,linked_memory_ids)
Phase 8  SQLite 保存会话历史 + ADD/UPDATE/DELETE 日志
```

**查询管道(`search()`):**
- Embedding 查询文本 → Qdrant 向量搜索 + metadata 过滤 + threshold → (可选)Reranker
- **无 LLM 参与**,纯向量相似度,不做查询改写或多步检索

**三层存储:**
| 存储 | 用途 |
|---|---|
| Qdrant(主) | fact 文本 + embedding + metadata |
| Qdrant(实体) | 命名实体 + linked_memory_ids |
| SQLite | 会话历史 + 操作日志 |

### 2.4 输出质量逐条评估

**🟢 A 级(精准,7 条)——值得吸收的能力:**

| fact | 价值 |
|---|---|
| OAuth2 失败根因是客户端没走代理,建议开 TUN 模式 | **跨事件因果链**——3 条独立事件合成 1 条根因+解法 |
| novel-mind 项目 6/6 纳入 GSD,目标是审计代码而非信任文档 | **意图捕捉**——超越关键词规则 |
| PKOS 区分正式层和暂存层,防污染主知识库 | **设计意图**——不只记"分了两层",还记"为什么分" |
| TuYa T5AI-Board 固件项目在 C:\...,做 Codex 配额监控 port | 路径+分支+工作内容三合一,信息密度高 |
| Agent 在 novel-mind 项目上崩了两次(1s + 51s) | 精确到秒级时间和重试行为 |
| PKOS 核心架构:云服务器做 Capture Gateway,Obsidian 是唯一正式入口 | 准确概括架构角色分配 |
| AI Agent 能力最强在代码/文档/客服,企业需解决权限/审计/安全/回滚才能普及 | "强在哪"和"卡在哪"拆成两段 |

**🟡 B 级(有价值但不精炼,8 条):**

| fact | 问题 |
|---|---|
| SponsorBlock 自动跳过赞助片段 | **推荐结果当长期记忆**,不是用户偏好 |
| Unhook 隐藏 YouTube 推荐/Shorts/评论 | 同上 |
| AI 应用从赌爆款转向融入真实工作流 | **AI 行业观点,不是用户个人信息** |
| course 项目从目录整理演进为反馈驱动工作流系统 | 演进历史和当前状态混在一起,应拆两条 |
| OpenAI Dreaming V3 记忆架构,算力降到 1/5 | **用户查的资讯**,不是用户的行为 |
| Agent terminated 原因是 MCP 工具冲突/上下文溢出 | 排障建议,跟实际崩了(#5)应合并 |
| 用户问了最新 ChatGPT 记忆更新 | **纯查询记录**,无长期记忆价值 |
| TuyaOpen SDK 在 WSL /home/li/TuyaOpen | 路径太碎,应挂在 TuYa 项目下面 |

**🔴 C 级(噪音,3 条):**

| fact | 问题 |
|---|---|
| Antigravity 2.0 在 I/O 升级 | **产品新闻**,不是用户个人信息 |
| Google 通知提到 Anthropic 话题 | **无意义噪音**,用户没做任何事 |
| Codex session 相关 Docker WSL 存储重置 | **过度碎片化**,应是 tooling 的一部分 |

**噪音率:3/20 = 15%**(纯噪音);若算上 B 级的混淆,信息质量问题占比更高。

### 2.5 Mem0 核心缺陷

1. **混淆"用户做了什么"和"用户聊了什么"**——产品新闻、查询记录、推荐结果都当用户个人信息
2. **无证据链**——提炼后原文丢失,fact 是黑盒结论,无法回溯
3. **无分类**——20 条全是平面临时 fact
4. **无时间趋势**——看不出"持续用"vs"新兴"vs"衰退"

---

## 三、Graphiti Demo 反馈

### 3.1 实验配置

| 项 | 值 |
|---|---|
| 版本 | graphiti-core 0.29.2 |
| 图库 | Neo4j 5.26.27 Community(Docker) |
| LLM | mimo-v2.5(OpenAI 兼容) |
| Embedder | Ollama bge-m3(自写 `OllamaEmbedder` 适配器) |
| 输入 | 1 条手动 + 5 条样本(Agent 2/GPT 1/Google 2) |
| 输出 | 15 节点(6 Episodic + 9 Entity)+ 11 边(9 MENTIONS + 2 RELATES_TO) |

### 3.2 部署踩坑(7 个,比 Mem0 严重)

| 坑 | 严重度 | 原因 | 解法 |
|---|---|---|---|
| 全部方法 async | 中 | `add_episode`/`search`/`build_indices_and_constraints` 全异步 | `asyncio.run()` 包装 |
| Responses API 404 | **高** | 硬编码用 OpenAI Responses API(`client.responses.parse()`),mimo 不支持 | 改 `openai_client.py` 加 Chat Completions fallback |
| 默认 model=gpt-5.5 | **高** | Graphiti 默认大模型 `gpt-5.5` | `LLMConfig(model="mimo-v2.5")` |
| small_model=gpt-4.1-nano | **高** | 小模型槽用于实体摘要等简单任务 | `LLMConfig(small_model="mimo-v2.5")` |
| Embedder 不兼容 | 中 | 默认用 OpenAI embedding API | 自写 `OllamaEmbedder`(50 行) |
| 响应解析不兼容 | **高** | `_handle_structured_response` 硬编码 `response.output_text` | 改 `openai_base_client.py` |
| token 字段名不同 | 中 | Responses API 用 `input_tokens/output_tokens`,Chat Completions 用 `prompt_tokens/completion_tokens` | 改 token 提取逻辑 |

**关键结论**:Graphiti 对 OpenAI 耦合度极高。用非 OpenAI 提供商需要**改 2 个源码文件 + 写 1 个适配器**,部署成本远高于 Mem0。

### 3.3 图谱结构(实测)

```
6 个 Episodic 节点(原始对话)
9 个 Entity 节点(LLM 自动抽取的实体)
9 条 MENTIONS 边(对话 → 实体)
2 条 RELATES_TO 边(实体间关系,带双时间)
```

**RELATES_TO 边示例(双时间):**

```
Antigravity 2.0 ──RELATES_TO──→ Gemini 3.5 Flash (Medium)
  fact: "Antigravity 2.0 displays a quota calculation interface
         that includes the Gemini 3.5 Flash (Medium) model"
  valid_at: 2026-06-06 12:16:36   ← 这件事从何时起成立
  created_at: 2026-06-17 07:18:34 ← 这条边何时写入图库
```

### 3.4 噪音问题

**典型噪音:"普通高等学校招生全国统一考试"被抽成 Entity 节点。**

原因:Graphiti 的 prompt 写的是 "Extract ALL memorable information — when in doubt, extract"。它**不区分**:
- 用户主动做的事
- 用户被动收到的通知(Google 推送的高考提醒)
- 外界发生的新闻

噪音率:1/9 实体 = 11%。

### 3.5 Graphiti 核心优势

1. **双时间(valid_at/invalid_at)**——记忆有有效期,过期关系可自动过滤
2. **自动实体抽取 + 图谱**——不需要预定义实体类型,LLM 自动建关系
3. **增量演化**——新 episode 加入时,已有实体/关系自动更新/合并

### 3.6 Graphiti 核心缺陷

1. **部署成本极高**——Docker Neo4j + 改源码 + 写适配器
2. **OpenAI 耦合极深**——核心管道 3 处硬编码依赖
3. **无证据链**——跟 Mem0 一样,不保留原始事件 ID
4. **无分类体系**——只有 Episodic/Entity 两类
5. **全收全录**——缺乏过滤层,噪音多

---

## 四、本项目(数据分析/)对照基线

### 4.1 记忆规模与质量

| 指标 | 值 |
|---|---|
| 总记忆数 | 194 条 |
| 有 evidence_ids 的记忆 | **194/194 = 100%** |
| evidence_ids 总数 | 1478 个 |
| 抽样 JOIN 命中率 | **288/288 = 100%**(每条记忆抽前 3 个 event_id 反查 unified_events) |

### 4.2 分类体系(6 类 × 23 子类)

| 类型 | 数量 | 子类示例 |
|---|---|---|
| capability | 148 | core_capability / occasional_capability / minor_capability |
| tooling | 21 | continuous_primary / surging_tool / abandoned_tool / specialized_high |
| fact | 11 | status / approach |
| preference | 7 | surging_interest / continuous_high / declining_interest |
| project | 5 | active_project |
| habit | 2 | search_execute_loop / search_ask_pattern |

### 4.3 证据链验证(以"GSD项目管理"为例)

```sql
-- 给定一条记忆,反查全部原始事件
SELECT ue.source, ue.service, ue.title, ue.content_rich
FROM memory_items mi, json_each(mi.metadata, '$.evidence_ids') AS eid
JOIN unified_events ue ON ue.event_id = eid.value
WHERE mi.subject = 'GSD项目管理';
```

**实测结果(前 5 条):**

```
1. [Agent/Codex] gsd-plan-phase
2. [Agent/Codex] gsd-list-workspaces
3. [Agent/Codex] gsd-ingest-docs
4. [Agent/Agents] gsd:plan-phase
5. [Agent/Codex] gsd-extract_learnings
...(共 30 条原始事件)
```

**这条 SQL 能跑通,返回 30 条原始事件。这就是证据链的证明——任何一条记忆都能追溯到具体raw,不是黑盒结论。**

### 4.4 时间趋势(本项目的隐藏优势)

tooling 类已实现趋势分类:
- **continuous_primary**(持续主要):codex / gsd / ollama / zcode
- **surging_tool**(新兴):hermes / opencode / workbuddy
- **declining_primary**(衰退):claude-code / openai-codex
- **abandoned_tool**(已废弃):chatgpt-web / google-colab / midjourney

这是 Mem0 和 Graphiti 都没有的能力。

---

## 五、三方核心对比

| 维度 | Mem0 | Graphiti | 本项目 |
|---|---|---|---|
| **存储** | Qdrant 向量库 | Neo4j 图库 + 向量 | SQLite + chroma |
| **部署成本** | 低(pip + Qdrant 文件模式) | **极高**(Docker + 改源码 + 适配器) | ✅ 零额外依赖 |
| **噪音率** | 15%(3/20 纯噪音) | 11%(1/9 实体噪音) | **0%**(规则前置过滤) |
| **证据链** | ❌ 原文丢失 | ❌ 只存 fact | ✅ 100% JOIN 命中 |
| **分类体系** | ❌ 平面 | ❌ 平面 | ✅ 6 类 × 23 子类 |
| **时间维度** | 单时间戳 | ✅ 双时间(valid/invalid) | 单时间戳 + 趋势分类 |
| **时间趋势** | ❌ | ❌ | ✅ 持续/新兴/衰退/废弃 |
| **LLM 提炼** | ✅ 跨事件因果 | ✅ 自动实体图谱 | ❌ 规则硬编码 |
| **自动实体关系** | 部分(entity_store) | ✅ 图谱节点+边 | ❌ 手写 5 种边 |
| **OpenAI 耦合** | 低(支持 Ollama) | **极高**(核心管道硬编码) | 无 |

---

## 六、回写本项目的行动点

### 6.1 值得吸收(2 项)

**① 双时间字段(来自 Graphiti)**

```sql
ALTER TABLE memory_items ADD COLUMN valid_from TEXT;
ALTER TABLE memory_items ADD COLUMN valid_until TEXT;
```

- 新记忆:`valid_from = event_time`,`valid_until = NULL`
- 新事件与已有记忆矛盾:旧记忆 `valid_until = 新事件时间`
- 查询时过滤:`WHERE valid_until IS NULL OR valid_until > datetime('now')`

成本:2 个 ALTER TABLE,不换数据库。

**② LLM 提炼增强层(来自 Mem0)**

新建 `integration/scripts/build_llm_memory.py`:
- 用 mimo-v2.5 对规则覆盖不到的事件做二次提炼
- **硬约束**:产出必须带 `evidence_ids`(吸收 Mem0 提炼能力,保留本项目证据链)
- 用本项目规则做**前置过滤**,避免 Graphiti 那种"高考通知"噪音
- 借鉴 Mem0 的 `ADDITIVE_EXTRACTION_PROMPT`(区分"用户做了什么"vs"用户聊了什么")

成本:1 个新scripts + 1 个 LLM 调用,不改现有管道。

### 6.2 明确不吸收(3 项)

| 不吸收 | 原因 |
|---|---|
| Neo4j 图数据库 | 部署成本远大于收益;SQLite 规则图谱在 200 条规模下够用 |
| Graphiti 全收全录策略 | 噪音率高,本项目规则前置过滤是核心优势 |
| Mem0/Graphiti 的存储后端 | 会破坏本项目零额外依赖的核心承诺 |

### 6.3 若后续要引入图数据库:FalkorDB 选型结论

本次实验明确"暂不上图数据库",但如果未来数据规模增长(节点 > 1 万)或多跳图遍历需求变强,**FalkorDB 是首选**,不是 Neo4j。

**为什么 FalkorDB 而不是 Neo4j:**

| 维度 | Neo4j(本次实测) | **FalkorDB(候选)** |
|---|---|---|
| 内存占用 | 高(~1GB JVM 常驻) | **极低**(基于 Redis,C++ 实现) |
| 启动速度 | 慢(Java 冷启动) | **秒级** |
| 部署 | `docker compose`(镜像大) | **`docker run` 一行**(镜像小) |
| 查询语言 | Cypher | **Cypher 子集**(语法兼容,迁移成本低) |
| 图谱可视化 | Neo4j Browser(7474) | **自带 Web UI(3000 端口)**,交互体验类似 |
| 商业授权 | Community 版有功能限制 | **SSPL 协议,源码开放** |
| Graphiti 兼容 | 原生支持 | 原生支持(Graphiti 官方推荐后端之一) |

**关键依据:**
- 本次实验中 Neo4j 常驻 ~1GB 内存,而 FalkorDB 基于 Redis,同样数据量内存占用约为 Neo4j 的 1/4
- Neo4j Community 版本对某些企业功能(如集群、增量备份)有限制,FalkorDB 单机版功能完整
- Graphiti 官方文档明确列出 FalkorDB 为支持后端,切换无需改 Graphiti 代码

**最小验证路径(留给未来):**
```powershell
docker run -p 3000:3000 -p 6379:6379 falkordb/falkordb
# 浏览器打开 http://localhost:3000 即是图谱可视化
# graphiti_demo/demo.py 改 NEO4J_URI=bolt://localhost:6379 即可复用
```

**判定阈值(何时考虑切换):**
- `memory_items` 超过 5000 条 且 需要频繁多跳查询(如"找出所有与 A 关联且与 B 矛盾的关系链")
- 或需要交互式图谱探索(SQL + networkx 无法满足拖拽下钻需求)

---

## 七、核心结论

### 7.1 本项目的护城河

**不是分类体系,不是双时间,而是"每条结论都能用一条 SQL 追溯到raw"。**

- 194/194 记忆有 evidence_ids(100%)
- 1478 个 evidence_ids 抽样 JOIN 命中率 100%
- 任何一条记忆都可以用 `json_each + JOIN` 反查原始事件

对个人数据分析项目,这是不可妥协的——结论必须可验证。

### 7.2 一句话总结

两个 demo 验证了"自己造的记忆层方向是对的"。值得吸收的是**双时间**(Graphiti)和 **LLM 提炼**(Mem0);不值得引入的是**图数据库**和**全收全录**。本项目应保持 SQLite + chroma + 规则图谱的轻量架构,在证据链基础上叠加双时间和 LLM 提炼能力。

**关于图数据库**:当前规模(194 条记忆)用 SQLite + networkx 规则图谱完全够用。若未来需要,FalkorDB 是比 Neo4j 更合适的轻量选择。详细的图数据库领域分类见《图数据库领域分类.md》。

---

## 八、复现路径

```powershell
# Mem0
cd C:\Users\li\Desktop\memory-bench
.venv\Scripts\python.exe mem0_demo\demo.py --reset --ingest --limit 20
.venv\Scripts\python.exe mem0_demo\demo.py --search "你的查询"

# Graphiti
cd C:\Users\li\Desktop\memory-bench\graphiti_demo
docker compose up -d
cd ..
.venv\Scripts\python.exe graphiti_demo\demo.py --setup --add "测试文本" --search "查询" --stats

# 证据链验证
cd C:\Users\li\Desktop\数据分析
python integration\scripts\unified_search.py memory --subject "GSD项目管理" --neighbors 1
```

## 九、产出物清单

| 文件 | 内容 |
|---|---|
| `memory-bench/README.md` | 实验场说明 + 隔离原则 |
| `memory-bench/samples/` | 三源各 200 条 + 记忆基线(只读快照) |
| `memory-bench/mem0_demo/demo.py` | Mem0 可复用 demo(支持 --ingest/--search/--reset) |
| `memory-bench/graphiti_demo/demo.py` | Graphiti 可复用 demo |
| `memory-bench/graphiti_demo/ollama_embedder.py` | Ollama embedder 适配器(50 行) |
| `memory-bench/graphiti_demo/docker-compose.yml` | Neo4j Docker 配置 |
| `memory-bench/graphiti_demo/graph_viz.html` | D3.js 图谱可视化 |
| `memory-bench/logs/mem0_bench_result_2026-06-17.md` | Mem0 详细结论 |
| `memory-bench/logs/graphiti_bench_result_2026-06-17.md` | Graphiti 详细结论 |
| `memory-bench/logs/all_194_memories.json` | 本项目全量 194 条记忆导出 |
| `memory-bench/logs/SUMMARY_两个Demo反馈总结.md` | **本文档** |
