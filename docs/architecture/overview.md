<!-- generated-by: gsd-doc-writer -->
# System Architecture

## System overview

Personal Knowledge System is a local, privacy-first personal intelligence platform. It ingests native conversation and activity sources, converts them into provenance-bearing canonical records, derives evaluated knowledge and search indexes, and exposes those results through command-line, REST, MCP, and desktop conversation interfaces. The architecture is layered around explicit authority boundaries: adapters capture external data, application modules own synchronization and knowledge lifecycles, retrieval modules read promoted serving state, and delivery surfaces reach those capabilities through fixed contracts rather than direct database access.

The source dependency direction is delivery → application → domain/foundation, with infrastructure reached through explicit contracts. `src/personal_knowledge/domains/` is compatibility-only; new product code imports canonical implementations from `application/`, `evaluation/`, and `core/`.

2026-08-29 起，平台在上述主链路之外新增了离线语义知识层（`tools/semantic/`）：把可见会话压缩为会话卡与知识事实，经 staging 导出、九类分类、正式层升格与语义收敛沉淀进 `var/db/personal_system.sqlite`，再向量化为 Chroma 语义索引并物化 `subject:` 主题 wiki 页。该层只读 canonical 数据、只写 `var/` 下的库；升格登记的 `knowledge_index_versions` 保持 candidate，不改变在役检索索引的选择。

## Component diagram

```text
Native sources
      |
      v
Adapters + sync ---> Canonical data ---> Knowledge lifecycle ---> Evaluation gates
                           |                                         |
                           |                                         v
                           +-------------------------------> Active retrieval
                           |                                         |
                           v                                         v
                    Python REST / MCP / domain gateway <------> Pi Kernel
                           |    ^                                  ^
                           v    |                                  |
                    CLI / MCP clients                              |
                                +------ Electron desktop shell -----+
```

The desktop uses two deliberately separate read paths. Named Electron bridge methods call fixed loopback routes for predefined desktop state, while AI evidence queries run through a Kernel skill lease, Capability Registry, domain bridge, and governed Python tool. Renderer, preload, and Electron main code do not open authoritative SQLite databases directly.

## Data flow

### Source data to serving knowledge

1. `pk-sync` enters through `personal_knowledge.cli.sync` and delegates to `application.sync`. Conversation-v2 synchronization probes native sources, captures content-addressed artifacts, selects an explicit family adapter, and produces sessions, typed events, relations, fidelity metadata, and provenance.
2. A new conversation generation is staged and checked before activation. The canonical conversation database under `data/canonical/agent/structured/db/` remains the conversation authority and provides compatibility projections for existing consumers.
3. `pk-ku` drives the incremental knowledge lifecycle: inspect, prepare, extract, evaluate, canary, promote, and watermark advancement. Evaluation is a gate; it does not silently promote a candidate.
4. Promotion updates the active knowledge collection selected by `var/db/knowledge_index_active.txt`. Retrieval modules combine canonical messages, conversation turns, knowledge units, and approved fallback layers without treating experimental memory data as the knowledge authority.
5. `rag-search`, REST handlers, MCP handlers, and governed Kernel tools read the active serving state and return bounded results with evidence and freshness metadata.

### Desktop conversation request

1. The renderer calls a named method exposed by `apps/personal_intelligence_desktop/src/preload.cjs`. The preload and main process validate the intent against fixed schemas and IPC allowlists.
2. Electron main routes the normalized request only to the configured loopback authority: Python REST on port `8000` for fixed conversation history and project-scope reads, or the Kernel on port `8790` for turns, task control, candidate review, projection, and proactive controls.
3. For a conversation turn, `KernelHost` creates a contained session. `runConversationTurn` injects only bounded history and approved derived projection context, then exposes tools granted by the selected skill lease.
4. Project operations cross `createProjectDomainBridge` to the fixed Python `/internal/pi-domain/dispatch` route. `PiDomainGateway` validates the capability, declared operation, allowed fields, idempotency key, and binding before dispatching to a concrete read, evidence, orchestration, or guarded-write provider.
5. The Kernel records metadata-only lifecycle events in `EventJournal` and returns safe event categories to the desktop. Prompt bodies, completions, credentials, raw SQL, and physical schemas are excluded from governed event and receipt surfaces.

