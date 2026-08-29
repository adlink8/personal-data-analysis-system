# MVP 管线转正 + KU 升格 + 检索接入 — 执行方案（MVP_PROMOTION_PLAN）

> **执行状态标注（2026-08-29，转正第一批）**
> - **事三（检索接入）— 大部分完成**：适配器以 `retrieval/semantic_cards.py` 落地（未走
>   `retrieval/mvp_cards.py` 并入 unified_search facade，故改动清单 #1–#3 未做）；#4 MCP 薄暴露
>   完成（1 个工具 `search_semantic_cards`，core 面 55→56；REST `POST /search/cards` 为接线新增，
>   含 session_id 详情模式）；#5 完成变体 `tests/contract/test_semantic_cards_wiring.py`
>   （另有 `tests/unit/test_semantic_cards.py`）；#6 runbook 未做。
> - **事一（管线转正）— 仅步骤 1 部分**：脚本出 tmp 落位 `tools/semantic/mvp_semantic_compress.py`
>   （与 export_ku_staging.py 同居，路径与原方案 `application/mvp/` 不同），已验证 report 模式
>   可从新位置运行；**步骤 2–6（配置化 / 数据归位 / runbook / CLI / 纯函数单测）未做**，
>   tmp 内运行数据（报告/会话清单）保留未迁。
> - **事二（KU 升格）、事四（Chroma 接入）：未动**，含 blocking 成本批准检查点，仍待决策。

**Date:** 2026-08-29
**方法:** 全程只读分析 + sqlite `file:...?mode=ro` 核数；未读任何凭据文件（`var/config/pi-provider.json` 未读取内容）；本文档为唯一写产物。
**根目录:** `D:\ADLINK\数据分析`
**输入校准:** `.planning/codebase/PIPELINE_MAP.md`、`tmp/mvp_semantic_compress.py`、`src/personal_knowledge/core/schema_ddl.py:72-143`（并外延核验了检索层/内核/治理清单的接线代码）。

---

## 0. 现状基线（全部只读实测，2026-08-29）

### 0.1 数据

| 对象 | 实测 |
|---|---|
| `var/db/semantic_mvp_v3.sqlite` | `session_cards` 173；`ku_facts` 1,037（active 1,009 / superseded 28）；`chunk_summaries` 216 |
| `ku_facts.confidence` | high 986 / medium 51（无 low） |
| `ku_facts.evidence_refs` | 1,037/1,037 非空（M2 校验后入库），格式 `["v2\|cm\|<hex>",...]`，可回溯 canonical_messages |
| `ku_facts.supersedes` | 28 条非空（M1 修复后 supersede 已实际生效） |
| 正式知识三表（personal_system.sqlite） | `knowledge_units` / `knowledge_unit_evidence` / `canonical_knowledge_units` / `canonical_unit_members` 全部 **0 行** |
| `knowledge_index_versions` | 1 行：`kiv_kg_20260812T025401Z_live` → collection `knowledge_units_empty_...`，`unit_count=0, status='active'` |
| `knowledge_build_runs` | 3 行（1 条 index/current 空索引构建 + 2 条 incremental/pending，属 D-30 封存队列台账） |
| 活跃指针 | `var/db/knowledge_index_active.txt` = `knowledge_units_empty_kg_20260812T025401Z_live` |
| MVP v3 试点指标 | full_recall 0.0609（v1 为 0.0329）、visible_rate 0.63、173 卡成本 ¥1.75（用户在 173/1,267 张卡处叫停，¥8 成本护栏未触发） |

### 0.2 代码与机制（本方案要接的既有接口）

