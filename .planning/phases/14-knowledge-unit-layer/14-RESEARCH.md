# Phase 14 Research — Production Knowledge Unit Backfill

**Phase:** 14 — Knowledge Unit Layer  
**Research mode:** implementation / production hardening  
**Researched:** 2026-07-10  
**Downstream consumer:** `gsd-plan-phase 14`

## Executive Summary

Phase 14 的 PoC 已证明 knowledge-unit retrieval 在现有 frozen test 上优于 raw baseline，但当前实现不能直接安全运行所谓“5,485 条全量抽取”。正式计划必须先把抽取改造成**冻结输入清单、逐项持久化、可恢复、可缓存、失败封闭**的生产回填任务；抽取结果只能进入版本化 staging，不能直接替换当前 active index。

当前权威数据与规划中的 5,485 条存在硬冲突：现有 `build_knowledge_units.load_evidence()` 对当前 canonical DB 实际返回 **2,237** 条，数据库 SQL 粗筛得到 3,248 条 eligible user messages，而 `KU-05` 写的是 5,485 条。Planner 不应把 5,485 硬编码成完成条件；第一项任务应生成可审计 inventory，明确 5,485 的来源和纳入规则。若要把 unified events、conversation bundles 或非 user messages 纳入输入，必须先修改 evidence contract 和 eval，不能静默扩大范围。

推荐顺序：

1. 修正 manifest、snapshot、resume/cache/retry/gate 与 active 隔离。
2. 对 300–500 条分层样本做 pilot，并实际中断/续跑。
3. 在 pilot 产物上先完成 canonicalization 和 hard-negative gate，避免全量完成后才发现 merge 设计错误。
4. 对冻结 inventory 做全量 backfill；随后生成 canonical build，而不是直接把 draft units 设为 active。
5. 从 canonical current units 建新 candidate，跑完整 A/B、联合 rollback，再接 unified retrieval、30-query canary 和 lifecycle。

## Current Facts

### Verified implementation state

| Area | Current evidence | Interpretation |
|---|---|---|
| Phase tests | 5 个现有 Phase 14 test files，`40 passed` | 覆盖 PoC schema/checkpoint/extraction parsing/pointer；不覆盖生产回填、canonicalization、canary、lifecycle |
| Canonical source | 623 sessions、57,765 messages；620 sessions eligible | Phase 13.5 store 可读且 integrity `ok` |
| Extractor input | SQL 粗筛 3,248；现有 `load_evidence()` 清洗去重后 2,237 | 与 KU-05 的 5,485 不一致，必须先 inventory |
| Knowledge DB | 57 draft rows：33 `current`、24 `staging` | 存在旧实验残留；不能作为生产 run 初始状态 |
| Canonical layer | `canonical_knowledge_units=0`，`canonical_unit_members=0` | Wave 3 尚未实现 |
| Index | active=`knowledge_units_a89ebe470357`，33 units | active 由 raw `knowledge_units` 构建，并非 canonical units |
| Run manifests | 2 个 extraction run 都是 `current` | “单一 current extraction checkpoint”不变量未建立 |
| Model contract | 代码硬编码 Vertex `gemini-3.5-flash`；AI-SPEC 锁定 CLI/config 注入的 `gpt-5.6-luna` | 正式计划必须消除模型合同冲突，禁止静默 fallback |
| Wave 5–6 | 无 knowledge search/canary/feedback/refresh/lifecycle 实现文件 | KU-07、KU-08 尚未开始 |

### What the 40 passing tests do not prove

- 没有测试 `--resume`、冻结 inventory、batch checkpoint、response cache 或进程中断恢复。
- 没有测试 terminal API error 会让 gate 失败。
- 没有测试同一 production run 重跑不删除已完成结果。
- 没有 canonicalization 或 hard-negative 测试文件。
- 没有从 Chroma 实际读取 ID 做 exact reconcile；当前实现用输入 IDs 同自己比较。
- 没有证明 promote 的 collection 存在、属于 passed candidate、与 DB checkpoint 匹配。
- 没有联合恢复 canonical DB 状态、active pointer、collection 和 manifest 的 rollback 测试。
- evaluator 没有实现 grounded Top-1、secret/deprecated 实际扫描或 launch gate exit code。

