# 个人数据分析项目

本项目用于把个人数字足迹整理成可持续追加、可查询、可分析的本地数据系统。

## 顶层目录

```text
数据分析/
├── Google/         GPT/         Agent/         # 三源原始数据(对称结构:原始/结构化/分析)
├── 统合模块/                                    # 核心:整合三源的脚本与产出
│   ├── 脚本/                                   # 全部 Python 脚本(构建/检索/服务层)
│   ├── lib/                                    # 前端依赖(query_graph 可视化用)
│   ├── SQLite数据库/                           # personal_system.sqlite(统合库)
│   ├── 分析数据/                               # 画像、_schema.json、ai_context/
│   └── 结构化数据/  原始输入索引/
├── imports/                                    # 增量导入暂存区
│   ├── incoming/                               # 新导出文件先放这里
│   ├── batches/                                # 每次导入一个批次目录
│   └── duplicate_audit/                        # 重复文件隔离区
├── .planning/                                  # 规划文档(codebase map + 架构图.drawio)
├── .gsd/                                       # GSD 工作流状态
├── README.md
└── requirements.txt
```

每个数据源(Google/GPT/Agent)内部三层:

```text
<模块>/
  原始数据/    # 平台导出、本机工具文件、会话、memory、skills 等未加工数据
  结构化数据/  # 清洗后的 CSV、SQLite、索引表、明细表和脚本
  分析数据/    # 报告、画像、增长图、关注点统计、思考模式推断
```

## 分析目标

每个数据模块生成自己的模块画像：

- 模块贡献了什么类型的数据。
- 数据随时间如何增长。
- 主要关注点是什么。
- 从行为痕迹能推断出哪些思考/工作模式。

统合模块生成个人系统画像：

- Google / GPT / Agent 的数据流向。
- 跨模块统一事件、实体和关系。
- 总体数据增长图。
- 总体关注点。
- 个人思考模式画像。

## 关键产物

- `Google/分析数据/模块画像.md`
- `GPT/分析数据/模块画像.md`
- `Agent/分析数据/模块画像.md`
- `统合模块/分析数据/统合画像.md`
- `统合模块/分析数据/统合画像_数据增长图.png`
- `统合模块/分析数据/统合画像_数据流向.csv`
- `统合模块/分析数据/统合画像_个人思考模式.csv`
- **交互式仪表盘**:`统合模块/脚本/dashboard.py`(见下文"交互式可视化")
- **统一检索 CLI**:`统合模块/脚本/unified_search.py` —— 语义检索 + 精确查询(见下文"统一检索层")
- **MCP Server**:`统合模块/脚本/mcp_server.py` —— 把数据暴露给 AI 客户端(见下文"MCP 接入")
- **REST API**:`统合模块/脚本/api_server.py` —— 零依赖 HTTP 接口(见下文"REST API 接入")
- **接入示例**:`统合模块/脚本/examples/` —— OpenAI 函数调用 / LangChain / RAG 注入(见下文"接入 RAG 平台 / Agent 框架")

## 重跑链路

### 推荐:统一管道入口

```powershell
python 统合模块\脚本\run_pipeline.py               # 全量重跑(步骤 1-12)
python 统合模块\脚本\run_pipeline.py --from 5      # 从步骤 5 恢复(跳过重建库)
python 统合模块\脚本\run_pipeline.py --only 3,4    # 只跑步骤 3 和 4
python 统合模块\脚本\run_pipeline.py --skip 10     # 跳过向量化(省时间)
python 统合模块\脚本\run_pipeline.py --dry-run     # 只打印顺序,不执行
```

任一步失败即中止并打印恢复命令(`--from N`),防止下游跑污染数据。

### 完整步骤(顺序固定,每步幂等)

