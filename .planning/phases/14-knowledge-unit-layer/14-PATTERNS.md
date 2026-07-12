# Phase 14 Pattern Map

本文件面向 Phase 14 planner，记录现有代码中应复用的路径、符号、契约和测试惯例。它描述的是当前项目事实，不代表当前实现已经满足生产要求。

## 1. 目录与命名约定

- 生产脚本放在 `integration/scripts/`，使用小写下划线文件名；脚本顶部以模块 docstring 写阶段、职责、流程和 CLI 示例。
- 提示词按版本分目录放在 `integration/prompts/<purpose>/v1_main.md` 与 `v1_schema.md`。canonical merge 应沿用为 `integration/prompts/knowledge_unit_merger/v1_main.md` 和 `v1_schema.md`。
- 自动化测试放在 `tests/test_<capability>.py`。Phase 14 现有测试使用 `test_knowledge_unit_*`、`test_knowledge_index_promotion.py` 命名。
- 分析产物放在 `integration/analysis/ai_context/`。JSON 使用 UTF-8、`ensure_ascii=False`、缩进格式；Markdown 与 JSON 成对输出是现有评估/preview 脚本的常见做法。
- 项目脚本通过 `Path(__file__).resolve().parent` 把 `integration/scripts` 加入 `sys.path`，再复用 `core.project_paths.UNIFIED_DB`、`AGENT_CONVERSATIONS_DB`，不要在新脚本重复硬编码数据库路径。

## 2. SQLite migration 模式

### 直接复用

- 文件：`integration/scripts/migrate_add_knowledge_unit_tables.py`
- 关键符号：`SCHEMA_SQL`、`inspect(db_path)`、`migrate(db_path, write=False)`、`main(argv=None)`。
- `SCHEMA_SQL` 使用 `CREATE TABLE IF NOT EXISTS`、`CREATE INDEX IF NOT EXISTS`、`CHECK`、`UNIQUE` 和 FK，统一通过 `executescript` 执行。
- inspect 使用 SQLite URI `file:<path>?mode=ro`，避免诊断动作产生写入。
- CLI 用互斥的 `--inspect` / `--write`；默认行为是 inspect/dry-run，只有显式 `--write` 才执行迁移。
- 返回结构化 dict，CLI 用 JSON 输出；错误结果返回非零退出码。

### 新 migration 的建议

- backfill ledger/cache/gate 字段优先通过幂等新增表实现；若必须 `ALTER TABLE`，先用 `PRAGMA table_info` 检查列是否存在，不能假设数据库只迁移一次。
- `migrate_add_rag_feedback_tables.py`、`migrate_memory_lifecycle.py` 应保持同一 `inspect/migrate/main` 接口和默认只读语义。
- schema 扩展后更新 `tests/test_knowledge_unit_contracts.py` 的临时库建表、幂等、CHECK/UNIQUE/FK 与“不触碰 memory_items”断言。

### 反模式

- 不要在普通导入或默认 CLI 路径执行迁移。
- 不要使用位置依赖的 `INSERT ... VALUES (...)` 写扩展后的表；当前旧代码大量依赖固定列数，扩展 schema 后应改为显式列名，避免迁移新增列破坏调用方。
- 不要修改或删除旧 production rows 来模拟幂等迁移。

## 3. Manifest、staging、checkpoint 模式

### 直接复用

- 文件：`integration/scripts/knowledge_unit_pipeline.py`
- `RunManifest.create(...)` 对 `input_data`、配置做稳定 SHA-256 派生，记录 source build、prompt/schema/model/embedding/config/git SHA。
- `StagingPublisher.begin_staging()` 建 manifest 并只清理相同 `run_id` 的旧 staging 数据。
- `promote(dataset_hash, stats)`、`abort(reason)`、`checkpoint_rollback(to_run_id)`、`table_reconciliation()` 是已有生命周期入口。
- `tests/test_knowledge_unit_checkpoint.py` 已建立临时 SQLite、稳定 run ID、staging/promote/abort/rollback/reconcile 的测试样式。

### Phase 14 后续应扩展的边界

- backfill item ledger、LLM response cache、失败分类和 gate 决策应与 `run_id` 关联；item key 应由 source identity + message/content hash + prompt/schema/model/config 派生，确保恢复不会重复计费或混用不同模型结果。
- inventory 必须形成稳定 source identity：DB checksum/schema/count/time range/eligible contract，并写入 manifest，而不是只记录 count 和首条 hash。
- extraction、canonical merge、index build 应各有独立 manifest；不要把三个阶段压成一个不可定位的 run。
- `StagingPublisher` 当前只完整处理 `knowledge_units`，canonical rows、index pointer、feedback/lifecycle 需要独立 publisher 或显式扩展后的联合事务。