## Standard Stack

沿用现有轻量栈，不引入新的 RAG orchestration framework：

| Concern | Prescriptive choice |
|---|---|
| Durable state / lineage | SQLite，显式事务、FK、UNIQUE、CHECK；单 writer |
| Structured output | Pydantic v2，`extra="forbid"` |
| LLM boundary | 当前项目的 OpenAI-compatible/Vertex HTTP boundary；model 从 CLI/config 注入并写 manifest |
| Retry | 标准库 HTTP + 明确错误分类、exponential backoff、jitter、`Retry-After`；不要新增任务队列 |
| Cache | SQLite 本地 response cache，key=`model + prompt_hash + schema_hash + normalized_input_hash + generation_config_hash` |
| Vector store | 现有 Chroma HTTP client + `local_embed` |
| Evaluation | pytest + 本地 SQLite/JSON evaluator；个人原文不发送到 tracing SaaS |
| CLI | argparse，默认 inspect/dry-run；所有 publish/write 操作显式开关 |

## Architecture Patterns

### 1. Freeze the input before making any LLM call

创建 production run 时一次性计算并持久化 ordered inventory：`evidence_ref`、`content_hash`、session/source/agent/time bucket、eligibility reason、position。`run_id` 必须由**完整 inventory hash**、source checkpoint、prompt/schema/model/config 派生，不能只使用 `evidence_count + first_hash`。

`--offset` 只用于人工查看或首次分片，不承担恢复正确性。恢复必须按持久化 item status 和 evidence identity 进行；否则上游新增会话会让 offset 漂移。

### 2. Durable work-item state machine

为每个 inventory item 持久化状态：

```text
pending → in_flight → succeeded | abstained
                   ↘ retryable → in_flight
                   ↘ terminal_failed
```

至少记录 `attempt_count`、`lease_started_at`、`last_error_class`、`cache_key`、`response_hash`、`unit_count`。启动/恢复时把过期 lease 恢复为 retryable。每个 item 的 validated units、evidence links 和 item terminal status 在同一 SQLite 事务提交。

### 3. Deterministic idempotency

- unit identity 使用 `schema_version|run_id|evidence_ref|ordinal|validated_payload_hash`。
- 同一个 run 的 `--resume` 不得调用当前 `begin_staging()` 删除全部 units。
- 新建 run 与恢复 run 分成两个显式入口，例如 `--start` / `--resume RUN_ID`。
- cache hit 仍必须重新执行当前 Pydantic/evidence/privacy gate，不能盲信旧解析结果。
- 同一冻结 snapshot、prompt、model、config 二次运行的 dataset hash 和 row set 必须一致。

### 4. Bounded concurrency, single writer

LLM worker 可有限并发，但只返回纯响应；主线程负责 validation 和 SQLite commit。`--batch-size` 表示一次调度/commit/report 的上限，不等于丢失失败项。并发度、RPM、最大重试、base/max backoff 均由 config/CLI 注入并写入 manifest。

当前 `call_llm()` 已有 3 次固定重试，因此计划应**加固现有 retry**，不是重复实现“从无到有”：补错误分类、jitter、`Retry-After`、token refresh 和 retry metrics。当前每次请求都会获取 gcloud token，应改为 run-scoped token provider，并在 401/过期时刷新。

### 5. Staging and active must be separate namespaces

生产 extraction run 通过 gate 后最多进入 `validated`/`extracted` checkpoint；不能直接把所有旧 `knowledge_units.current` 降级并把 draft units 设为 current。只有 Wave 3 canonicalization 产生的 `canonical_knowledge_units.status=current` 才是 candidate index 输入。

Candidate collection 必须使用新的 immutable build/checksum 名称。builder 必须拒绝删除或重建 active pointer 指向的 collection。构建到新 collection 后，从 Chroma **实际读取 IDs** 做 missing/orphan/duplicate/checksum reconcile。