### 语义知识层管线（离线，2026-08-29 新增）

`tools/semantic/` 七个工具组成一条离线管线，除 LLM 调用外全部本地确定性执行，各步骤幂等可重跑：

```text
canonical 会话（只读）
      |
      v
mvp_semantic_compress.py ---> var/db/semantic_mvp_v3.sqlite（session_cards + ku_facts）
      |
      v
export_ku_staging.py ---> var/db/semantic_ku_staging.sqlite（unit_type='unclassified'）
      |
      v
classify_ku_staging.py ---> 九类枚举分类
      |
      v
promote_ku_formal.py ---> var/db/personal_system.sqlite（正式层，版本登记 candidate）
      |
      v
dedup_canonical_ku.py ---> canonical 层语义收敛
      |
      v
build_semantic_vector_store.py ---> Chroma + semantic_index_registry.json
      |
      v
materialize_wiki.py ---> var/db/personal_wiki_projection.sqlite（subject: 主题页）
```

1. **压缩**（`mvp_semantic_compress.py`）：只读打开 canonical 会话库，剥离 system-reminder 注入后按规模分路径——小会话（≤20 条消息）单窗口（22,000 字符预算）单次调用，大会话 map-reduce（12,000 字符分块、至多 24 块 + 一次合并）。每条事实的 evidence_ids 必须命中实际送入模型的消息 id（缺失 `v2|cm|` 前缀时自动修复，否则丢弃），杜绝编造出处。LLM 经 `PiKernelProvider` 逐次建 pi 内核任务（默认 `http://127.0.0.1:8790` 的 `/v1/tasks`，模型 hy3），带硬性成本上限（`PK_MVP_COST_CAP`，默认 ¥8）。产物写 `var/db/semantic_mvp_v3.sqlite`，绝不写 canonical。
2. **staging 导出**（`export_ku_staging.py`）：把 ku_facts 映射为正式 `knowledge_units` 字段形状写入独立 staging 库；`unit_id = 'stg|' + sha256(fact_key)` 确定性幂等，单事务全量重建；不触碰 canonical 与统合库。
3. **九类分类**（`classify_ku_staging.py`）：仅处理仍为 `unclassified` 的行，经同一 pi 内核 LLM 通道判入九类枚举：preference、habit、personal_fact、project_decision、capability、tool_usage、solution、decision_rationale、technical_conclusion。
4. **正式层升格**（`promote_ku_formal.py`）：把已分类行幂等升格进 `var/db/personal_system.sqlite`——写 `knowledge_build_runs`（run_type='promote'）、`knowledge_units`（正式 `v1|` id）、`knowledge_unit_evidence`、`canonical_knowledge_units`（+members，仅精确归一化分组），并登记一条 status='candidate' 的 `knowledge_index_versions`；在役检索索引（`var/db/knowledge_index_active.txt`）不被切换，serving 切换是独立决策。未分类行留在 staging。
5. **语义收敛**（`dedup_canonical_ku.py`）：从 current KU 两阶段重建 canonical 层——精确归一化分组 + 本地 bge-small-zh 512 维余弦合并（默认阈值 0.95，须同 unit_type）；0.90~0.95 的相似对仅上报待审不合并；标识符冲突守卫要求合并双方标识符词集一致，否则阻断。只重写 promote 运行产出的行。
6. **向量库**（`build_semantic_vector_store.py`）：把 `semantic_mvp_v3.sqlite` 的 session_cards 与 active ku_facts 向量化进 Chroma（默认 `127.0.0.1:8001`）；collection 按 `semantic_mvp_v1_<UTC时间戳>` 版本化，旧版本永不删除；构建登记写 `var/db/semantic_index_registry.json`（candidate | active | superseded，`--activate` 保证 active 至多一个）。embedding 用本机 bge-small-zh-v1.5（512 维，`personal_knowledge.core.local_embed`），不经联网 LLM。
7. **wiki 物化**（`materialize_wiki.py`）：以会话卡实体为主题键把 current KU 物化为 `subject:` 主题页（topic_type 固定 subject，`project:` 等键需 personal 断言背书，不在此层使用）；绑定 KU 数低于 `--min-claims`（默认 5）的主题不建页。正文是 claims + 证据引用的聚合，永不含原始对话正文、不含时间戳（同输入同 `page_checksum`）；唯一可写库是可再生的 `var/db/personal_wiki_projection.sqlite`，重跑内容不变则跳过、源变化才追加不可变新版本。