| # | 脚本 | 作用 |
|---|------|------|
| 1 | `build_integrated_system.py` | 重建统合 SQLite(`personal_system.sqlite`),含 9 张原始表 |
| 2 | `enrich_unified_events.py` | **语义增强层**:追加 3 张增强表(`unified_events_rich`/`event_categories_v2`/`entity_links_v2`),修复三类数据质量问题 |
| 3 | `build_merge_layer.py` | **合并层**(去重折叠):新建 `merge_clusters`/`merge_members` 叠加表(原始数据零损失)。三层分类:L1 真重复→1 条代表,L2 同主题→簇摘要,L3 保留 |
| 4 | `build_deep_profiles.py` | 基于统合库 + 增强表生成模块画像和统合画像。`--use-merged` 生成去重视图 |
| 5 | `build_memory_store.py` | **记忆层**(Phase 04):tooling 工具偏好记忆 |
| 6 | `build_capability_memory.py` | 记忆层:capability 能力使用记忆 |
| 7 | `build_context_memory.py` | 记忆层:fact / project / habit 上下文记忆 |
| 8 | `build_preference_memory.py` | 记忆层:preference 关注偏好记忆(Google 信号) |
| 9 | `build_memory_graph.py` | 记忆图谱:节点 + 5 种跨类关系边 |
| 10 | `build_vector_store.py` | **向量库构建**:把 `content_rich` 经本地 `bge-small-zh-v1.5` 向量化,写入 chroma `personal_events`(支持 `--resume`) |
| 11 | `build_context_doc.py` | 生成 `统合模块/分析数据/ai_context/person_profile.md` |
| 12 | `build_profile_from_memory.py` | 生成记忆图谱版 `统合模块/分析数据/ai_context/person_profile_v2.md` |
| P5 | `evaluate_memory_depth.py` | **Phase 05 准入评估**:抽样检查 memory item / relation 的证据链、时间跨度、复现度、关系强度,输出 `memory_depth_readiness.md` |

> ⚠️ 第 2 步必须紧跟第 1 步:第 1 步会删除并重建整个库文件,增强表会随之丢失,需重跑第 2 步补回。第 3 步(合并层)依赖第 2 步的 `content_rich`;第 4 步依赖增强表,缺它则画像会回退到修复前的污染数据。第 5-9 步(记忆层)依赖前 4 步的统合库与增强表;第 10-12 步依赖前 9 步。
>
> 第 10 步使用本机 `D:\models\bge-small-zh-v1.5`(512维)批量向量化,支持 `--resume` 断点续传。Ollama `bge-m3` 客户端保留为备用实现,不是当前 `personal_events` collection 的构建模型。

## 增量导入

新导出的原始文件先放到 `imports/incoming/`,再用导入脚本解析入库(不直接动 `Google/原始数据/` 等源目录):

```powershell
# 1. 把新导出文件放进对应 incoming 目录
#    imports/incoming/google/<新 takeout>
#    imports/incoming/gpt/<新 chatgpt 导出>

# 2. 跑导入脚本(从项目根目录)
python 统合模块\脚本\run_import_pipeline.py --source google --input imports\incoming\google
python 统合模块\脚本\run_import_pipeline.py --source gpt    --input imports\incoming\gpt
```

每次导入在 `imports/batches/<batch_id>/` 下留批次记录(`raw/` + `extracted/` + `manifest.json`)。重复文件按 sha256 比对后隔离到 `imports/duplicate_audit/quarantine/`,不删除原文件。导入完成后跑重跑链路即可把新数据纳入统合层。

## 语义增强层(阶段1)

`enrich_unified_events.py` 修复三类在静态报告里被掩盖的数据质量缺陷:

**A. 补真实文本(`unified_events_rich`)**
- 问题:Agent session 事件的 `content` 字段存的是 uuid/时间戳(无语义),真实对话在原始 jsonl 里没被接进统合层。
- 修复:联接 `agent_data.sqlite.session_messages`,按 session 聚合真实 user/assistant 对话(过滤 uuid/路径/系统指令噪声),写入 `content_rich`。GPT/Google/skill/memory 的 content 已有真实文本,直接透传。

**B. 纯净分类(`event_categories_v2`)**
- 问题:老分类器把 `service`/`source_table` 元数据拼进分类文本,导致 Agent 模块(其 service=Codex、source_table=sessions)99.9% 自我命中"AI/Agent/模型"。
- 修复:新分类器(`rules.PURE_TOPIC_RULES`)只对 `title + content_rich` 分类,关键词不含工具名/表名。修复后 Agent 从单一类别垄断变成 8 类真实分布。

**C. 真实跨模块连接(`entity_links_v2`)**
- 问题:老 `entity_links` 只有 19 条(类型B是死代码,类型A要求跨模块同名碰撞,而 Agent 的 session/file 实体全是全局唯一 UUID)。
- 修复:用三种真实信号建连 —— 共享域名、共享项目名、时序链路(同年同月内 Google搜索→GPT提问→Agent执行)。修复后生成 7182 条链接,含 33 条完整"搜索→执行"链。

**修复前后对比(统合层关注点分布):**