### 6. Promotion is a verified checkpoint operation

Promote 前必须验证：

- collection 存在且 count/checksum 与 `knowledge_index_versions` 匹配；
- index version 状态为 candidate；
- 对应 canonical build、extraction run 和 frozen eval report 全部 gate passed；
- active pointer 与 DB 中 active version 一致。

文件指针与 SQLite 无法组成单一原子事务，因此使用 prepare/commit journal：先写 promotion intent，验证 DB 更新，再 `os.replace` pointer，最后写 committed；启动时可恢复未完成 journal。Rollback 必须恢复 canonical current checkpoint、index version、pointer 和 manifest，并再次 exact reconcile。

## Strict Extraction Gate

正式 production gate 应失败封闭，至少包含：

| Gate | Required condition |
|---|---|
| Snapshot completeness | frozen inventory count/hash 与 run manifest 一致；pending/in_flight/retryable=0 |
| API completion | transient retries 可非零，但 `terminal_api_errors=0`；有 terminal error 就不能结束为 passed |
| Nonzero output | `units_total > 0`，防止空 run 被错误发布 |
| Minimum yield | 阈值由 300–500 pilot 的有效产出分布预先固化到 config/manifest；不得在看到全量结果后调低 |
| Schema | valid responses / parseable responses ≥95%；schema invalid 计入失败率 |
| Overall failure | terminal + schema + validation reject rate ≤10%，且 critical reject 必须为 0 |
| Evidence | foreign/missing ref=0；引用必须能在 frozen snapshot 和 canonical DB 回查 |
| Speaker | personal fact/preference/habit 无 user-authored support=0 |
| Privacy | secret/deleted/excluded/ineligible/thinking/tool-raw hits=0 |
| Reproducibility | cache/replay 得到相同 validated dataset hash |

Minimum yield 不应直接照搬 PoC 的 33/20。Pilot 应分层采样并计算可接受的保守下界；目标是捕获“API 全失败但 gate PASS”，而不是奖励模型强行生成。Abstention 是合法结果，必须单独报告。

当前 gate 只检查 `schema_invalid / total < 5%` 与 `units_without_evidence == 0`，没有纳入 `errors`、nonzero output、minimum yield、pending items 或 privacy scan，因此可能在全部 API 调用失败时错误 PASS。

## Full Backfill Risks and Controls

| Risk | Current behavior | Required control |
|---|---|---|
| 中断后重跑 | 同 run `begin_staging()` 删除旧结果 | item ledger + resume + lease recovery |
| 输入漂移 | 每次重新查询，run hash 只含 count/first hash | frozen inventory + full Merkle/dataset hash |
| 重复付费/耗时 | 无 response cache | content-addressed local cache |
| API 限流/短故障 | 固定 3 次重试，无 jitter/Retry-After | classified backoff + resume queue |
| 错误 gate PASS | API errors 不参与 gate | terminal completion + strict gate |
| active 被破坏 | 同名 collection 先删除再构建 | immutable candidate + active collision refusal |
| 原始 draft 绕过 merge | vector builder 读取 `knowledge_units.current` | 只读 passed canonical build |
| 隐私泄漏 | session eligibility + tag stripping，缺少产物 secret scan | pre-call eligibility + post-response privacy scan |
| 运行身份不可追溯 | `source_build_id="canonical-v1"` 硬编码 | Phase 13.5 snapshot/checksum manifest |
| 统计误判 | 5,485 与实际 2,237 冲突 | inventory report 作为 planning checkpoint |

按当前代码每 item 固定 `sleep(1)`，5,485 条仅 sleep 下界约 91.4 分钟，尚不含 token 获取、LLM latency、retry 和 embedding；“约 1.5 小时”只能视为乐观下界。当前真实 2,237 输入对应 sleep 下界约 37.3 分钟。

## Pilot and Backfill Protocol

### Pilot: 300–500 items

不要使用“最新前 N 条”。按 source、agent、time bucket、message length、system-injection presence、历史 sensitive/excluded 邻近场景分层确定性采样，并冻结 sample manifest。

Pilot 必须验证：