- **MVP 管线**：`tmp/mvp_semantic_compress.py`（704 行，pilot/retry/scale/report 四模式），经 `core/llm.make_llm_client(purpose="conversation_summary")` → pi 内核 → hy3；参数全部硬编码（窗口/价格/路径），成本护栏 `PK_MVP_COST_CAP`（默认 ¥8）。
- **KU 权威层合同**（schema_ddl.py:72-143）：`knowledge_units`（unit_type 9 类枚举 / subject+question+answer NOT NULL / evidence_quote NOT NULL / lifecycle 5 枚举 / status(staging,current,rejected) / supersedes_id / version / run_id FK）、`knowledge_unit_evidence`（unit_id+evidence_ref=canonical_message_id，UNIQUE）、`canonical_knowledge_units`（`cu|sha256(lower(subject)|type|sha256(answer)[:16])`）、`knowledge_index_versions`（candidate→active→rolled_back）。
- **既有可直接复用的 builder**：`application/knowledge/build_canonical_knowledge_units.py`（分桶+0.85 embedding 相似合并+min(confidence)+conflict→review，`--run <run_id> --dry-run/--write`）；`application/knowledge/promote_units.py`（staging→current，human-invoked）；`application/knowledge/build_knowledge_unit_vector_store.py`（canonical current 单元 → 版本化 Chroma collection，exact reconcile 门，写 candidate 版本行）；`application/knowledge/promote_knowledge_index.py` + `rollback_knowledge_checkpoint.py`（原子指针 + jsonl 审计）。
- **检索层**：`retrieval/unified_search.py` 是纯 facade（逻辑在 semantic_search/events_query/memory 等 7 个子模块，路径真相源 `retrieval/_constants.py`）；`retrieval/layers/knowledge_unit.py` 查 active collection（`_KU_SLOTS=1`，lifecycle=current 才返回）；本地 embedding `core/local_embed.py` = bge-small-zh-v1.5（512 维，GPU，纯本地，`runtime_config.embedding_model_path()` 定位模型目录）。
- **服务面**：`pk rag-mcp` → `services/mcp_server.py`（stdio，`mcp_tools/tool_definitions.py` 现有 **55 工具**）；pi 内核域网关 = `governance/manifests/capabilities/project-capabilities.json` **45 操作**（checksum 封印，`registry_checksum_drift` fail-closed）+ `services/pi_domain_gateway.py` + `services/pi_read_dispatch.py`。
- **仓库惯例**：无顶层 `scripts/`；管线正身住 `src/personal_knowledge/application/<domain>/`；operator 工具在 `tools/supported/`；一次性/取证在 `tools/{migrations,forensics}/`；运行手册在 `docs/runbooks/*.md`；provider 配置在 `var/config/`；报告在 `var/reports/`。

---

## 总体原则（四件事共同遵守）

1. **证据链不断**：任何 KU 化产物保留 `evidence_ref → canonical_messages` 可回溯；引用解析失败 = 拒绝入库（沿用 MVP M2 语义）。
2. **D-30 / D-31 封存不动**：不触碰 `knowledge_run_items` 24,487 条 pending 队列；不调用 `pk-ku extract`；不启用 `view_candidate_prepare`。本方案唯一 LLM 成本（事二案 A）走 D-31 条款自身预留的路径——"separate explicit user cost approval checkpoint"，设为 blocking 决策检查点。
3. **增量可回滚**：所有写 personal_system.sqlite 的步骤只做 INSERT（四表现全空），按 run_id 整批可删；写前做 sqlite 文件备份；Chroma 侧走既有 candidate→active→rolled_back 状态机，active 指针回滚即回到空索引稳态。
4. **每步有验收**：见各事"步骤"表；所有验收命令均只读或可 dry-run。
5. **MVP 三库对照惯例不变**：v1/v2 永不重写；v3 只增不改。

---

## 事一：MVP 管线转正

### 现状
管线正身住在 `tmp/`（非正式代码区，PIPELINE_MAP §6.1 已标记"迁移转正决策待做"）；模型/价格/窗口参数/DB 路径全部硬编码在脚本常量区；无运行手册；pilot 会话清单和报告散在 `tmp/`。

### 目标
管线成为正式 application 代码（可 import、可测试、可配置），运行手册入库，产出库位置保持不变。

### 步骤（每步含验收）

| # | 步骤 | 验收标准 |
|---|---|---|
| 1 | **落位**：新建 `src/personal_knowledge/application/mvp/`（含 `__init__.py`），`tmp/mvp_semantic_compress.py` 正身迁为 `application/mvp/semantic_compress.py`；去掉 `sys.path.insert(0,"src")` bootstrap 改为正常包内相对导入；`tmp/` 原件与 `tmp/__pycache__` 删除（tmp 本就是临时区；历史报告随迁 `var/reports/mvp/` 归档） | `python -c "from personal_knowledge.application.mvp import semantic_compress"` 成功；`tmp/` 下无 py 正身 |
| 2 | **配置化**：新建 `var/config/mvp_pipeline.json`（字段：`model`、`price_in/out_per_mtok`、`msg_cap=800`、`window_cap=22000`、`chunk_cap=12000`、`max_chunks=24`、`large_msgs=20`、`min_session_chars=200`、`workers=3`、`cost_cap_cny=8`、`norm_prefix_len=40`、`v1/v2/v3_db`、`pilot_sessions_path`、`report_path`、`ref_prefix`）；模块内保 DEFAULT_CONFIG 兜底；env `PK_MVP_COST_CAP` 仍最高优先 | 单测断言：改 JSON 中 `cost_cap_cny` → `run_scale` 启动日志打出新值；删 JSON → 默认值可用 |
| 3 | **数据文件归位**：`tmp/mvp_sessions.json` → `var/config/mvp_pilot_sessions.json`；报告输出路径 → `var/reports/mvp/`；**`var/db/semantic_mvp_v3.sqlite` 位置不变更**（见下方决策） | pilot/report 模式从新路径读清单成功；v3 库 mtime 在纯 report 运行后不变 |
| 4 | **运行手册**：新建 `docs/runbooks/mvp-pipeline.md`（照 `product-sync.md` 体例）：① `ops/` 启动 agent stack（内核 127.0.0.1:8000）② 连通自检（`make_llm_client(purpose="conversation_summary")` 单次 ping）③ `python -m personal_knowledge.application.mvp.semantic_compress scale [limit]`（成本顶 env 说明）④ `report`（注明口径=12 会话 pilot 对照 v1）⑤ 故障段：`provider_response_unavailable` → run_tag 已保证重跑安全；429 → 内核侧退避 | 手册含全部命令原文与预期输出样例；照手册从零走通一遍 scale limit=1 |
| 5 | **CLI 入口**（推荐，一行接线）：`cli.py` 增加 `pk mvp-compress` 子命令，照 `rag-search` 的 `_entry_main` 模式指向模块 `main` | `pk mvp-compress report` 等价于 `python -m` 调用 |
| 6 | **纯函数单测**：`tests/unit/test_mvp_semantic_compress.py` 覆盖 `norm_prefix` / `normalize_refs` / `make_chunks` / `sample_chunk_indices` / `consolidate`（fixture sqlite，**零 LLM 调用**） | `pytest tests/unit/test_mvp_semantic_compress.py` 全绿 |