| | 修复前 | 修复后 |
|---|---|---|
| #1 关注点 | AI/Agent/模型 7327(90%) | 编程/调试/开发 1833(22%) |
| 思考模式 | 工具链驱动 5007(61.5%) | 系统化整理+工具链+其他 三足鼎立 |

## 合并层(去重折叠 · 阶段1.5)

`build_merge_layer.py` 在**不改动原始 9 张表**的前提下,新建 `merge_clusters`/`merge_members`/`merge_build_meta` 3 张叠加表,把相似事件折叠成簇。核心承诺:**合并=折叠,不是删除。任何时刻 JOIN 回去都能拿到每条原始事件的完整内容。**

### 三层分类算法

| 层 | 含义 | 判据 | 处理 |
|---|---|---|---|
| **L1 真重复** | 同一事件被记录多次 | 余弦≥0.97 + 原始 Jaccard≥0.80 + 语义骨架 Jaccard≥0.75 + **内容区分度<0.5** | 折叠为 1 条(保留时间最早的代表) |
| **L2 同主题** | 同一主题的不同操作/提问 | 余弦 0.88~0.97 连通分量 | 聚成簇(留代表+标题摘要) |
| **L3 保留** | 独立事件或结构相似超大簇 | 超大簇保护(size>50)或无相似邻居 | 保持原样 |

**内容区分度**(第 4 道门槛):对 L1 候选簇,把每个成员的"语义骨架"(去数字/路径/UUID)去重,唯一值比例 ≥ 0.5 判为结构相似(如 15 个不同文件名的 umath-*.csv 路径,公共前缀长但文件名各异)→ 降级进 L2;真重复(如 26 条完全相同的"文档产物"文本)骨架唯一值=1 → 确认 L1。

### 产出表

- `merge_clusters`:簇主表(cluster_id / level / representative_id / member_count / summary / mean_similarity)
- `merge_members`:成员明细(cluster_id / event_id / is_representative / role)—— 100% 可追溯
- `merge_build_meta`:构建元数据(输入事件数/压缩率/阈值/耗时)—— 幂等校验用

### 实测效果(7723 条输入)

```
L1 真重复:  521 条 → 118 代表  (省 403)
L2 同主题:  1364 条 → 398 簇   (省 966)
L3 结构保护:3337 条(5 超大簇保持独立)
L3 保留原样:2501 条
净压缩率: 17.7% (7,723 → 6,354)
耗时: ~24s
```

### 下游消费

合并层是**可选增强**,所有脚本向后兼容:
- `unified_search.py`:加 `--dedup` 标志按合并层折叠检索结果;`merge-stats` 子命令查看压缩报告
- `build_deep_profiles.py`:加 `--use-merged` 生成去重视图(产物加 `_去重` 后缀,不覆盖全量版)
- `dashboard.py`:侧栏"原始/去重"视图切换

### 幂等性

重复运行先 `DROP IF EXISTS` 再建,结果一致。

## 交互式可视化

启动本地仪表盘(浏览器自动打开):

```powershell
streamlit run 统合模块\脚本\dashboard.py
```

四个页面:

1. **总览** —— 三源事件总数、按月堆叠增长图(plotly 可悬停/缩放/筛选图例)、分类修复前后对比。
2. **模块下钻** —— 选 Google/GPT/Agent,看该模块关注主题/思考模式/服务分布,按月份和服务下钻到真实事件。
3. **事件明细** —— 全量事件搜索过滤(源/分类/月份/服务/关键词),点开看完整 `content_rich`(真实对话)。这是查看"我具体在做什么"的核心入口。
4. **跨模块链路** —— 展示"搜索→提问→执行"时序链(架构图核心承诺),以及共享项目名/域名的跨模块连接。
5. **向量检索** —— 用自然语言语义搜索历史数据(跨三源),返回按相似度排序的真实事件。首次查询约 20 秒(本地模型加载),后续查询明显更快。

仪表盘从 `personal_system.sqlite` 实时查询,重跑数据后刷新页面即可更新。侧栏显示增强表、向量库、合并层就绪状态,支持原始/去重视图切换。

## 共享脚本模块

**入口与编排:**
- `统合模块/脚本/run_pipeline.py` —— **统一管道入口**:按依赖顺序串联全部 build_* 步骤,支持 `--from`/`--only`/`--skip`/`--dry-run`(见上文"重跑链路")。
- `统合模块/脚本/run_import_pipeline.py` —— **增量导入管道**:把 `imports/incoming/` 下的新导出文件解析入库,生成批次记录并隔离重复文件(见上文"增量导入")。
- `统合模块/脚本/dump_schema.py` —— 打印统合库 schema,产出 `统合模块/分析数据/_schema.json`(表清单 + `unified_events` 列)。