### 当前实现陷阱（planner 必须安排修复）

- `begin_staging()` 会删除同一 run 的旧单元，不适合直接承担逐 item 断点恢复；恢复数据要先落 ledger/cache，再按完成项重建或续写。
- `promote()` 把旧 `current` unit 改成 `status='staging'` 并令 `supersedes_id=unit_id`，语义混合；后续应区分发布状态和业务 lifecycle。
- `checkpoint_rollback()` 未验证目标 run 存在/完整，也未恢复 canonical、Chroma collection 和 active pointer；不能把它当作联合回滚完成态。
- production SQLite writer、canonical publisher、index publisher 必须串行；只读评估和纯测试可以并行。

## 4. 抽取器、模型与 CLI 模式

### 当前可复用符号

- 文件：`integration/scripts/build_knowledge_units.py`
- Pydantic 合同：`KnowledgeUnit`、`ExtractionResult`，使用 `ConfigDict(extra="forbid")`、枚举 validator、字段长度与 confidence 范围。
- 输入清洗：`SYSTEM_INJECTION_PATTERNS`、`strip_system_injections()`、`is_meaningful()`。
- source 读取：`load_evidence(canonical_db, limit)` 使用只读 SQLite、只取 eligible user role、清洗后 content hash 去重。
- 输出解析：`_clean_json()` 处理 fenced JSON 和首个完整 JSON object。
- CLI：`main(argv=None)` + `argparse`；`--dry-run` 与 `--write` 互斥，未指定时默认 dry-run，`run(...)` 返回进程退出码。

### planner 应保留的接口风格

- 新增 `--model`、`--batch-size`、`--run-id`/`--resume`、`--inventory`、`--report` 等参数时继续允许 `main(argv)` 在单测中直接调用。
- 模型、prompt version、schema version、retry policy、timeout 和 batch size 必须进入 manifest/config hash；不能只打印在 stdout。
- LLM 适配层应返回结构化 result（text、usage、error class、attempts、retry-after），使重试、cache 和 gate 可单测；实际生产模型必须由配置/CLI 注入并写 manifest。
- 报告只写 counts、rates、stable hashes、run IDs 和错误分类；禁止写原始会话、完整 prompt payload、token 或 evidence_quote。

### 当前实现陷阱

- `GCP_PROJECT`、SDK 路径、`VERTEX_MODEL=gemini-3.5-flash` 被硬编码，与 AI-SPEC 的 Luna 模型要求冲突。
- `call_llm()` 每次调用都刷新 token，固定最多三次重试和固定 sleep；没有 jitter、`Retry-After`、可重试/永久错误分类或跨 item token/cache 复用。
- gate 仅检查 schema invalid rate 与 unsupported evidence，未把 API errors、零产出、最低 yield、privacy/secret 命中计入失败条件；全 API 失败仍可能通过。
- 当前每条 evidence 后 `commit()` 与 `sleep(1)`，但没有 item ledger，进程中断后无法准确续跑。
- prompt 文档要求 schema 失败最多重试一次，而代码直接计失败；实现、prompt 和评估合同需要统一。

## 5. Canonicalization 模式

- schema 已存在于 `canonical_knowledge_units` 与 `canonical_unit_members`；canonical unit 使用独立 `run_id`，成员表以 `UNIQUE(canonical_unit_id, member_unit_id)` 保证链接幂等。
- merge prompt 应沿用 extractor 的双文件版本结构和严格 JSON/Pydantic 校验。
- stable canonical ID 应基于规范化 subject/type/claim 与版本化规则派生；不要基于数据库自增 ID 或执行顺序。
- hard negatives（冲突、deprecated、secret/ineligible、近似但不同 subject）必须先进入 deterministic gate，再允许 candidate index build。
- canonical publish 必须 staging-first；失败 merge 不得覆盖已有 `status='current'` canonical rows。
- `integration/scripts/build_knowledge_unit_vector_store.py` 后续应只读取 `canonical_knowledge_units WHERE status='current' AND lifecycle='current'`，并通过 members/evidence 保留可追溯性。

## 6. Vector index、A/B、promotion 与 rollback 模式

### 现有模式

- `integration/scripts/build_knowledge_unit_vector_store.py`
  - `VectorStoreStats` 汇总 build/collection/count/missing/orphan/duplicate/model/gate。
  - collection 命名采用 `knowledge_units_<build-id>`，candidate build 不直接覆盖 active pointer。
  - `--dry-run`/`--write` 与显式 `--db` 延续项目 CLI 约定。
  - 版本写入 `knowledge_index_versions`，初始状态为 `candidate`。