### 产出库位置决策：**不变更** `var/db/semantic_mvp_v3.sqlite`
理由：v1/v2/v3 三库是"每轮一库、永不重写"的证据对照链（脚本头注释与 PIPELINE_MAP 双重确认）；173 卡的证据引用已 100% 落在 v3；换库 = 断对照。配置化后路径已可变，未来若 schema 需变更（如卡面字段调整，见决策点 1）则开 **v4 新文件**，v3 转对照证据。

### 涉及文件
新增：`src/personal_knowledge/application/mvp/{__init__,semantic_compress}.py`、`var/config/mvp_pipeline.json`、`var/config/mvp_pilot_sessions.json`（移动）、`docs/runbooks/mvp-pipeline.md`、`tests/unit/test_mvp_semantic_compress.py`；修改：`src/personal_knowledge/cli.py`（+1 子命令）；删除：`tmp/mvp_semantic_compress.py`、`tmp/mvp_sessions.json`（内容已迁）。

### 工作量估计
约 0.5–1 人天（1 个执行 plan；纯函数迁移+配置，无新依赖）。上下文成本：轻。

### 风险
- **价格漂移**：脚本现硬编码 ¥1/¥2 per MTok（来自 pi-provider.json 价目），配置化后若 provider 调价而 JSON 未更 → 成本核算失真。缓解：runbook 注明"价格来源=pi-provider.json，调价须同步"，scale 运行日志继续打印实时累计成本。
- **迁移期双入口**：若 tmp 旧脚本未删，操作者可能跑旧版。缓解：删除原件 + runbook 写明唯一入口。
- **内核未启动**：`make_llm_client` 直接 `sys.exit`。缓解：runbook 第②步自检前置。

---

## 事二：KU 升格映射（ku_facts → knowledge_units / canonical）

### 现状
MVP 事实（fact + evidence_refs + supersedes + status + confidence + norm_prefix）与 KU 正式 schema（unit_type/subject/question/answer/evidence_quote/lifecycle/version/supersedes_id）之间无映射；正式四表 0 行；既有 canonical 合并器与向量构建器"等米下锅"。

### 目标
新增一个**升格映射器**，把 1,037 条事实按映射规则落入正式四表（先 staging），复用既有 canonical 化与后续索引链路；全程 dry-run 可审、写后可按 run_id 回滚。

### 字段映射规则