**共享工具:**
- `统合模块/脚本/common.py` —— 纯工具函数(sha256/norm/short/write_csv 等),消除原 build_integrated_system 与 build_deep_profiles 的重复定义。
- `统合模块/脚本/rules.py` —— 统一分类规则:`TOPIC_RULES`/`THINKING_RULES`(老规则,对照基线)+ `PURE_TOPIC_RULES`/`PURE_THINKING_RULES`(纯净规则,剥离元数据污染)。
- `统合模块/脚本/chroma_client.py` —— 轻量 chroma REST 客户端(基于 requests,绕开 chromadb 官方客户端的 httpx 兼容性问题)。
- `统合模块/脚本/local_embed.py` —— 当前生产 embedding 实现:`bge-small-zh-v1.5`,512维。

**记忆层(Phase 04):**
- `统合模块/脚本/build_memory_store.py` —— tooling 工具偏好记忆基础表。
- `统合模块/脚本/build_capability_memory.py` —— capability 能力使用记忆。
- `统合模块/脚本/build_context_memory.py` —— fact / project / habit 上下文记忆。
- `统合模块/脚本/build_preference_memory.py` —— preference 关注偏好记忆。
- `统合模块/脚本/build_memory_graph.py` —— 记忆关系图谱(节点 + 5 种跨类边)。
- `统合模块/脚本/query_graph.py` —— 记忆图谱查询与可视化(命令行遍历 + networkx 成图,依赖 `统合模块/lib/`)。
- `统合模块/脚本/build_profile_from_memory.py` —— 从 `memory_items` + `memory_relations` 生成 `person_profile_v2.md`。
- `统合模块/脚本/mine_deep_memory_graph.py` —— **Phase 06 深挖入口**:只消费 readiness 通过的主题,产出带证据/时间/关系/反例的 `deep_memory_mining.*`。
- `统合模块/脚本/build_deep_memory_profile.py` —— **Phase 06 深层画像**:把深挖 JSON 转成 `deep_memory_insights.*`、`deep_memory_profile.md` 和评估报告。

**记忆层补强(Phase 05):**
- `统合模块/脚本/source_adapters/` —— source adapter contract + Google activities 样例 adapter,为后续输入模块化做准备。
- `统合模块/脚本/memory_governance.py` —— 统一 `evidence_ids` / `confidence` / `last_seen` / `source_hash` / `merge_key` metadata。
- `统合模块/脚本/evaluate_memory_depth.py` —— 深挖准入评估,输出 `统合模块/分析数据/ai_context/memory_depth_readiness.md`。
- `tests/test_memory_contracts.py` —— core / CLI / REST / MCP 四层记忆查询契约测试。

**深层记忆图谱(Phase 06):**
- `统合模块/分析数据/ai_context/deep_memory_mining.json` —— readiness 通过主题的深挖事实层结果。
- `统合模块/分析数据/ai_context/deep_memory_insights.md` —— strong / moderate / weak / unsupported 洞察清单。
- `统合模块/分析数据/ai_context/deep_memory_profile.md` —— 面向 agent prompt 的深层画像。
- `统合模块/分析数据/ai_context/deep_profile_evaluation.md` —— 浅层 `person_profile_v2.md` 与深层 profile 的对比评估。
- Phase 06 **不自动写回** `memory_items`，只产出旁路分析结果，避免把推测污染长期记忆。

**Agent 对话规范化 + mem0 候选压缩(Phase 07):**
- `Agent/结构化数据/脚本/normalize_agent_conversations.py` —— 把 Codex rollout jsonl 拆成 turn/message/tool/event 旁路表(`agent_messages` 等),role 归一化,带 `raw_file + line_no` 证据链,不动旧 `sessions`/`session_messages` 表。
- `统合模块/脚本/build_conversation_segments.py` —— 从清洗后的 Agent/GPT `role=user` 消息切出"用户想法片段",确定性规则切分(列表/换行/长度上限)。
- `统合模块/脚本/build_mem0_candidate_memory.py` —— mem0 候选记忆压缩实验,噪声预过滤 + 证据链强制,**只产候选不写 `memory_items`**;mem0 可选,缺依赖时降级本地启发式。
- `统合模块/分析数据/ai_context/conversation_segments.json` / `mem0_candidate_memories.json` / `mem0_candidate_evaluation.md` —— Phase 07 旁路产物。
- `tests/test_agent_conversation_normalization.py` —— 覆盖 jsonl 解析 / role 过滤 / 证据链回溯 / 候选不污染 memory_items。
- Phase 06 负责深层洞察,Phase 07 负责更可靠的输入和候选压缩;两层都不回写 `memory_items`。

