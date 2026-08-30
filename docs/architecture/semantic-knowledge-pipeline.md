<!-- generated-by: gsd-doc-writer -->
# 语义知识层管线：从原始会话到可检索知识

本文描述 `tools/semantic/` 下七个离线脚本组成的知识管线：把 canonical 会话压缩为会话卡与知识事实，经 staging 导出、九类分类、正式层升格与语义收敛沉淀进统合库，再向量化为 Chroma 语义索引并物化 `subject:` 主题 wiki 页。管线总览与规模基线另见 [overview.md](overview.md) 的「语义知识层管线」一节；本文是各阶段的机制细节与运行手册。

设计基调：除 LLM 调用外全部本地确定性执行；canonical 数据只读；所有产物落在 `var/` 下；每一步幂等可重跑。

## 1. 管线总览

```text
canonical 会话库（只读）
    │  mvp_semantic_compress.py（pilot/retry/scale/report，LLM 经 pi 内核 /v1/tasks，hy3）
    ▼
var/db/semantic_mvp_v3.sqlite（session_cards + chunk_summaries + ku_facts）
    │  export_ku_staging.py（stg| 确定性 id，单事务全量重建）
    ▼
var/db/semantic_ku_staging.sqlite ◀── classify_ku_staging.py（九类枚举，只处理 unclassified）
    │  promote_ku_formal.py（run_type='promote'，四表，幂等全量刷新）
    ▼
var/db/personal_system.sqlite（正式层）
    ▲  dedup_canonical_ku.py（canonical 层语义收敛：0.95 合并 + 标识符守卫）
    │  build_semantic_vector_store.py（版本化 collection，registry JSON 登记）
    ▼
Chroma 127.0.0.1:8001 + var/db/semantic_index_registry.json

var/db/personal_system.sqlite + semantic_mvp_v3.sqlite
    │  materialize_wiki.py（subject: 主题键控，wiki_page_body_v1 契约）
    ▼
var/db/personal_wiki_projection.sqlite（wiki 主题页）
```

| 阶段 | 脚本 | 输入（只读） | 输出（可写） | LLM |
|---|---|---|---|---|
| 压缩 | `mvp_semantic_compress.py` | canonical 会话库 | `semantic_mvp_v3.sqlite` | 是（pi 内核 hy3） |
| staging 导出 | `export_ku_staging.py` | `semantic_mvp_v3.sqlite` | `semantic_ku_staging.sqlite` | 否 |
| 九类分类 | `classify_ku_staging.py` | `semantic_ku_staging.sqlite` | 同库原位更新 `unit_type` | 是（pi 内核 hy3） |
| 正式层升格 | `promote_ku_formal.py` | `semantic_ku_staging.sqlite` | `personal_system.sqlite` 四表 | 否 |
| 语义收敛 | `dedup_canonical_ku.py` | `personal_system.sqlite` | 同库 canonical 两表 | 否（本地 embedding） |
| 向量库 | `build_semantic_vector_store.py` | `semantic_mvp_v3.sqlite`（+staging 反查类型） | Chroma collection + `semantic_index_registry.json` | 否（本地 embedding） |
| wiki 物化 | `materialize_wiki.py` | `personal_system.sqlite` + `semantic_mvp_v3.sqlite` | `personal_wiki_projection.sqlite` | 否 |

## 2. 阶段详解

### 2.1 压缩：`mvp_semantic_compress.py`

会话 → 会话卡 + 知识事实。只读打开 canonical 会话库（`file:...?mode=ro`），经 `personal_knowledge.core.canonical_visibility.canonical_projection_predicate` 取可见会话；对消息内容先剥离 `<system-reminder>` 注入块，纯注入消息整条丢弃，再按每消息 800 字符截断。

四种运行模式：

```bash
python tools/semantic/mvp_semantic_compress.py pilot            # 12 会话试点（tmp/mvp_sessions.json）
python tools/semantic/mvp_semantic_compress.py retry <sid...>   # 重试指定失败会话
python tools/semantic/mvp_semantic_compress.py scale [limit]    # 全量压缩未打卡的可见会话
python tools/semantic/mvp_semantic_compress.py report           # 纯只读，v1 vs v3 召回报告
```

`pilot`/`scale`/`retry` 需要 pi 内核在跑且设置了 `PI_KERNEL_INTERNAL_CAPABILITY`（见第 4 节 LLM 链路）；`report` 纯只读，把 v1/v3 两代压缩的可见率与召回率重算进 `tmp/mvp_recall_report_v3.json`。