| ku_facts（源） | 目标 | 规则 / 陷阱 |
|---|---|---|
| `fact_key` | `knowledge_units.unit_id` 派生输入 | 不直传（ID 格式合同不同）：`unit_id = "v1\|" + sha256(run_id + "\|" + sha256(fact_key) + "\|" + ordinal)`，满足 `v1|sha256(run_id|bundle_hash|ordinal)` 合同 |
| `fact` | `evidence_quote` + `answer` 原料 | **evidence_quote 用 fact 原文落库（MVP 转正口径，显式声明）**：KU schema 要求 NOT NULL 且语义为"证据引文"，但 MVP fact 是压缩重述而非逐字引文；真实逐字链由 `knowledge_unit_evidence → canonical_messages` 承担，quote 列记载的是"转正时的知识陈述"。替代方案（让 LLM 从被引消息中摘逐字句）成本高且引入二次幻觉面，不推荐 |
| `evidence_refs` JSON 数组 | `knowledge_unit_evidence` × N | 每引用一行，`evidence_type='message'`；UNIQUE(unit_id, evidence_ref) 去重；**任一 ref 在 canonical_messages 查无 → 整条事实拒绝升格并计入拒收清单**（证据链优先） |
| `session_id` | `source_session_id` | 直传（`v2|cs|...`） |
| `evidence_refs[0]` | `source_message_ref` | 取首个引用；该列是向量构建器 user-context 富化（≤2×512 字符、privacy redact）的锚点，必须真实可解析 |
| `confidence` high/medium/low | `0.9 / 0.7 / 0.5` | 定比映射写死在映射器常量；当前库只有 high/medium |
| `status` + `supersedes` | `lifecycle` + `supersedes_id` + `version` | **方向翻转陷阱**：ku_facts 里是**旧行**.supersedes=**新 fact_key**（语义实为 superseded_by）；KU 侧是**新 unit**.supersedes_id=**旧 unit_id**、旧 unit `lifecycle='superseded'`、新 unit version=旧+1。映射器必须按此翻转，dry-run 报告输出翻转对账数（应 = 28 条 superseded 事实对应的链） |
| `norm_prefix` | **不迁移** | 留在 MVP 库继续承担管线内对账；KU 去重走 canonical 层的 `cu|sha256(subject|type|answer_hash)`（见下） |
| —（源无） | `unit_type`（9 类枚举） | 由结构化案产出（案 A：LLM 分类；案 B：prompt 直出）；LLM 不可用/拒答时的确定性 fallback = `personal_fact`，且该行**保持 status='staging' 不自动 current** |
| —（源无） | `evidence_scope` | 从 canonical_messages 按首引用反查 `evidence_scope`，缺省 `'user'` |
| —（源无） | `status='staging'`（全部） | 不直接 current；抽查验收通过后走 `promote_units.py`（human-invoked） |
| —（源无） | `run_id` | 先建 `knowledge_build_runs` 行：`run_type='extraction'`、`status='validated'`、`input_hash = sha256(升格前有序 fact_key 清单)`（幂等合同：同输入同 run 可判重） |

### 两案对比与推荐

| | 案 A：一次轻量 LLM 结构化调用（存量 backfill） | 案 B：管线 prompt 直出三段式（增量） |
|---|---|---|
| 做法 | 新增批处理调用（每批 ~30 条 fact，输入 fact 文本+引用消息 id 清单），输出每条的 `unit_type/subject/question/answer` 严格 JSON；落库前跑确定性校验（枚举合法性、长度界、JSON schema） | 修改 `PROMPT_SMALL / PROMPT_CHUNK / PROMPT_MERGE` 三处 schema，让压缩调用直接为每条 fact 附 `subject/question/answer/unit_type`，零额外调用 |
| 覆盖 | **存量 1,037 条可修**（案 B 管不到存量） | 只覆盖未来增量会话；存量不动 |
| 成本 | ≈35 次调用 × (~1.2k in + ~2k out tok) ≈ **<¥1**（hy3 ¥1/¥2 per MTok）；D-31 要求显式成本批准检查点 | 增量摊入原有压缩调用，≈0 边际成本；重跑全量存量需 ~¥8–14 且无必要 |
| 幻觉面 | 二次结构化可能改写事实语义 → 缓解：校验器要求 `answer` 与原 fact 的 norm_prefix 同前缀（内容不改写，只做分段/分类/提问化） | 无二次面（同一次调用产出） |
| 失败半径 | 批级失败可重试；单条失败 → fallback staging | prompt 变更影响整条管线，需回归 recall 报告 |
| 结论 | **推荐采纳（存量唯一可行路径）** | **推荐采纳（增量升级）** |

**推荐 = 双轨时序**：案 A 一次性回填存量（映射器内置，blocking 成本批准检查点后执行）→ 案 B 作为管线 v3.1 的 prompt 升级合入事一落位后的正式模块（`session_cards.card_json` 的 facts 条目新增字段属加法兼容，无需 v4 库）。两案共用同一份"结构化输出合同"（同一 9 类枚举与字段界），避免两套口径。

### canonical 合并层如何接
**不新写合并代码**——直接调用既有 `build_canonical_knowledge_units.py --run <run_id>`：
1. 它按 `subject / unit_type / evidence_scope / temporal` 分桶、桶内 question+answer embedding 相似 0.85 提案合并、confidence 取成员最小、conflict→review、保留 member links + merge_reason + supersedes/version 血缘；
2. `canonical_unit_id = cu|sha256(lower(subject)|type|sha256(answer)[:16])` 天然幂等——同一 (subject,type,answer) 重跑同 ID，映射器侧只需保证 subject/answer 文本规范化质量（案 A 输出清洗：去尾部句号、全半角统一，规则写进校验器）；
3. MVP 事实间的旧 supersede 链（28 条）在 canonical 层由 lifecycle 保守合并自然承接（"任何非 current 成员都会体现在合并结果上"，builder 源码注释），不要求逐链搬运。

### 步骤（每步含验收）