1. 正常完成和 response cache replay。
2. 运行中强制终止，恢复后不重复写、不丢 item。
3. 429/500/503/timeout/invalid JSON/foreign evidence ref 的 fake-client 注入。
4. 至少 20 个 units 的人工 evidence-support 审查，支持率 ≥90%。
5. schema ≥95%、speaker/privacy critical error=0。
6. 基于 pilot 固化 production minimum-yield、concurrency、retry 和成本/时延预算。
7. 在 pilot units 上运行 Wave 3 merge-positive/hard-negative gate。

### Full production backfill

- 输入数量取 inventory artifact 的权威 count；若产品范围确认是 5,485，inventory 必须能逐条解释这 5,485 条从哪里来。
- 使用新的 run ID 和 staging tables；保留当前 `knowledge_units_a89ebe470357` active checkpoint。
- 分批建议初始 100 items，有限并发；batch 完成即 commit manifest progress/report。
- Pilot cache 只有在 model/prompt/schema/input/config hash 完全相同时才可复用。
- Full extraction gate 通过后先进入 canonicalization；不得直接 build/promote active index。

## Wave 3 Dependency: Canonicalization First

Canonicalization 实现应在 pilot 后、全量 LLM 回填期间或之前完成验证；**全量 canonical build** 则严格依赖完整 passed extraction run。

Prescriptive flow：

```text
passed extraction snapshot
  → subject + unit_type + speaker eligibility + temporal compatibility buckets
  → embedding proposals (question + answer)
  → LLM/rule merge decision
  → canonical staging + member lineage
  → 20 positives / 20 hard negatives gate
  → canonical current checkpoint
  → immutable candidate collection
```

禁止用“canonical row count 减少”作为成功条件。必须满足 hard-negative false merge=0、positive recall≥80%、跨 subject/role/time incompatible auto-merge=0。Conflict 进入 review，不自动 current。现有 active 33 units 是 raw draft PoC，只能作为 rollback baseline，不能证明 Wave 3 完成。

## Wave 5–6 Architecture

### Wave 5: Retrieval interface and canary

- 在 `unified_search.py` 建唯一 `search_knowledge_units()` backend；CLI、REST、MCP 只做适配，不各自实现检索逻辑。
- 响应返回 route、index/canonical/extraction versions、unit IDs、evidence refs、fallback/abstain reason。
- evidence ref 无法回查、lifecycle 非 current 或 active checkpoint 不一致时，过滤并 raw fallback/abstain。
- 本地 feedback tables 默认仅保存 query hash、returned IDs/scores、route、latency、versions、label；不保存 raw query。
- 30 个真实 query canary：helpful≥80%、critical wrong/stale=0、fallback≤30%、warm p95≤raw baseline 2x；失败自动/显式 rollback 到 raw/default checkpoint。

### Wave 6: Incremental refresh and lifecycle

- Phase 13.5 必须提供稳定 source snapshot/checksum 或 delta watermark；当前 `canonical-v1` 字符串不够。
- delta 先定位 affected evidence refs/subjects，只重建受影响 subjects；定期 full reconcile 兜底。
- deleted/excluded/deprecated 在一次 refresh 内传播到 draft、canonical、Chroma；orphan=0。
- feedback 的 wrong/stale/missing 只能进入 dev/hard-negative backlog，不自动改 frozen test。
- memory lifecycle 首先生成 dry-run link proposal；显式 `--write` 才更新，且只 deprecate 不物理删除。

## Don't Hand-Roll

- 不引入 LangChain、LlamaIndex、LangGraph、Celery 或外部 workflow 服务；SQLite item ledger 足够覆盖单机 2k–5k 级回填。
- 不用 list offset 作为恢复机制；用 frozen IDs/hash + item status。
- 不用 `INSERT OR IGNORE` 掩盖冲突；冲突必须成为 gate/error evidence。
- 不自制模糊“事务”同时假装 SQLite 与文件/Chroma 原子；使用 journal + reconcile。
- 不把 raw response cache 提交 Git，也不把个人原文发送到外部 tracing/eval SaaS。
- 不用同一个 collection name 原地重建 candidate，尤其不能删除 active collection。
- 不用 LLM judge 替代 deterministic schema/evidence/privacy gate。