按会话规模分两条路径：

- **小会话**（≤ 20 条消息）：拼成单窗口（22,000 字符预算），一次 `PROMPT_SMALL` 调用产出完整卡（purpose / conclusions / entities / artifacts / open_questions / facts / summary_md）。
- **大会话**（> 20 条消息）：map-reduce。贪心按 12,000 字符切块；超过 24 块时均匀采样 24 块（保留首尾块）并标记 `truncated_sampling`；每块一次 `PROMPT_CHUNK` 调用（间隔 0.5s）产出块摘要，最后一次 `PROMPT_MERGE` 调用把全部块摘要合并为最终卡。

证据引用 M2 校验：每条 fact 的 `evidence_ids` 必须命中实际送入模型的消息 id 集合。模型偶发丢掉 `v2|cm|` 前缀时自动补前缀修复；既不命中也无法修复的引用直接丢弃——编造的出处进不了库。

事实对账 M1（norm_prefix）：`norm_prefix(fact)` 取小写去标点后的前 40 字符，插入与查重共用同一归一化；同文本 → noop，norm_prefix 相同但文本不同 → 旧行标记 `superseded` 并指向前向替代者。fact_key 形如 `kc|` + 归一化后 80 字符。

写入 `semantic_mvp_v3.sqlite` 三张表：`session_cards`（session_id 主键，含 token 用量与 chunk_count）、`chunk_summaries`（按 run 维度）、`ku_facts`（含 evidence_refs / supersedes / status / norm_prefix）。**绝不写 canonical。**

成本护栏：`scale` 模式用 3 个工作线程并发调 LLM（每线程自开只读 canonical 连接；MVP 库写入全部留在主线程，单写者），按 input ¥1 / output ¥2 每 MTok 累计成本，达到 `PK_MVP_COST_CAP`（环境变量，默认 ¥8）即取消剩余任务（`cap_stopped`）。`scale` 只处理剥离注入后 ≥ 200 字符且尚未打卡的可见会话，已打卡自动跳过。

### 2.2 staging 导出：`export_ku_staging.py`

把 `ku_facts` 映射为正式 `knowledge_units` 的字段形状，写入独立 staging 库。三条硬边界写死在代码里：源库或目标库落在 `data/canonical` 区直接 `sys.exit` 拒绝；不写 `personal_system.sqlite`。

映射规则：

- `unit_id = 'stg|' + sha256(fact_key)` —— 确定性，因此天然幂等；
- `run_id = 'stg_' + 源库文件名主干`（staging 不挂 `knowledge_build_runs`，无 FK）；
- lifecycle：`active → current`、`superseded → superseded`，其他 status 计入 `bad_status_skipped`；
- confidence：high 0.9 / medium 0.7 / low 0.5 / 其余 0.5；
- `unit_type` 的 CHECK 放宽到允许 `'unclassified'`（九类判类留给下一阶段）；question 置空串，answer = fact 原文；evidence_refs（`v2|cm|...`）进伴生表 `knowledge_unit_evidence_staging`。

幂等语义：单事务内 DELETE 全量 + 重新 INSERT，重复运行收敛到同一状态。**重导保留分类**：重建前先读出既有 `unit_id → unit_type` 映射回填，已由分类阶段定型的行不会被重置为 `unclassified`。

退出码即校验：`current == active` 且 `superseded == superseded` 且悬空 supersedes_id 为 0 才返回 0，否则 1。

```bash
python tools/semantic/export_ku_staging.py [--db var/db/semantic_mvp_v3.sqlite] [--out var/db/semantic_ku_staging.sqlite]
```

### 2.3 九类分类：`classify_ku_staging.py`

经同一 pi 内核 LLM 通道（`make_llm_client(purpose="conversation_summary")`）把事实判入九类枚举：`preference`、`habit`、`personal_fact`、`project_decision`、`capability`、`tool_usage`、`solution`、`decision_rationale`、`technical_conclusion`。

幂等：只 SELECT `unit_type='unclassified'` 的行，已分类的行永远不会被重发。默认每批 40 条（`--batch N`），模型返回的类别不在枚举内则丢弃计数（`bad`），对应行保持 `unclassified`，可重跑补判。

```bash
PI_KERNEL_INTERNAL_CAPABILITY=<cap> python tools/semantic/classify_ku_staging.py [--batch 40]
```

### 2.4 正式层升格：`promote_ku_formal.py`

把已分类的 staging 行幂等升格进 `var/db/personal_system.sqlite`（UNIFIED_DB）。写四张表：