| # | 步骤 | 验收标准 |
|---|---|---|
| 0 | **checkpoint:decision（blocking）**：用户批准案 A 的 LLM 结构化成本（D-31 预留路径；预估 <¥1）并定案决策点 2/3（norm_prefix 长度、Q-A 三段式） | 用户明确批准记录（写入 plan SUMMARY） |
| 1 | **映射器**：新建 `application/knowledge/promote_mvp_facts.py`（照同目录 builder 惯例：`--dry-run / --write / --rollback <run_id>`；写前自动做 `var/backups/personal_system_pre_ku_promotion_<ts>.sqlite` 备份，294MB，先例 `personal_system_pre_conflict_resolution_20260811`） | dry-run 报告输出：待升格数 / 拒收数（含原因）/ supersede 翻转对账数 / 按类型分布；四表写入数与报告一致 |
| 2 | **案 A 批处理结构化**（批准后）：映射器内置批调用 + 确定性校验器（枚举/长度/norm_prefix 同前缀） | 全部输出通过校验；失败条目走 fallback staging 清单，无静默改写 |
| 3 | **canonical 化**：`python -m .../build_canonical_knowledge_units.py --run <run_id> --dry-run` 审合并提案 → `--write` | dry-run 统计合理（conflict 数列出）；写后 `canonical_unit_members` 行数 = draft 数；重复执行 --write 幂等（同 canonical_unit_id 不重复插入） |
| 4 | **抽查与 current 提升**：随机抽 20 条 current 候选人工核对（subject/answer 与 fact 语义一致、evidence 回溯命中）；`promote_units.py` / `ku.py promote-units` 提升 | 20/20 抽查通过；canonical current 数与提升清单一致；未通过条目保持 staging |
| 5 | **回滚演练**：对新 run_id 执行 `--rollback`，四表行数归零，v3 库未动 | rollback 后 `select count(*)` 四表 = 0；备份文件校验存在 |

### 涉及文件
新增：`src/personal_knowledge/application/knowledge/promote_mvp_facts.py`、`tests/unit/test_promote_mvp_facts.py`；修改：无既有文件（案 B 改 `application/mvp/semantic_compress.py` 内三段 prompt，属事一落位后增量）；数据写：`var/db/personal_system.sqlite` 四表 + `knowledge_build_runs`、备份至 `var/backups/`。

### 工作量估计
约 1–1.5 人天（1–2 个执行 plan：映射器+测试 1 个，案 A 执行+canonical 化+抽查 1 个）；LLM 成本 <¥1。

### 风险
- **evidence_quote 口径**：以 fact 自身落库是"转正口径"而非逐字引文，若未来 KU 消费方假设 quote=逐字，会产生语义偏差。缓解：在映射器模块 docstring 与 runbook 显式声明；`knowledge_unit_evidence` 始终是权威证据链。
- **方向翻转搞反**：supersedes 语义两库相反，是本映射最易错点。缓解：dry-run 强制输出翻转对账数（必须等于 superseded 事实链数），单测覆盖一条完整链。
- **写权威库**：personal_system.sqlite 是 294MB 在役库。缓解：只 INSERT、单事务、写前备份、run_id 整批回滚、永不 UPDATE/DELETE 既有行（四表当前 0 行，冲突面为零）。
- **D-30 邻接**：映射器输入只有 v3 库 ku_facts，代码路径不 import 不查询 `knowledge_run_items`；PR 审查点：diff 中不得出现该表名。

---

## 事三：检索接入（让 173 卡 + 1,037 事实可查）

### 三路线对比

| | (a) 域网关注册新 read 操作 | (b) 扩展 unified_search 加 MVP sqlite 数据源 | (c) stdio rag-mcp 直接加工具 |
|---|---|---|---|
| 改动面 | **双语言四面**：`governance/manifests/capabilities/project-capabilities.json`（45→46 op，**checksum 封印必须重算**，fail-closed）+ `services/pi_domain_gateway.py` OPERATIONS + `services/pi_read_dispatch.py` READ_DISPATCH_OPERATIONS + 内核侧重启；另需过 `pi_domain_gateway` 的 allowed 参数硬约束 | `retrieval/_constants.py` +1 路径、新子模块 `retrieval/mvp_cards.py`、facade re-export +2 CLI 子命令（既有拆分模式原样照抄） | `mcp_tools/tool_definitions.py` +handler；但若检索逻辑写在 handler，就绕过了 retrieval SSOT，形成第二份查询实现 |
| 治理成本 | 高：manifest checksum + 内核进程编排 + Node/Python 双侧测试 | 低：纯 Python、只读、无进程契约 | 低-中：MCP 工具注册有既有模式可抄 |
| 可测试性 | 端到端才能测（需内核在线） | 纯函数级可测（fixture sqlite） | 中 |
| 消费方 | pi 内核侧 AI 会话 | CLI + API + MCP + 未来内核（一处实现多方消费） | 仅 MCP |
| 结论 | 价值真实但**重**；等内核侧有第一个真实消费场景再做，避免为一条只读查询动治理封印 | **推荐（主路径）** | **推荐（薄消费层，叠在 b 上）** |