规模基线（2026-08-29 对库实测）：

| 指标 | 数值 | 出处 |
|---|---|---|
| 压缩会话 / 可见会话 | 1,108 / 1,267 | `semantic_mvp_v3.sqlite` session_cards；canonical 投影谓词筛选的可见会话 |
| current 知识单元 | 7,402 | `personal_system.sqlite` `knowledge_units`（lifecycle='current'） |
| canonical 知识单元 | 7,059 | `personal_system.sqlite` `canonical_knowledge_units` |
| 证据行 | 14,031（10,432 个唯一引用，全部解析到 canonical 消息，零悬空） | `personal_system.sqlite` `knowledge_unit_evidence` |
| 向量文档（active build） | 8,510（bge-small-zh-v1.5，512 维，build `sem_20260829123152`） | `semantic_index_registry.json` |
| wiki 主题页 | 1,595（全部 topic_type='subject'） | `personal_wiki_projection.sqlite` `wiki_projection_pages` |

### 语义会话卡检索面

`src/personal_knowledge/retrieval/semantic_cards.py` 是 MVP 语义层的只读检索适配器：`search_cards` 向量优先——仅当登记存在 active build、Chroma 可达且本机 embedding 模型可用时走 Chroma 向量检索，任一环节失败都无声回退纯 sqlite 关键词打分（字段权重 fact 4 / purpose 3 / summary_md 2 / card_json 1；ASCII 标识符 + 中文 2-gram 分词）；结果行附 `meta={"mode": "vector"|"keyword"}` 标注实际路径；`get_card` 返回单张完整会话卡 + active facts（含 evidence_refs）。两个消费面零改动复用同一适配器：

- MCP 工具 `search_semantic_cards`（`src/personal_knowledge/mcp_tools/tool_definitions.py` 注册，`mcp_tools/handlers/data.py` 进程内直连）；
- REST `POST /search/cards`（`src/personal_knowledge/services/api_server.py` 路由，`services/http/handlers/data.py` 的 `handle_search_cards`；body 传 `session_id` 时返回单卡详情，未找到返回 404）。

## Kernel 契约修复（2026-08-29）

- **任务响应持久化**：`apps/personal_intelligence_kernel/src/tasks/ledger.mjs` 第二个迁移（`002_pi_kernel_task_responses_v1`）在 `var/db/pi_kernel_tasks.sqlite` 增加 `pi_kernel_task_responses` 表（task_id 主键、response_json、sha256 response_checksum、created_at），载荷有界（`MAX_RESPONSE_BYTES` = 1 MB，超限不落库，重放按既有 provider/skill_response_unavailable 契约失败关闭）。`POST /v1/tasks` 带 `include_response=true`（内部能力门控）的重复重放因此可跨重启幂等返回同一响应。
- **路由契约断言**：`apps/personal_intelligence_kernel/src/server.mjs` 的 `ALLOWED_ROUTES` 冻结白名单枚举全部已派发路由；`apps/personal_intelligence_kernel/test/server.test.mjs` 断言五个 `/v1/operations` 控制面路由必须先在白名单声明，防止派发分支与已发布路由契约静默漂移。

## Key abstractions