- `integration/scripts/evaluate_knowledge_unit_rag.py`
  - `EvalMetrics`、`evaluate_raw_baseline()`、`evaluate_candidate()`、`run()`、`_format_report()`。
  - frozen dataset 输出 Recall@5、MRR@5、no-answer false positives、deprecated/secret hit、p95 latency。
- `integration/scripts/promote_knowledge_index.py`
  - `read_active()`、原子 `_write_active()`（临时文件后 replace）、append-only JSONL `_log()`。
  - `promote()`、`rollback_to_previous()`、`list_versions()` 共享 `knowledge_index_versions` 与 active pointer。
- `tests/test_knowledge_index_promotion.py` 通过 monkeypatch 模块级 `ACTIVE_POINTER`/`PROMOTE_LOG`，使用临时 DB，且 promotion 单测不依赖真实 Chroma。

### planner 必须补强

- actual-ID reconcile 必须从 Chroma collection 读取实际 IDs 后与 eligible canonical IDs 比较；当前代码把 `indexed_ids=set(ids)` 与自身比较，无法发现真实 missing/orphan。
- 构建同名 collection 时不能吞异常后盲删/重建；active collection 永远禁止删除，candidate 重建要有明确 ownership/build ID。
- A/B report 应产生机器可读 gate result，并把 dataset hash、candidate checksum、metrics、gate status 与 index version 绑定。
- `promote(collection)` 必须验证：candidate 存在、collection 实际可读、count/checksum 对齐、frozen gate 已 PASS、未过期、当前 pointer 与 DB 状态一致。
- promote 顺序要么采用可恢复 journal，要么先验证并记录事务意图，再原子切 pointer，最后确认 DB；任一中断都能 reconcile。
- rollback 应联合恢复 DB run/canonical status、index version、active pointer，并在执行后做实际 collection read smoke test；JSONL log 不能作为唯一真相。
- 14-04 只能构建 candidate 和产出 A/B 结果，不自动 promote；真实 promote 是单独 checkpoint。

## 7. Retrieval、REST 与 MCP contract 模式

### 复用链路

`search_vectors.py` 的底层检索 → `unified_search.py` 的纯 Python contract/编排 → `api_server.py` REST → `mcp_server.py` tool schema 和 handler。

- `search_vectors.py`
  - `_query_collection()` 统一 Chroma query，`_normalize_similarity()` 保持 score 口径。
  - 每条结果包含稳定识别和解释字段：ID、score、collection、retrieval_unit、rank_reason；knowledge unit 结果应保留 canonical_unit_id、unit_type、subject、lifecycle、version 和可追溯 evidence refs（默认不泄漏原文）。
- `unified_search.py`
  - 用纯函数承载业务合同；参数先通过 `_bounded_int()` 等 helper 做边界处理。
  - list/detail contract 使用顶层 `{ok,count/total,limit,offset,items,truncated,...}`，SQLite 连接放 `try/finally`，查询参数化。
- `api_server.py`
  - 是标准库 `BaseHTTPRequestHandler`，不是 FastAPI。
  - GET/POST 路由调用 `backend` contract；旧 `/search/semantic` 使用 `_ok(data)` 包装，`/data/*` 使用 `_contract(data)` 保留顶层合同。新增 knowledge contract 应明确选择一种并为兼容性加测试。
- `mcp_server.py`
  - tool 在静态 `TOOLS` 列表中以 JSON Schema 声明；handler 在 `handle_call_tool()` 分支中复用 backend，不重复 SQL。
  - 数据型 contract 用 `_json_contract()` 返回顶层 JSON 文本；日志只写 stderr，避免破坏 stdio 协议。

### Canary/feedback 建议

- canary route/tool 不应绕过 `unified_search.py`；把 routing decision、raw-vs-KU 选择、latency 和 outcome 作为结构化合同字段。
- feedback schema 只保留 query hash、result/canonical IDs、label、timestamp、run/index version、可选分类；默认不存 query 原文、结果全文或 evidence_quote。
- top_k 必须有界，空 query 返回可预测的 400/empty contract；missing active index 要显式降级到 raw 并返回 `route_reason`，不能吞掉故障。
- REST 和 MCP 应针对同一 backend contract 做形状等价测试。

## 8. Memory lifecycle 集成模式