**推荐：(b) 为主 + (c) 薄暴露**。查询逻辑唯一住在 `retrieval/mvp_cards.py`（SSOT），MCP 工具是它的 20 行包装。路线 (a) 列入后续待办：当内核侧 AI 需要在 Skill 内调用 MVP 检索时，以 `mvp.knowledge_search` 形式注册（复用 `knowledge.search` 的 dispatch 槽位模式），届时一并过 manifest checksum 流程。

### 推荐路线改动清单

| # | 改动 | 文件 |
|---|---|---|
| 1 | 路径真相源加 `MVP_V3_DB` | `retrieval/_constants.py` |
| 2 | 新子模块（约 150 行，全 `mode=ro`）：`search_mvp_facts(query, limit, status='active', session_id=None)`（LIKE 子串命中 `ku_facts.fact`，返回 fact_key/fact/confidence/status/session_id/evidence_refs/回溯提示）；`search_mvp_cards(query, limit)`（命中 `session_cards.purpose/summary_md/card_json`）；`mvp_stats()`（三表计数 + status 分布） | 新 `retrieval/mvp_cards.py` |
| 3 | facade re-export + CLI 子命令 `mvp-facts` / `mvp-cards`（照 `memory`/`cluster` 子命令模式）+ `stats` 输出补 MVP 块 | `retrieval/unified_search.py` |
| 4 | MCP 薄暴露：新增 2 个只读工具 `mvp_search_facts` / `mvp_search_cards`（55→57），照 `list_google_assertions` 的简单只读工具接线模式 | `mcp_tools/tool_definitions.py`、`mcp_tools/handlers/`（新 `mvp.py` 或并入 `data.py`） |
| 5 | 单测：fixture 库覆盖命中/status 过滤/证据引用格式/空库降级 | 新 `tests/unit/test_mvp_cards.py` |
| 6 | runbook 补"检索入口"节 | `docs/runbooks/mvp-pipeline.md` |

**检索技术选型**：用 **LIKE 子串**，不建 FTS。理由：语料 1,037 事实 + 173 卡，全表扫描 <10ms；SQLite FTS5 默认分词器对中文无效，trigram 需要新版本且要建虚表（引入写路径）。中文语义召回由事四的向量槽承担，本路线只做关键词/精确面。

### 步骤与验收

| # | 步骤 | 验收标准 |
|---|---|---|
| 1 | 实现 #1–#3 | `python -m personal_knowledge.retrieval.unified_search mvp-facts "Phase 41 决策"` 命中已知事实，耗时 <1s；`mvp-facts --status superseded` 返回 28 条 |
| 2 | 证据回溯抽查 | 随机 20 条结果的 evidence_refs 逐条在 canonical 库（`mode=ro`）命中 canonical_messages，20/20 |
| 3 | MCP 暴露 #4 | `pk rag-mcp` 会话内调用 `mvp_search_facts` 返回结构化 JSON；工具清单 55→57 |
| 4 | 只读回归 | 全程 `mode=ro` 连接；事三完成后 `var/db/semantic_mvp_v3.sqlite` mtime 不变；`pytest tests/unit/test_mvp_cards.py` 全绿 |

### 涉及文件
见改动清单 #1–#6（4 个修改 + 2 个新建）。

### 工作量估计
约 1 人天（1 个执行 plan）。可与事二并行（无文件交叉；只依赖 v3 库存在）。

### 风险
- **写入门面反模式**：unified_search 是纯 facade，逻辑若写进门面会复活"3,221 行上帝文件"。缓解：改动清单已限定"只 re-export + CLI 壳"。
- **管线写入与检索读并发**：scale 运行写 v3 时 LIKE 读可能短暂锁冲突。缓解：`mode=ro` + sqlite 默认重试；runbook 注明 scale 期间检索可能短暂不可用（低危，写事务粒度为单会话）。
- **MCP 工具数增长**：55→57 是在役工具面。缓解：工具 description 明确标注 MVP 轨道与只读边界；不改既有 55 个。

---

## 事四：Chroma 接入（设计，不实现）

### 现状
`build_knowledge_unit_vector_store.py`（Phase 14 Wave 4.1）与 `knowledge_index_versions(candidate→active→rolled_back)` 状态机代码完备但常年空转：active 指针指向显式空索引（unit_count=0），`KnowledgeUnitLayer._KU_SLOTS=1` 的知识检索槽每次都落在空 collection 上走 fallback。

### 目标（设计态）
事二产出 current canonical 单元后，既有链路零改动（或近零改动）点亮知识检索槽。

### 消费链（全部为既有代码，事四不需要新写）