1. `knowledge_build_runs`：一条 `run_type='promote'` 行，`run_id = 'pm_' + sha256(内容)[:16]`（内容确定性）；
2. `knowledge_units`：正式 id `v1|` + staging id 的 sha256 段（run 无关，增量刷新身份不变），status='current'，`subject`/`evidence_quote` 由 answer 截断填充，source_agent='mvp'；
3. `knowledge_unit_evidence`：staging 证据引用按新 id 直迁；
4. `knowledge_index_versions`：从 `semantic_index_registry.json` 的 active build 推导一条 `kiv_<build_id>`，status 恒为 **candidate** —— serving 切换（`var/db/knowledge_index_active.txt`）是独立决策，升格不触碰在役索引。

`supersedes_id` 翻译：staging 行的 supersedes 存的是后继 fact_key（`kc|...`），因 staging id 是其确定性哈希，可不经源库直接换算成 `stg|sha256` 再映射为正式 id；映射不到计入 dangling。

幂等语义是**全量刷新**：先把历史上全部 `run_type='promote'` 运行的四表行删净（删除顺序按外键依赖），再整体 upsert——staging 里被移除或改型的行不会在正式层留残。canonical 层（`canonical_knowledge_units` + members）**刻意不碰**：该层由 `dedup_canonical_ku.py` 独占，避免精确分组重建冲掉语义收敛结果。

未分类行留在 staging（正式 CHECK 拒绝 `unclassified` 类型），打印 skipped 计数。

```bash
python tools/semantic/promote_ku_formal.py [--dry-run]
```

### 2.5 语义收敛：`dedup_canonical_ku.py`

canonical KU 层（`canonical_knowledge_units` + `canonical_unit_members`）的唯一写者。从 current KU 两阶段重建：

1. **精确归一化分组**：`(unit_type, 去空白小写 answer)` 相同的 KU 归一组，每组取最长 answer 作代表；
2. **语义合并**：本地 bge-small-zh（`personal_knowledge.core.local_embed`，512 维，无网络无成本）嵌入全部代表，余弦 ≥ `--threshold`（默认 0.95）且 **unit_type 相同**的代表并查集合并，最长 answer 成为 canonical answer。

两道守卫：

- **标识符冲突守卫**：两个代表中任一方含有对方没有的标识符 token（`[A-Za-z_][A-Za-z0-9_\-.\\/]{3+}`，去停用词与纯数字）即视为不同实体，即使相似度过阈值也不合并——例如 `deep-read` 与 `deep-reads` 指向不同仓库的情况；
- **标记区**：0.90 与阈值之间、同类型的相似对只计数上报（review material），不合并。

写入：canonical_unit_id = `cu|` + sha256(`unit_type|归一化代表 answer`) 前 32 字符；`merge_reason` 取 `semantic_0.95_xN` / `exact_norm_dup` / `single`；confidence 取成员最大值。只重写 promote 运行产出的行（先删后插），库里其他来源的行不受影响。脚本内 `os.environ.setdefault("PERSONAL_DATA_EMBED_MODEL_PATH", r"D:\models\bge-small-zh-v1.5")` 兜底模型路径（runtime_config 默认候选指向 C 盘残缺缓存，实测加载必失败）。

```bash
python tools/semantic/dedup_canonical_ku.py [--threshold 0.95] [--dry-run]
```

### 2.6 向量库：`build_semantic_vector_store.py`

把 `semantic_mvp_v3.sqlite` 的产物向量化进 Chroma（默认 `127.0.0.1:8001`，`--host/--port` 可改）。数据面全部只读：

- **active ku_facts** → 文档 `guard_text(fact)`（`personal_knowledge.core.privacy_guard` 隐私防护），id `f|<fact_key>`，metadata 含 `kind:'fact'`、session_id、fact_key、**unit_type**（从 staging 库按 `stg|sha256(fact_key)` 反查；staging 缺失时为 `unclassified`）、confidence、valid_from；
- **全部 session_cards** → 文档 `guard_text(purpose + '\n' + summary_md)`，id `c|<session_id>`，metadata 含 `kind:'card'`、n_messages、created_at。

版本化惯例：collection 命名 `semantic_mvp_v1_<UTC时间戳>`，每次构建产生新版本，**旧版本一律保留、绝不删除**（脚本无任何删除路径）；同名 collection 已存在（时间戳撞车或重复运行）直接报错拒绝而非覆盖。空间为 cosine，单批 HTTP 写入上限 500 条；写入后 `count` 与预期不符则报错保留现场、不写登记。