- 现有 memory 候选代码（例如 `integration/scripts/build_memory_promotion_candidates.py`）采用稳定 hash ID、白名单状态、显式 validation、dry-run preview、只有 `--write` 才入库，可作为 lifecycle 同步脚本风格参考。
- `sync_memory_lifecycle.py` 应先生成 reconcile/preview，列出 would-create/update/deprecate/conflict 和 stable IDs，再由显式 `--write` 应用。
- deprecated/superseded/conflict 不能物理删除；知识 canonical 与 memory_items 的映射需有可审计 source/run/version。
- 若上游 canonical 状态不完整或 index pointer 不一致，sync 应 fail closed，不应产生“promotion_ready/approved”一类状态。
- memory lifecycle `--write` 是显式人工 checkpoint，执行后必须重跑 search contract、secret/deprecated gate 与联合 rollback 测试。

## 9. 测试惯例与推荐测试边界

### 现有惯例

- pytest 与 unittest 混用，均允许；新 Phase 14 测试优先与相邻文件保持一致。
- SQLite 测试一律使用 `tmp_path`/`TemporaryDirectory` 建临时 DB；通过 `SCHEMA_SQL` 或测试专用 `executescript` 构造最小 fixture。
- 外部服务通过 monkeypatch/假 client 注入，不让 unit tests 依赖真实 Vertex/Chroma。
- 校验失败使用 `pytest.raises(ValidationError/sqlite3.IntegrityError)`；contract tests 明确断言 keys、bounds、状态白名单和隐私字段缺失。
- REST 集成测试使用随机本地端口、`ThreadingHTTPServer` 或子进程，先轮询 `/health`，结束时 shutdown/terminate 并 join/wait。

### 按目标文件的测试映射

- `tests/test_knowledge_unit_backfill.py`：inventory identity、item ledger 幂等、interrupt→resume、部分失败不 promote、全 API error fail closed、零产出/min-yield gate、报告不含原文。
- `tests/test_knowledge_unit_retry_cache.py`：429/5xx/timeout 重试，4xx fail-fast，Retry-After+jitter，cache key 含 model/prompt/schema/config，resume 不重复调用，usage/attempts 记录。
- `tests/test_knowledge_unit_checkpoint.py`：扩展 canonical/index/pointer 联合 rollback 与不存在/不完整目标拒绝。
- `tests/test_canonical_knowledge_units.py`：stable IDs、member UNIQUE、duplicate merge、conflict/deprecated/secret hard negatives、失败不覆盖 current。
- `tests/test_knowledge_unit_vector_store.py`：fake Chroma 实际 IDs 的 exact reconcile、active collection 防删、candidate metadata/checksum、canonical-only source。
- `tests/test_knowledge_index_promotion.py`：未通过 gate/不存在/checksum 不符拒绝 promote；中断恢复；DB-pointer-collection reconcile；联合 rollback。
- `tests/test_knowledge_search_contracts.py`：纯 backend + REST + MCP 等价形状、active KU 路由、missing index raw fallback、bounded top_k、稳定 trace fields。
- `tests/test_rag_feedback_privacy.py`：schema 和 reports 不含 query/raw content/evidence quote/token/secret；只存 hashes/IDs/labels。
- `tests/test_knowledge_incremental_refresh.py`：新增/修改/删除 source 的最小重算、cache reuse、无变化 no-op、失败保留旧 active。
- `tests/test_memory_lifecycle_sync.py`：preview-first、显式 write、状态映射、冲突 fail closed、幂等、联合 rollback。

### 分层验证命令

- 单任务：`python -m pytest tests/test_<target>.py -q`
- Phase 14 快速回归：`python -m pytest tests/test_knowledge_unit_*.py tests/test_knowledge_index_promotion.py -q`
- REST/MCP contract 改动：加跑 `tests/test_data_access_contracts.py`、`tests/test_apps_sdk_data_contracts.py`、`tests/test_memory_contracts.py`。
- production checkpoint 前必须先用临时 DB/fake Chroma 跑故障注入；不得以真实长运行作为首次验证。

## 10. Planner 任务拆分约束

- 每个 implementation task 应同时列出目标代码、对应测试、只读/写入模式和可执行验证命令。
- 14-02 先冻结 inventory/source identity 和 backfill resume/cache/gates；在 count contract 未确认前不写死 5,485。
- 14-03 交付 300–500 分层 pilot、人工 evidence review checkpoint、canonicalization 和 hard-negative gate。
- 14-04 执行 full extraction、canonical build、actual-ID candidate index 和 frozen A/B；停在“可 promote”状态。
- 14-05 才补强/执行真实 promote、30-query canary 和 feedback privacy gate。
- 14-06 交付 incremental refresh、memory lifecycle preview/write checkpoint、joint reconcile/rollback 和整阶段回归。