```
事二产出: canonical_knowledge_units (status='current', lifecycle='current')
          + canonical_unit_members → knowledge_units.source_message_ref
              │
              ▼
build_knowledge_unit_vector_store.py --write
  · load_eligible_units(): 读 UNIFIED_DB canonical current 单元
  · _load_user_contexts(): 按 member 的 source_message_ref 反查 canonical
    同 turn 最近的 eligible user 消息（≤2 片×512 字符，privacy_guard redact）
  · embedding 文本 = 主题 + 用户上下文 + 知识问题 + 知识答案
    document = question + answer（不含证据正文——隐私合同）
  · bge-small-zh-v1.5 (512d) 本地 GPU；exact reconcile 门（missing/orphan/duplicate=0）
  · 写 knowledge_index_versions(candidate) + collection_checksum
              │
              ▼
promote_knowledge_index.py --promote <collection>
  · 原子翻转 var/db/knowledge_index_active.txt + promote_log.jsonl 审计
              │
              ▼
KnowledgeUnitLayer 立即可查（读 active 指针，lifecycle=current 过滤，
annotate_candidate_support 支持度门）；回滚 = rollback_knowledge_checkpoint.py
--to previous（回到空索引稳态，与 2026-08-12 之前状态等价）
```

### 前置条件清单（事四开工门）
1. `knowledge_build_runs` 存在 `status IN ('current','validated')` 的行（事二步骤 1 建）——`_get_current_run_id` 的输入；
2. canonical 存在 current 行且 member `source_message_ref` 可解析（事二步骤 3–4 产出）；
3. Chroma localhost:8001 REST 服务在役（`core/chroma_client.py`，仓内无 chroma.sqlite3，需 ops 侧确认服务存活）；
4. bge 模型目录存在（`runtime_config.embedding_model_path()` / env `PERSONAL_DATA_EMBED_MODEL_PATH`）——builder 的 `verify_model()` 硬门。

### embedding 通道三案

| 案 | 说明 | 代价 | 判定 |
|---|---|---|---|
| **本地小模型（bge-small-zh-v1.5）** | 仓内现成：`core/local_embed.py` 已服务 personal_events / conversation_turns 两个 collection，且 KU builder **代码内已硬编码**该模型与 `verify_model()` 门；纯本地零调用成本、零隐私出域 | 0（模型 95MB 已在本机） | **推荐**。唯一需注意：查询端（`search_vectors` / `layers/knowledge_unit.py` 用 `state.embedding`）与构建端必须同模型同维度——现状已同，选它=不改任何代码 |
| 服务端 embedding API | 经 pi 内核新 purpose（如 `text_embedding`）+ pi-provider.json 增端点 | 新 provider 配置、按 token 计费、双端改造（build + query）、D-31 邻接 | 不推荐：1,000 量级语料 + 512 维本地模型完全够用，服务端方案在本语料规模无收益 |
| 暂缓 | KU 表保持空，检索槽继续 fallback | 0 | 仅当决策点 1/3 推翻事二时成立；否则无理由 |

**混合模型警告**：Chroma 按 collection 隔离 embedding_policy，跨 collection 混模型技术上可行，但查询端必须逐 collection 匹配模型——引入按 collection 选模型的分支。**全仓统一 bge** 是最省事且与现状一致的定案。

### 后续实现步骤（定案后另行 plan，本方案不实现）
1. 前置条件四项核查（脚本化 checklist）→ 2. `build_knowledge_unit_vector_store.py --dry-run` 审 reconcile 报告 → 3. `--write` 建 candidate → 4. `promote_knowledge_index.py --promote`（人工核对 collection checksum）→ 5. 语义检索冒烟（`unified_search.py semantic` 路由应显示 knowledge_unit 命中）→ 6. 回滚演练。

### 工作量估计
设计 0（本节即交付）；实现约 0.5 人天 + 1 个 human-verify 检查点（Chroma 服务与模型目录为本机环境依赖，agent 无法独立保证）。

### 风险
- **reconcile 门失败**：canonical 行与 collection 内容不一致即 gate FAIL。缓解：门本身就是设计好的 fail-closed；dry-run 先行。
- **空索引 active 的"伪稳态"被打破**：promote 是一次真实的知识层状态变迁（PIPELINE_MAP §6.2 观察点 5）。缓解：promote_log.jsonl 既有审计 + rollback 路径先演练再 promote。

---

## 待用户决策点（4 项）

### 决策点 1：卡面 schema 定稿
- **现状**：卡面 7 字段（purpose / conclusions / entities / artifacts / open_questions / facts / summary_md），173 张卡与两份报告已按此产出。
- **选项 A（推荐）**：定稿现 7 字段。理由：已有存量数据、recall 口径、验证报告全部锚定该 schema；目前没有真实消费方提出字段缺口。定稿动作 = schema 写入 runbook + `var/config/mvp_pipeline.json` 注释。
- **选项 B**：调整字段（如 decisions 单列、entities 带类型）。代价：卡面 JSON 结构变更 → 按三库对照惯例开 v4 库重跑，存量 173 卡需兼容读取层。
- **推荐 A**；B 的触发条件留给未来真实消费方（检索层不读卡面细字段，只有 summary_md/purpose/fact 进检索）。