## Common Pitfalls

1. 把 agent profile 的 Terra/Luna 分工与 production extraction model 混为一谈。GSD planner 模型不等于数据抽取模型；后者必须遵守 AI-SPEC、由 CLI/config 注入并记录实际 ID。
2. 将 `status=current` 同时用于“抽取通过”和“可在线检索”。应区分 extraction validated、canonical current、index active。
3. 先 promote draft 再 canonicalize，会使错误知识进入 retrieval surface。
4. 只检查 Chroma count，无法发现同数量的 wrong/orphan IDs。
5. evaluator 总是 exit 0 或缺少真实 secret/deprecated scan，会制造假绿色 gate。
6. 只对最近 300 条做 pilot，会遗漏旧格式、旧 agent 和长文本长尾。
7. 为追求 minimum yield 压低 abstention，会增加无依据知识；yield 阈值只做灾难检测。
8. 在全量之后才实现 merge，会把 1.5 小时任务变成不可用数据堆积。

## Validation Architecture (Nyquist)

每个实现 task 必须同时交付自动验证；不能把验证全部推迟到 phase 末尾。

### Test layers

| Layer | Purpose | Required evidence |
|---|---|---|
| Unit | hash、state transition、retry classification、gate math | pure tests，无网络 |
| Component | temp SQLite + fake LLM + fake Chroma | resume/cache/idempotency/reconcile |
| Crash recovery | 子进程在确定 checkpoint 被终止后恢复 | row set/hash 与 uninterrupted run 相同 |
| Contract | CLI/REST/MCP 统一字段和 fallback | parameterized contract tests |
| Offline eval | frozen + merge positive/hard negative | machine-readable gate report + nonzero failing exit |
| Pilot | 300–500 真实分层样本 | manifest、aggregate metrics、人工 review record |
| Production | full inventory | count/hash/reconciliation/gate report |
| Canary | 30 真实 queries | privacy-safe feedback + rollback evidence |

### Nyquist task-to-test mapping

| Planned capability | Tests that must ship with it |
|---|---|
| Inventory/snapshot | stable ordering/hash；count drift abort；eligibility/privacy exclusion |
| Resume/batch | interrupted vs uninterrupted dataset hash 相同；expired lease recovery |
| Cache | exact key hit；prompt/model/schema/config change miss；cache replay revalidates |
| Retry | 429/500/503/timeout retry；400/401 classification；Retry-After/jitter bounds |
| Strict gate | all API errors cannot PASS；zero/min-yield fail；critical privacy/evidence fail |
| Staging isolation | failed/new run leaves old current + active pointer/collection byte-for-byte unchanged |
| Canonicalization | 20 positive recall≥80%；20 hard negatives false merge=0；time/role/subject isolation |
| Index build | actual collection IDs exact reconcile；active collision refusal；immutable naming |
| Promote/rollback | nonexistent/unpassed candidate rejected；journal recovery；joint DB/index/pointer rollback |
| Retrieval/canary | knowledge-first + raw fallback；citation failure abstains；feedback stores no raw query |
| Incremental lifecycle | only affected subjects change；deleted/deprecated leaves zero index residue |

Phase verification 还应运行全量回归套件，但 `210 passed` 只能证明无已覆盖回归，不能替代上述缺失测试。

## Files the Planner Should Create or Modify

### Production extraction (KU-05)

- Modify `integration/scripts/build_knowledge_units.py`
- Modify `integration/scripts/knowledge_unit_pipeline.py`
- Modify `integration/scripts/migrate_add_knowledge_unit_tables.py`（新增 run item/cache/gate 状态所需 schema；保持幂等迁移）
- Create `integration/scripts/evaluate_knowledge_unit_extraction.py`
- Create `tests/test_knowledge_unit_backfill.py`
- Create `tests/test_knowledge_unit_retry_cache.py`
- Extend `tests/test_knowledge_unit_checkpoint.py`
- Create privacy-safe inventory/pilot/full reports under `integration/analysis/ai_context/`（聚合值与 hashes，不含原文）