**服务层与接入:**
- `统合模块/脚本/unified_search.py` —— **统一检索层**:把语义检索、精确查询、事件详情、统计、记忆查询合成一组纯函数,CLI / MCP / Agent 共用同一后端,见下文"统一检索层(CLI)"。
- `统合模块/脚本/mcp_server.py` —— **MCP Server**:把统合库、向量库、记忆图谱暴露成 MCP tools,支持 MCP 的 AI 客户端零代码接入,见下文"MCP 接入"。
- `统合模块/脚本/api_server.py` —— **REST API**:纯标准库 `http.server` 实现,把检索与记忆能力暴露成 HTTP 接口,零额外依赖,见下文"REST API 接入"。
- `统合模块/脚本/dashboard.py` —— Streamlit 交互仪表盘,见下文"交互式可视化"。
- `统合模块/脚本/examples/` —— **接入示例**:`openai_function_calling.py` / `langchain_tool.py` / `rag_inject.py`,见下文"接入 RAG 平台 / Agent 框架"。

## 向量库与 AI 上下文(阶段2)

把 8136 条事件的 `content_rich` 向量化,让 AI 能按需语义检索用户历史,并生成可直接注入 system prompt 的长期上下文文档。

### 依赖

- **当前模型**:`D:\models\bge-small-zh-v1.5`(512维,通过 sentence-transformers 本地加载)
- **chromadb**(Docker):本项目用独立 collection `personal_events`,**不触碰**你已有的 `novel_6`/`novel_7` collection
- 不依赖 chromadb Python 客户端包(因 httpx 与本地 chroma 服务有 502 兼容性问题,改用自写的 `chroma_client.py` 直调 REST API)

### 向量库结构

单 collection `personal_events` + 元数据过滤(不分模块多库,保留阶段一跨模块时序链的价值):

```
chroma: personal_events
├─ documents: content_rich(真实文本)
├─ embeddings: bge-small-zh-v1.5 512 维
├─ ids: event_id(与统合库对齐)
└─ metadatas: source / category_v2 / event_time / month / service / event_type / title
```

### 关键产物

- **向量库**:chroma `personal_events`(~7700 条可语义检索事件)
- **`统合模块/分析数据/ai_context/person_profile.md`** —— AI 长期上下文文档,含数据概览/工具偏好/关注主题/思考模式/跨模块协作/检索说明,可注入 AI system prompt
- **`统合模块/脚本/search_vectors.py`** —— 检索脚本,AI 想知道"用户之前怎么处理 X"时调用:
  ```python
  from search_vectors import search
  results = search("PPT 排版怎么做", top_k=5)        # 跨三源检索
  results = search("数据库调试", source="Agent")      # 按源过滤
  ```
  命令行:`python 统合模块\脚本\search_vectors.py "PPT 排版" --source Agent --top-k 5`

### 性能说明

- 当前构建使用本地 sentence-transformers 批量向量化,避免 Ollama 批处理不稳定问题
- `build_vector_store.py` 支持 `--resume` 断点续传,进度存 `vector_build_progress.json`
- 查询时首次约 20 秒(本地 bge-small-zh 模型加载到内存),后续查询明显更快

## 统一检索层(阶段3 · CLI)

`unified_search.py` 是所有程序化接入的公共后端。把"语义检索"、"精确查询"和"记忆查询"合成一组纯函数,**CLI / MCP / 以后的 Agent / RAG 平台都共用这一个文件**,保证四种接入方式行为一致。

两类检索互补:
- **语义检索**(`search_semantic`):自然语言 → 向量库召回,适合"我大概记得做过类似的事"。
- **精确查询**(`query_events`):按源/时间/分类/关键词 AND 过滤 sqlite,适合"列出 2025 年 3 月所有 Agent 事件"。
- **记忆查询**(`get_memory_profile` / `get_memory_by_subject`):读取 `memory_items` + `memory_relations`,适合"我长期偏好什么工具/主题/工作流"。

Phase 05 起,记忆对象 metadata 统一包含:
- `evidence_ids`
- `confidence`
- `last_seen`
- `source_hash`
- `merge_key`