构建登记写 `var/db/semantic_index_registry.json`：`status ∈ {candidate, active, superseded}`，**active 至多一个**——`--activate` 把本次 build 标 active、其余曾是 active 的降级 superseded（candidate 保持不动，不连带改写历史）。登记文件存在但不可解析时报错退出，绝不静默覆盖。本脚本不写 canonical 的 `knowledge_index_versions`（那是 promote 阶段的事）。

默认 dry-run 防误写；`--dry-run` 与 `--write` 互斥；`--activate` 隐含 `--write`。

```bash
python tools/semantic/build_semantic_vector_store.py --dry-run
python tools/semantic/build_semantic_vector_store.py --write [--activate]
```

### 2.7 wiki 物化：`materialize_wiki.py`

把正式层 current KU 按会话卡实体做主题键控，物化统合 wiki 页。数据流：KU 的 `source_session_id`（`v2|cs|<hex>`）对上 `session_cards` 的会话 → 取该卡 `card_json.entities` 归一化为主题 → KU 绑定到这些主题（一条 KU 可出现在多个页面）。实体归一化：trim → 去路径前缀取主干（按 `/`、`\` 分割取最后一段）→ lowercase；归一化后为空或无法通过 `TopicKey("subject", ...)` 校验（含 `:`、`/`、`\`、控制字符等）的实体丢弃。

`topic_type` 固定 `subject`——这是契约要求而非可选项：`project:{scope}` 等键在 topic 解析里必须有 personal state 断言匹配，否则 `topic_not_found`，物化的页面永远读不到。

噪声阈值与排序：绑定 current KU 数低于 `--min-claims`（默认 5）的主题不建页；`--limit-topics N` 按（claims 降序、主题名升序）取前 N。

页面正文服从 `wiki_page_body_v1` 契约：`{schema, topic, subject, aggregation, claims, evidence_refs, source_fingerprint}`。正文是聚合结果（claims + 证据引用），**永不含原始对话正文，也不含任何时间戳**——同一输入产生同一 `page_checksum`，时间戳只存在于版本/页面行里。claim 为扁平列表、每条自带 `unit_type`；每页至多 200 条 claim、200 条证据引用、每条 claim 至多 8 个证据引用。

写入与幂等：版本行走 `WikiMaterializer.materialize`（`pv_N` 递增 + 依赖登记），页面行走 `derived_store.insert_page`（`(topic_id, projection_version)` 唯一，无重复行）；重跑时与最新存储页 checksum 相同的主题整体跳过，源内容变化才追加新的不可变版本。**唯一可写库是 `var/db/personal_wiki_projection.sqlite`**（可丢弃、再生物）；两个源库只读打开。

```bash
python tools/semantic/materialize_wiki.py --dry-run
python tools/semantic/materialize_wiki.py [--min-claims 5] [--limit-topics N]
```

## 3. LLM 链路与依赖

管线内全部 LLM 调用（压缩、分类）都走同一条链：`make_llm_client(purpose="conversation_summary")` → `PiKernelProvider` → **pi 内核**。

- `make_llm_client`（`src/personal_knowledge/core/llm.py`）：未设 `PI_KERNEL_AI_WORKFLOW=1` 且未设 `PI_KERNEL_INTERNAL_CAPABILITY` 时直接 `sys.exit`（fail-closed）；设置其一即返回 Pi 内核 backed 的 OpenAI 兼容 facade。
- `PiKernelProvider`（`src/personal_knowledge/core/providers.py`）：对 `{PI_KERNEL_URL 默认 http://127.0.0.1:8790}/v1/tasks` 发 POST，头带 `X-PI-Internal-Capability`，body 含 `task_id`、`session_id`、`idempotency_key`（`pi-idem-py-{purpose}-{request_checksum[:40]}`）与 `include_response: true`；base_url 强制 loopback（127.0.0.1 / localhost / ::1），否则 `provider_endpoint_invalid`。每次请求的 checksum 由 purpose、messages、temperature、max_tokens 决定。
- 实际模型为 **hy3**（内核侧读 `var/config/pi-provider.json`，provider=openai-compatible；价格 input ¥1 / output ¥2 每 MTok，与压缩脚本的成本估算一致；该文件含 API key，由内核持有，管线脚本不经手任何密钥）。

本地 embedding 依赖：`personal_knowledge.core.local_embed` 加载本机 **bge-small-zh-v1.5（512 维）**。`dedup_canonical_ku.py` 与 `build_semantic_vector_store.py` 均在 import 前执行 `os.environ.setdefault("PERSONAL_DATA_EMBED_MODEL_PATH", r"D:\models\bge-small-zh-v1.5")` 兜底；调用方已显式设置该环境变量时不覆盖。模型不可用时两脚本都 fail-closed（verify_model 不通过即退出，不产生半成品）。

## 4. 数据边界与安全

- **canonical 只读铁律**：管线内所有打开 canonical 库的连接一律 `mode=ro` URI；`mvp_semantic_compress.py` 的产物只进 `var/db/semantic_mvp_v3.sqlite`；`export_ku_staging.py` 在函数入口显式拒绝源库或目标库落在 `data/canonical` 区（`sys.exit`）。
- **UNIFIED_DB（`personal_system.sqlite`）写者只有 promote 与 dedup**：七个脚本中仅 `promote_ku_formal.py` 与 `dedup_canonical_ku.py` 以可写方式连接它；其余脚本（export、classify、materialize、vector store）对它的访问至多只读。dedup 又只重写 promote 运行产出的行。
- **证据链纪律**：压缩阶段 M2 校验保证每条 fact 的引用指向实际送入模型的消息；升格后证据全部落在 `knowledge_unit_evidence`。截至 2026-08-29 对库实测：14,031 条证据行、10,432 个唯一引用，全部为 `v2|cm|` 格式且**全部解析到 `canonical_messages.canonical_message_id`，零悬空**。
- **密钥脱敏**：API key 只存在于 `var/config/pi-provider.json` 并由内核侧读取；管线脚本代码不含也不经手任何密钥，认证走 `X-PI-Internal-Capability` 头 + loopback 限制；进入向量库与 wiki 页的文本均先过 `guard_text` 隐私防护，wiki 正文永不含原始对话正文。

## 5. 运行手册

### 5.1 前置条件

| 依赖 | 用于 | 说明 |
|---|---|---|
| pi 内核在跑（`http://127.0.0.1:8790`） | 压缩、分类 | `PI_KERNEL_URL` 可覆盖，强制 loopback |
| `PI_KERNEL_INTERNAL_CAPABILITY` 环境变量 | 压缩（pilot/scale/retry）、分类 | 缺失时 `make_llm_client` 直接退出 |
| 本机 embedding 模型 bge-small-zh-v1.5（512 维） | 收敛、向量库 | 路径经 `PERSONAL_DATA_EMBED_MODEL_PATH`，脚本内兜底 `D:\models\bge-small-zh-v1.5` |
| Chroma 在 `127.0.0.1:8001` | 向量库 `--write` | 构建前 heartbeat 预检，不可达即退出 |

report、export、promote、dedup（除模型加载）、materialize 均无需 LLM 与网络。

### 5.2 全量重跑顺序（从仓库根）

```bash
# 1. 压缩（需要内核 + 能力变量；已有卡片的会话自动跳过）
python tools/semantic/mvp_semantic_compress.py scale
# 2. staging 导出（幂等，保留已分类 unit_type）
python tools/semantic/export_ku_staging.py
# 3. 九类分类（只处理 unclassified）
PI_KERNEL_INTERNAL_CAPABILITY=<cap> python tools/semantic/classify_ku_staging.py
# 4. 正式层升格（全量刷新，可先 --dry-run）
python tools/semantic/promote_ku_formal.py
# 5. canonical 层语义收敛（可先 --dry-run）
python tools/semantic/dedup_canonical_ku.py
# 6. 向量库（新时间戳 collection；--activate 切换 active）
python tools/semantic/build_semantic_vector_store.py --write --activate
# 7. wiki 物化（同 checksum 跳过）
python tools/semantic/materialize_wiki.py
```

### 5.3 数字基线（2026-08-29 对库实测）

| 指标 | 数值 | 出处 |
|---|---|---|
| canonical 会话（可见 / 总数） | 1,267 / 2,426 | `agent_conversations.sqlite` + 投影谓词 |
| 已压缩会话卡 | 1,108 | `semantic_mvp_v3.sqlite` `session_cards` |
| ku_facts（active / superseded） | 7,403 / 284 | `semantic_mvp_v3.sqlite` `ku_facts` |
| staging 知识单元 | 7,687 | `semantic_ku_staging.sqlite` `knowledge_units_staging` |
| 正式 current KU（另 superseded 283） | 7,402 | `personal_system.sqlite` `knowledge_units` |
| canonical 知识单元 | 7,059 | `personal_system.sqlite` `canonical_knowledge_units` |
| 证据行（唯一引用） | 14,031（10,432，零悬空） | `personal_system.sqlite` `knowledge_unit_evidence` |
| 向量文档（active build） | 8,510（build `sem_20260829123152`，512 维） | `semantic_index_registry.json` |
| wiki 主题页 | 1,595 | `personal_wiki_projection.sqlite` `wiki_projection_pages` |

current KU 的九类分布（2026-08-29）：personal_fact 2,867、technical_conclusion 1,474、project_decision 1,328、solution 421、capability 384、tool_usage 383、preference 342、habit 148、decision_rationale 55。

正式层当前 promote 运行：`pm_539d5631a59f6ea7`（run_type='promote', status='current'）；两条语义 index 版本（`kiv_sem_20260829110358`、`kiv_sem_20260829123152`）均为 candidate，在役索引指针 `knowledge_index_active.txt` 未被切换。

## 6. 失败模式与恢复

| 失败模式 | 行为 | 恢复 |
|---|---|---|
| 单会话压缩失败 | L4 修复：`db.rollback()`，失败会话的部分 `chunk_summaries` 不会泄漏进下一个会话的提交 | `retry <sid...>` 模式按 session_id 重试，幂等 |
| 成本护栏触发 | `scale` 累计成本（input ¥1 / output ¥2 每 MTok）达到 `PK_MVP_COST_CAP`（默认 ¥8）即取消剩余任务（`cap_stopped=true`），已完成会话已提交 | 直接重跑 `scale`，已打卡会话跳过 |
| 幂等键冲突（`provider_response_unavailable`） | 历史缺陷：内核任务账本持久化幂等键，但响应缓存仅在内存，内核重启后字节级相同的重跑会失败。已由 `pi_kernel_task_responses` 表修复（`002_pi_kernel_task_responses_v1` 迁移，响应载荷有界 1 MB，超限不落库按既有契约失败关闭），`include_response=true` 的重复重放可跨重启幂等返回同一响应 | 管线侧再加一道保险：每次运行的 `run_id`（`v3-<UTC>`）作为 run tag 追加到 prompt 尾部，使幂等键逐次运行新鲜，重跑不再与旧任务撞键 |
| LLM 返回无法解析 / 引用编造 | `parse_json` 剥代码围栏后取首尾大括号，失败抛异常走会话级回滚；M2 校验丢弃无法锚定的 evidence_ids | 重跑该会话；无脏数据入库 |
| staging 重导与分类冲突 | 不存在：重导回填既有 `unit_type`，只重建行内容 | 直接重跑 export |
| 升格中途失败 | 全量刷新在单连接事务内先删后写，`PRAGMA foreign_keys=ON` 保证删除顺序 | 修正后重跑 promote，run_id 由内容决定，收敛到同一状态 |
| dedup 误合并风险 | 标识符冲突守卫阻断 + 0.90~0.95 标记区只上报不合并；`--dry-run` 可先看合并样例 | 调整 `--threshold` 后重跑，canonical 层整体重建 |
| Chroma count 不符 / collection 撞名 | 报错退出：前者不写登记、collection 保留待人工处理；后者拒绝覆盖（脚本无删除路径） | 人工处理后重跑，新时间戳产生新版本 |
| registry 文件损坏 | 存在但不可解析时报错退出，绝不静默覆盖 | 人工修复 JSON 后重跑 |
| wiki 物化失败 | 逐主题 try/except，错误计入 `stats.errors`，退出码 1；已写页面不受影响 | 重跑：同 checksum 跳过，仅补缺失主题 |

重算语义小结：v1/v2 证据库（`semantic_mvp.sqlite` / `semantic_mvp_v2.sqlite`）永不改写，仅 report 模式读作对照；v3 库、staging 库、正式层 promote 数据、canonical 层、wiki 页全部可由上游数据确定性重建，任何一层损坏都可从其直接上游重跑恢复。

## 7. 参考

- 总览与检索面：[overview.md](overview.md)（「语义知识层管线」「语义会话卡检索面」两节）
- 正式层 DDL：`src/personal_knowledge/core/schema_ddl.py`（`knowledge_units` / `knowledge_unit_evidence` / `canonical_knowledge_units` / `canonical_unit_members` / `knowledge_index_versions`）
- LLM 链路：`src/personal_knowledge/core/llm.py`、`src/personal_knowledge/core/providers.py`
- 内核任务响应持久化：`apps/personal_intelligence_kernel/src/tasks/ledger.mjs`