### Canonicalization (KU-06)

- Create `integration/prompts/knowledge_unit_merger/v1_main.md`
- Create `integration/prompts/knowledge_unit_merger/v1_schema.md`
- Create `integration/scripts/build_canonical_knowledge_units.py`
- Create `tests/test_canonical_knowledge_units.py`
- Modify `integration/scripts/build_knowledge_unit_vector_store.py` to consume canonical current units and actual-ID reconcile
- Create `tests/test_knowledge_unit_vector_store.py`

### Promotion hardening

- Modify `integration/scripts/evaluate_knowledge_unit_rag.py`
- Modify `integration/scripts/promote_knowledge_index.py`
- Modify `integration/scripts/rollback_knowledge_checkpoint.py`
- Extend `tests/test_knowledge_index_promotion.py`

### Retrieval/canary (KU-07)

- Modify `integration/scripts/search_vectors.py`
- Modify `integration/scripts/unified_search.py`
- Modify `integration/scripts/api_server.py`
- Modify `integration/scripts/mcp_server.py`
- Create `integration/scripts/migrate_add_rag_feedback_tables.py`
- Create `integration/scripts/evaluate_knowledge_canary.py`
- Create `tests/test_knowledge_search_contracts.py`
- Create `tests/test_rag_feedback_privacy.py`

### Incremental lifecycle (KU-08)

- Create `integration/scripts/refresh_knowledge_units.py`
- Create `integration/scripts/reconcile_knowledge_index.py`
- Create `integration/scripts/migrate_memory_lifecycle.py`
- Create `integration/scripts/sync_memory_lifecycle.py`
- Create `tests/test_knowledge_incremental_refresh.py`
- Create `tests/test_memory_lifecycle_sync.py`

## Planning Boundaries and Checkpoints

建议拆成多个可独立验证的 GSD plans，而不是一个 1.5 小时黑盒 task：

1. **14-02 — Production backfill engine + inventory**：先解决 5,485/2,237 冲突并交付恢复能力。
2. **14-03 — 300–500 pilot + canonicalization implementation**：包含人工 evidence checkpoint 和 hard-negative gate。
3. **14-04 — Full extraction + canonical build + candidate A/B**：长运行 checkpoint；不自动 promote。
4. **14-05 — Promotion hardening + retrieval canary**：30-query 用户/人工 label checkpoint。
5. **14-06 — Incremental refresh + lifecycle closure**：联合 rollback 和 final phase verification。

`14-04` 的生产调用、`14-05` 的真实 promote/canary、memory lifecycle `--write` 都应标记为显式 checkpoint。Planner 可以并行安排纯代码/测试任务，但 SQLite production writer 和 index publisher 必须串行。

## Open Decisions the Plan Must Resolve from Evidence

1. **5,485 的定义**：它是否包含 unified events/evidence bundles，而当前 extractor 只处理 canonical eligible user messages？在 inventory 完成前不要承诺固定调用数。
2. **Production extraction model**：AI-SPEC 锁定 `gpt-5.6-luna`，当前代码实际使用 `gemini-3.5-flash`。必须选择并记录实际可用 model；不可静默复用旧 baseline。
3. **Phase 13.5 source checkpoint**：canonical DB 目前没有 build manifest table；至少要使用 DB checksum/schema/count/time range 形成 immutable source identity，或先补上游 manifest。
4. **Minimum yield**：必须由分层 pilot 预注册，而不是凭 PoC 20 条估算。

## Sources and Confidence

**Primary local sources:** `.planning/STATE.md`、`ROADMAP.md`、`REQUIREMENTS.md`、Phase 14 `CONTEXT`/`AI-SPEC`/`14-01-PLAN`、`.ai-bridge/rag-knowledge-unit-issue.md`、当前 implementation files、当前 tests、SQLite read-only inventory。  
**Confidence:** High for current-code gaps and database counts；Medium for elapsed-time estimates；input total remains unresolved until inventory contract is reconciled.