`build_profile_from_memory.py` 和 `unified_search.py memory --subject ...` 会同步展示关键证据摘要,不再只给结论。

- `person_profile_v2.md` 适合做**浅层长期记忆注入**: 工具偏好、项目、习惯、事实清单。
- `deep_memory_profile.md` 适合做**深层模式注入**: 时间演化、主题簇、能力路径、反例约束。

### 命令行用法

```powershell
# 语义检索(模糊召回)
python 统合模块\脚本\unified_search.py semantic "PPT 排版怎么做" --top-k 3
python 统合模块\脚本\unified_search.py semantic "数据库调试" --source Agent

# 语义检索 + 去重(合并层折叠重复命中)
python 统合模块\脚本\unified_search.py semantic "PPT" --top-k 8 --dedup

# 精确查询(结构化过滤,所有参数可选)
python 统合模块\脚本\unified_search.py query --source GPT --month 2025-03
python 统合模块\脚本\unified_search.py query --category 编程 --keyword 报错 --limit 10

# 精确查询 + 去重
python 统合模块\脚本\unified_search.py query --source Agent --dedup --limit 30

# 单条详情(拿到 event_id 后看完整内容)
python 统合模块\脚本\unified_search.py detail <event_id>

# 数据库 + 向量库统计概览
python 统合模块\脚本\unified_search.py stats

# 合并层压缩报告(L1/L2 去重情况)
python 统合模块\脚本\unified_search.py merge-stats

# 长期记忆对象
python 统合模块\脚本\unified_search.py memory
python 统合模块\脚本\unified_search.py memory --type tooling
python 统合模块\脚本\unified_search.py memory --subject Codex
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 2

# 向量库聚类/去重(对检索结果二次加工)
python 统合模块\脚本\unified_search.py cluster --source Agent --threshold 0.92
python 统合模块\脚本\unified_search.py cluster --threshold 0.88 --min-cluster-size 3 --json

# JSON 输出(给其他程序消费)
python 统合模块\脚本\unified_search.py semantic "PPT" --json
python 统合模块\脚本\unified_search.py merge-stats --json
python 统合模块\脚本\unified_search.py cluster --json --limit 500   # 调试用小样本
```

加 `--json` 任何子命令都输出结构化 JSON,便于脚本/管道消费;不加则是人类可读文本。CLI 依赖 Python 标准库 + numpy(`cluster` 用 numpy 算余弦相似度)。

### 管道加工:聚类/去重

`cluster` 子命令把向量库做**二次加工**:拉出全部 embedding,算两两余弦相似度,相似度 ≥ 阈值的连通成簇,每簇只保留一个代表点。本质是把"一堆高度重复的历史"压成"一组去重后的代表事件"。

- **去重场景**(高阈值 0.95+):压掉几乎逐字重复的事件(同一对话被多次记录、重复的系统指令)
- **聚类场景**(低阈值 0.85-0.92):把语义相近的事件归为主题簇(同一问题的多次提问、同类文件)

参数:`--threshold`(相似度阈值,0-1,越大越严格)、`--min-cluster-size`(只保留 size≥N 的簇)、`--source`(按源过滤)、`--limit`(调试限流)、`--members`(人类可读模式展示成员 id)。

```powershell
# 看去重效果(全量,7723 条 → 3786 代表,压缩约 51%)
python 统合模块\脚本\unified_search.py cluster --threshold 0.92

# 管道链:聚类拿代表点 → 喂给 detail 看完整内容
for /f %i in ('python 统合模块\脚本\unified_search.py cluster --threshold 0.92 --json ^
    ^| python -c "import sys,json;[print(c[\"representative_id\"]) for c in json.load(sys.stdin)[\"clusters\"][:5]]"') ^
    do python 统合模块\脚本\unified_search.py detail %i

# 用 jq 提取代表点 id 列表(下游消费)
python 统合模块\脚本\unified_search.py cluster --json ^
  | jq -r ".clusters[].representative_id"
```

> ⚠️ 全量(7700+)在低阈值下会抓到超大簇(如所有 SKILL.md、所有 json 配置归一簇)——这是结构相似而非语义重复。建议去重用 ≥0.95,主题聚类用 0.85-0.92 并关注 `mean_similarity` 高的小簇。

### 模块用法(给上层接入用)