| Abstraction | Location | Responsibility |
|---|---|---|
| `TypedEvent`, `EventRelation`, `AdaptedSession` | `src/personal_knowledge/core/conversation_events.py` | Canonical conversation event, relation, session, fidelity, and provenance contracts. |
| `SourceArtifactSet`, `CapabilityDescriptor`, `AdaptationResult` | `src/personal_knowledge/adapters/conversation_sources/contracts.py` | Immutable adapter input and deterministic, provenance-validated adapter output. |
| Conversation adapter registry | `src/personal_knowledge/adapters/conversation_sources/registry.py` | Selects a versioned family-specific adapter and fails closed instead of using a generic parser. |
| `shadow_conversation_generation` / `activate_conversation_generation` | `src/personal_knowledge/application/conversation/v2_sync.py` | Stages and activates versioned canonical conversation generations. |
| `pk-ku` command seam | `src/personal_knowledge/application/ku.py` | Coordinates inspection, extraction, evaluation gates, promotion, lifecycle, and watermark operations. |
| Retrieval facade and layers | `src/personal_knowledge/retrieval/unified_search.py`, `src/personal_knowledge/retrieval/layers/` | Presents a stable search API over canonical, knowledge-unit, and fallback retrieval layers. |
| `PiDomainGateway` | `src/personal_knowledge/services/pi_domain_gateway.py` | Enforces the fixed operation registry, capability checks, input allowlists, binding, and idempotency before Python-domain dispatch. |
| `KernelHost` | `apps/personal_intelligence_kernel/src/kernel-host.mjs` | Owns contained model sessions, skills, task control, candidates, domain-tool bridging, and Kernel readiness. |
| `EventJournal` | `apps/personal_intelligence_kernel/src/events/journal.mjs` | Persists bounded Kernel lifecycle events and consumer checkpoints in SQLite. |
| Desktop bridge contract | `apps/personal_intelligence_desktop/src/desktop-api-schema.mjs`, `apps/personal_intelligence_desktop/src/preload.cjs`, `apps/personal_intelligence_desktop/src/main.mjs` | Constrains renderer access to named IPC methods and fixed localhost provider routes. |
| `search_cards` / `get_card` | `src/personal_knowledge/retrieval/semantic_cards.py` | MVP 语义会话卡只读检索适配器：向量优先、关键词回退，`meta.mode` 标注实际路径。 |
| `pi_kernel_task_responses` | `apps/personal_intelligence_kernel/src/tasks/ledger.mjs` | 有界任务响应持久化，支撑 `include_response` 重复重放跨重启幂等。 |
| `ALLOWED_ROUTES` | `apps/personal_intelligence_kernel/src/server.mjs` | 内核 HTTP 路由冻结白名单；测试断言保证派发分支不漂移出已发布契约。 |

## Directory structure rationale

```text
apps/                         User-facing and runtime applications
  personal_intelligence_desktop/  Electron conversation shell
  personal_intelligence_kernel/   Contained Node.js agent runtime
  personal_data_chatgpt/           ChatGPT MCP application and service scripts
  personal_decision_cockpit/       Retained React cockpit source
src/personal_knowledge/       Installable Python product package
  adapters/                   External-source and conversation-family adapters
  application/                Canonical use cases and lifecycle ownership
  core/                       Paths, privacy, event, provider, and SQLite foundations
  evaluation/                 Extraction, retrieval, compare, and audit gates
  retrieval/                  Search backends, serving selection, and stable facade
  services/                   REST, MCP, projection, gateway, and tool delivery
  domains/                    Legacy re-export compatibility shims
tests/                        Unit, contract, integration, governance, and UAT fixtures
assets/                       Versioned prompts, public evaluation fixtures, and vendor assets
governance/                   Machine-readable policies, schemas, and capability manifests
data/                         Private raw, staging, canonical, and import data
var/                          Generated databases, runtime state, reports, logs, and cache
docs/                         Architecture explanations and operator runbooks
tools/ and ops/               Repository tooling, ops helpers, and tools/semantic semantic pipeline
archive/                      Quarantined or retained historical material
```

The separation keeps reviewed source and policies independent from private inputs and generated runtime state. `core.project_paths` is the path authority and derives locations from the repository root, preferring the current `data/` and `var/` layout while retaining limited legacy fallback behavior. `%USERPROFILE%/.agentsview/sessions.db` is an external protected source and is opened read-only; it is never relocated into the repository.

`apps/personal_decision_cockpit/` remains in the tree, but the current Python server explicitly disables its `/app` static hosting and ten cockpit-only projection routes. Active delivery still includes health, search, intelligence, decision, agent, orchestration, review, and wiki-topic handlers defined by `src/personal_knowledge/services/api_server.py`.