### 决策点 2：norm_prefix 前缀长度 40 → 60
- **现状**：`norm_prefix()` 取归一化后前 40 字符做 supersede 对账键；M1 修复后已实际生效（28 条 superseded）。v2 核验报告曾发现 5 对共享长前缀的近重复；40 字符已能覆盖绝大多数中文事实的"同一事实"判别（40 全角字符 ≈ 完整一句），但理论上存在"前 40 字相同、结论不同"的误并面。
- **选项 A**：保持 40。零改动；对账语义与已发生的 28 条链一致。
- **选项 B（推荐）**：改为 60（配置化后为 `norm_prefix_len` 参数）。更保守 = 误并概率进一步下降；代价：去重灵敏度略降（更多近重复共存）。
- **推荐 B，但带前置审计**：先跑一个只读对比脚本（40 vs 60 两种前缀在 1,037 条上的 supersede 差异清单），确认无误并案例后切 60；配置化使切换零代码成本。若审计显示 40 与 60 的差异为 0，则保持 40 亦可（届时由用户终裁）。

### 决策点 3：Q-A 三段式 vs answer-only
- **现状**：KU schema 设计为 subject + question + answer 三段（`canonical_document`/`embedding_text` 都按 Q+A 双段拼）；MVP fact 是单段陈述。
- **选项 A（推荐）**：三段式。question/answer 由结构化产出（存量=案 A 批调用，增量=案 B prompt 直出）。理由：向量构建器的 embedding 文本与返回 document 都按 Q+A 设计，answer-only 会让"知识问题"段空置，检索对齐质量下降；且 canonical ID 只 hash answer，三段式的 subject/type 才是合并分桶的正交轴。
- **选项 B**：answer-only（question 填占位符）。零 LLM 成本、实现最快，但检索 embedding 少一路对齐信号，且与 Phase 14 既定 KU 语义背离。
- **推荐 A**：成本 <¥1（案 A）+ prompt 增量字段（案 B），收益是 KU 层语义完整。

### 决策点 4：embedding 方案选型
- **选项 A（推荐）**：本地 bge-small-zh-v1.5（512d）。零新依赖、零调用成本、与既有两个 collection 及 KU builder 代码现状完全一致。
- **选项 B**：服务端 embedding API（经 pi 内核新 purpose）。需 provider 配置 + 计费 + 双端改造；在本语料规模（~1,200 条向量）无收益。
- **选项 C**：暂缓 Chroma 接入。仅在事二被否/推迟时成立。
- **推荐 A**；若用户对"模型文件不在仓内、依赖本机目录"有顾虑，备选是把模型路径纳入 `runtime_config` 的既有配置面（已是如此）并在 runbook 写明目录要求。

---

## 执行顺序与依赖

```
事一（管线转正）            事三（检索接入）
   │  配置/落位/CLI            │  只依赖 v3 库
   ▼                          ▼
案 B prompt 升级（增量）      （与事二并行，无文件交叉）
   │
   ▼
事二（KU 升格）──决策点 0 blocking（成本批准 + 决策点 2/3 定案）
   │  四表有数据、canonical current
   ▼
事四（Chroma 接入）──决策点 4 定案 + 前置条件四项核查
```

- Wave 1：事一、事三（并行，文件零交叉）。
- Wave 2：事二（依赖事一的落位与配置；含 blocking 成本批准检查点）。
- Wave 3：事四（依赖事二 canonical current；实现另行 plan）。
- **总工作量**：约 3–4 人天 / 4–5 个执行 plan；新增 LLM 成本 <¥1（全部在事二，受 blocking 检查点保护）。
- **回滚总策略**：事一/事三纯代码可 git revert；事二按 run_id 删增量 + 写前备份；事四回滚 = 指针回退到空索引（既有 `rollback_knowledge_checkpoint.py`）。全程不触碰：v1/v2 对照库、canonical 权威库写路径、D-30 封存队列、`knowledge_index_promote_log.jsonl` 审计史。

---

## 源覆盖审计

| 源项 | 覆盖 |
|---|---|
| 事 1 MVP 管线转正（落位/配置/手册/产出库） | 事一（产出库=不变更，已给论证） |
| 事 2 KU 升格映射（映射规则/两案对比/canonical 接法） | 事二（含方向翻转陷阱与回滚） |
| 事 3 检索接入（三路线对比/推荐/改动清单） | 事三（b 主 + c 薄暴露；a 列后续待办含理由） |
| 事 4 Chroma 接入（消费链/embedding 三案/不实现） | 事四（设计态 + 前置条件 + 后续步骤） |
| 特别要求：待用户决策点单列 | 4 项各含选项与推荐 |
| 原则：证据链 / D-30、D-31 / 增量可回滚 / 每步验收 | 总体原则节 + 各事验收列 + 回滚总策略 |

*Plan: 2026-08-29（只读分析；除本文件外无写操作）*