```python
import sys; sys.path.insert(0, "统合模块/脚本")
import unified_search as us

us.search_semantic("PPT 排版怎么做", top_k=5)          # 模糊召回
us.search_semantic("PPT 排版怎么做", top_k=5, dedup=True)  # 去重召回
us.query_events(source="Agent", month="2025-03")        # 结构化过滤
us.query_events(source="Agent", month="2025-03", dedup=True)  # 去重过滤
us.get_event_detail("gpt_xxx")                          # 单条全字段
us.stats()                                              # 概览
us.merge_stats()                                        # 合并层压缩报告
us.get_memory_profile(memory_type="tooling")             # 记忆概览
us.get_memory_by_subject("Codex")                        # 单条记忆 + 关系
us.get_memory_neighbors("Codex", hops=2)                 # 记忆图谱邻居
us.cluster(threshold=0.92)                              # 聚类/去重
```

## MCP 接入(阶段3 · 零代码接 AI 客户端)

`mcp_server.py` 把统合库 + 向量库 + 记忆图谱暴露成 [MCP](https://modelcontextprotocol.io) tools。任何支持 MCP 的 AI 客户端(Claude Desktop / Cursor / ZCode / Continue 等)**配置一行即可检索你的历史数据和长期记忆,无需写集成代码**。

精确查询、详情与统计直接复用 `unified_search` 读取 SQLite；语义检索通过本地 REST API 复用常驻的嵌入模型与 Chroma，结果口径与 CLI 一致，同时避免每个 MCP 客户端重复加载模型。

| Tool | 作用 | 何时用 |
|---|---|---|
| `search_semantic` | 自然语言 → 向量库 → top-K 事件 | "我大概记得做过类似的事" |
| `query_events` | 按源/时间/分类/关键词精确过滤 | "列出 2025-03 的 Agent 事件" |
| `get_event_detail` | 按 event_id 取单条全字段 | 点开看详情 |
| `stats` | 数据库 + 向量库统计概览 | AI 建立全局认知的第一步 |
| `list_categories` | 列出所有 category_v2 分布 | 知道有哪些维度可过滤 |
| `get_memory_profile` | 长期记忆概览 | 先理解你的工具/能力/偏好结构 |
| `get_memory_by_subject` | 单条记忆 + 关系 + 可选邻居 | 点查 Codex / GSD / 项目主题等 |

### 启动与配置

先保持 REST API 启动，供 `search_semantic` 复用常驻模型：

```powershell
python 统合模块\脚本\api_server.py
```

MCP server 本身走 stdio 传输；只有语义检索访问 `127.0.0.1:8000` 本地回环地址：

```powershell
python 统合模块\脚本\mcp_server.py
```

客户端配置(把下面这段加进对应 MCP 配置文件,如 Claude Desktop 的 `claude_desktop_config.json`、Cursor 的 `.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "personal-data": {
      "command": "python",
      "args": ["C:/Users/li/Desktop/数据分析/统合模块/脚本/mcp_server.py"]
    }
  }
}
```

依赖:`pip install mcp`(见 `requirements.txt`)。配好后客户端会自动发现这 7 个 tools,AI 可直接调用检索你的历史和长期记忆。

## REST API 接入(阶段3 · HTTP)

`api_server.py` 用 Python 标准库实现,**零额外依赖**。把统合库 + 向量库暴露成 HTTP 接口,任何能发 HTTP 请求的环境(curl/前端/其他服务/Dify 等 RAG 平台)都能接入。所有接口同样走 `unified_search` 后端,行为与 CLI/MCP 一致。

### 接口

| 方法 | 路径 | 作用 |
|---|---|---|
| GET | `/health` | 健康检查 |
| GET | `/stats` | 数据库 + 向量库统计概览 |
| GET | `/categories?source=` | 分类分布(可选按源过滤) |
| GET | `/memory?type=&limit=` | 长期记忆概览(可选按类型过滤) |
| GET | `/memory/<subject>?neighbors=N` | 单条记忆详情 + 关系 + 可选 N 跳邻居 |
| POST | `/search/semantic` | 语义检索(body: query/top_k/source) |
| POST | `/search/query` | 精确查询(body: source/month/category/keyword/limit) |
| GET | `/event/<id>` | 单条事件全字段 |
| GET | `/profile` | AI 长期上下文文档内容(RAG 注入用) |

统一返回 `{"ok": bool, "data": ..., "error": ...}`。

### Phase 05 验证命令

```powershell
python tests\test_memory_contracts.py
python 统合模块\脚本\source_adapters\google_activities.py --limit 2
python 统合模块\脚本\run_pipeline.py --dry-run
python 统合模块\脚本\run_pipeline.py --only 5,6,7,8,9,11,12
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1
python 统合模块\脚本\evaluate_memory_depth.py
```

### Phase 06 验证命令

```powershell
python 统合模块\脚本\mine_deep_memory_graph.py --dry-run
python 统合模块\脚本\mine_deep_memory_graph.py --output-json
python 统合模块\脚本\build_deep_memory_profile.py
python 统合模块\脚本\build_deep_memory_profile.py --evaluate
```

### Phase 07 验证命令

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --dry-run --limit-files 5
python Agent\结构化数据\脚本\normalize_agent_conversations.py --write
python 统合模块\脚本\build_conversation_segments.py --write
python 统合模块\脚本\build_mem0_candidate_memory.py --sample --force-local
python tests\test_agent_conversation_normalization.py
```

### 启动与示例

```powershell
# 默认 127.0.0.1:8000(仅本地,不对外暴露)
python 统合模块\脚本\api_server.py
# 指定端口
python 统合模块\脚本\api_server.py --port 9000

# 统计概览
curl http://127.0.0.1:8000/stats

# 语义检索
curl -X POST http://127.0.0.1:8000/search/semantic ^
     -H "Content-Type: application/json" ^
     -d "{\"query\": \"PPT 排版\", \"top_k\": 3}"

# 精确查询
curl -X POST http://127.0.0.1:8000/search/query ^
     -H "Content-Type: application/json" ^
     -d "{\"source\": \"Agent\", \"month\": \"2025-03\"}"

# 记忆查询
curl http://127.0.0.1:8000/memory?type=tooling
curl http://127.0.0.1:8000/memory/Codex?neighbors=2
```

> ⚠️ 默认只监听 127.0.0.1。若需对外/跨机访问,自行加反向代理 + 鉴权(API 本身不带鉴权)。

## 接入 RAG 平台 / Agent 框架(阶段3 · 示例)

`统合模块/脚本/examples/` 下有 3 个可运行示例,覆盖三类典型接入。详见 `examples/README.md`。

| 示例 | 接入方式 | 适用 | 依赖 |
|---|---|---|---|
| `openai_function_calling.py` | OpenAI 函数调用 | GPT/DeepSeek/千问 等按需检索历史 | `openai` |
| `langchain_tool.py` | LangChain Tool | 已用 LangChain/LangGraph 的项目 | `langchain` 全家桶 |
| `rag_inject.py` | RAG 上下文注入 | Dify/FastGPT/自建 RAG 静默增强 | 仅标准库(调 HTTP API) |

**选型建议:**
- 想让模型**自己决定何时查数据** → OpenAI 函数调用 / LangChain Tool
- 想**无脑增强每次回答**(任何 LLM 都行)→ RAG 注入
- 在 **Dify/FastGPT/Coze** 等平台 → 用上面的 REST API 配成"自定义 HTTP 工具",无需写 Python

RAG 注入示例同时提供两种增强策略,可叠加:
- **长期画像**(静态):把 `/profile` 的内容塞进 system prompt,让 AI"知道你是谁"
- **相关事件**(动态):用当前问题调 `/search/semantic`,把 top-K 历史塞进 user prompt,让 AI"记得你做过什么"

```powershell
# 先启动 API(另开终端),再跑 RAG 示例
python 统合模块\脚本\api_server.py
python 统合模块\脚本\examples\rag_inject.py "上次怎么调试 Docker 的"
```

## 四种接入方式总览

| 方式 | 文件 | 交互对象 | 何时用 |
|---|---|---|---|
| 交互式仪表盘 | `dashboard.py` | 人(streamlit) | 自己探索、看图、下钻 |
| CLI | `unified_search.py` | 脚本/管道 | 自动化、cron、给别的脚本调 |
| MCP | `mcp_server.py` | AI 客户端(Claude/Cursor 等) | 让支持 MCP 的客户端零代码接入 |
| REST API | `api_server.py` | 任何 HTTP 客户端 | RAG 平台、前端、跨语言、远程 |

四者**共用同一个 `unified_search` 后端**,语义检索 / 精确查询 / 详情 / 统计的行为完全一致,只是面向的调用方不同。`examples/` 里的 OpenAI/LangChain 示例则进一步把后端包成 Agent tool。

## 注意

个人思考画像是基于本地行为数据的推断，用于自我复盘、AI 上下文建设和数据系统优化，不是心理诊断。
