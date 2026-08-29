<!-- refreshed: 2026-08-29 -->
# 在线运行时全景图（RUNTIME_MAP）

**分析日期:** 2026-08-29
**范围:** 只测绘"在线运行时"——内核内部结构、技能/工具覆盖、REST 服务面、前端三件套、运行入口；回答"这个系统有几套在线设计、哪些活着哪些遗留"。
**方法:** 全部论断基于源码与清单文件的实际读取；未验证项已标注。`var/config/pi-provider.json` 仅读取非密钥字段（api_key 已脱敏）；`var/secrets/` 仅记录存在。

---

## 1. 概览：一共四套在线设计 + 一批已退役痕迹

| # | 设计 | 入口 | 状态 |
|---|------|------|------|
| 1 | **Pi 智能体栈（primary）** | `ops/runtime/start-agent-stack.ps1` 拉起 REST :8000 + Pi 内核 :8790 + GPT Apps MCP :8789（+可选 tunnel :8081） | **在役主链路**。运行时模式指针 `var/db/pi_runtime_activation.pointer.json` 为 `"mode": "primary"`（2026-08-12 由 canary 升级，Phase 53/60 验收） |
| 2 | **个人检索直接面（legacy-grade REST）** | `rag-api`（`src/personal_knowledge/services/api_server.py` 同一进程）的 `/search/*` `/memory*` `/profile` `/data/*` `/categories` `/event/*` 路由 + stdio MCP `rag-mcp`（`src/personal_knowledge/services/mcp_server.py`，55 工具） | **在役并存**，不经 Pi 内核；`pyproject.toml:10-20` 仍注册为 console scripts |
| 3 | **Decision Cockpit web** | `apps/personal_decision_cockpit`（React+Vite）经 REST `/app` 托管 + 10 条 `/ui/*` 投影路由 | **FROZEN 2026-08-11**（`apps/personal_decision_cockpit/FROZEN.md`），分发处已注释，代码保留；wiki 4 条 `/ui/topic*` 例外保持可用 |
| 4 | **Electron 桌面壳** | `apps/personal_intelligence_desktop`（Electron 43，12 文件）固定 loopback 路由图 → kernel :8790 + Python :8000（Phase 61-11） | 已实现、可跑（`npm start`）；日常使用度**未验证** |
| 退役 | rag-pipeline、旧图伪关系、semantic_mvp v1/v2、pi runtime legacy/shadow/canary 模式 | 见 §6 | 硬禁用/归档 |

**主数据通路（conversation turn 为例）：**
`apps/personal_intelligence_desktop`（或任意客户端）→ `POST :8790/v1/conversations/turn`（`apps/personal_intelligence_kernel/src/server.mjs:339`）→ `KernelHost.executeConversationTurn`（`apps/personal_intelligence_kernel/src/kernel-host.mjs:600`）→ 派生 conversation lease（`runtime/resource-policy.mjs` 按 side_effect_class 过滤 capability）→ `conversation/turn-service.mjs:runConversationTurn` 驱动真实 Pi `AgentSession` 迭代环 → 模型工具调用经 `tools/domain-bridge.mjs:createProjectDomainBridge` → `POST :8000/internal/pi-domain/dispatch` → Python 域网关五道闸（`src/personal_knowledge/services/pi_domain_gateway.py`）→ 各 read/tool handler → 结果回注回合。

---

## 2. 内核内部结构（apps/personal_intelligence_kernel/src/，26 模块 / 4972 行）

排除 `node_modules`（2000+ 文件均为依赖）。包声明 `apps/personal_intelligence_kernel/package.json`：`@earendil-works/pi-ai` / `pi-coding-agent` / `pi-storage-sqlite-node` 0.83.0，Node ≥22.19。

### 2.1 模块清单与职责

| 模块 | 行数 | 职责 |
|------|------|------|
| `server.mjs` | 586 | HTTP 壳：路由表（`ALLOWED_ROUTES` 23 条 + 实际分发分支）、64KB body 上限、安全错误码白名单（`SAFE_ERROR_CODES` 70+）、SSE、CLI（`runKernelServerCli`） |
| `kernel-host.mjs` | 1136 | 唯一业务 host：`executeTask`（纯模型任务）/`executeSkillTask`（技能步骤机）/`executeConversationTurn`（真实对话回合）/`createConversationSession`/`stageCandidate`/`reviewCandidate`/`getModelProjection`/proactive 4 固定路由/cancel/reconcile；持有全部 store 与 Phase 48 包决策门（`governance/manifests/ai/pi-package-decision.json`） |
| `events/journal.mjs` | 352 | SQLite 事件账本 `var/db/pi_kernel_events.sqlite`（append-only、幂等键、consumer checkpoint、SSE replay） |
| `events/schema.mjs` | 300 | `pi_kernel_event_v1` 事件构造/校验（20+ 事件类型，含 `conversation.delta.committed`） |
| `tasks/ledger.mjs` | 139 | 任务账本 `var/db/pi_kernel_tasks.sqlite`：7 状态机 + lease + outbox，**持久化** |
| `sessions/store.mjs` | 28 | 会话元数据 `var/db/pi_kernel_sessions.sqlite`：拒绝 body/prompt/credential 字段（metadata-only） |
| `candidates/store.mjs` | 20 | 候选元数据 `var/db/pi_kernel_candidates.sqlite`：禁 serving/promotion 权威词 |
| `conversation/turn-service.mjs` | 289 | 单回合 AgentSession 生命周期（订阅→prompt→idle→dispose），只投影安全事件类别 |
| `conversation/session-service.mjs` | 115 | governed 空会话创建（Plan 61-05）：经 Python `conversation.project_scope.select` 批准 scope |
| `runtime/conversation-session.mjs` | 117 | 每回合 AgentSession 工厂；真实 `ModelRuntime`（opencode-go provider，key=OPENCODE_API_KEY 或 pi-provider.json） |
| `runtime/resource-policy.mjs` | 259 | 三 profile allowlist（conversation=只读 / reflection=candidate / operator=mutation）、containment 会话（noExtensions/noSkills/noPromptTemplates/noThemes/noContextFiles） |
| `runtime/containment-probe.mjs` | 317 | 运行时遏制探针（敌意 fixture 验证）——**仅测试引用**（`test/runtime-containment.test.mjs`），资格验证工具非主链路 |
| `reflection/conversation-delta-dispatcher.mjs` | 98 | Plan 61-06 持久重放 dispatcher（conversation.delta.committed → guarded staging）——**无生产 caller，仅测试引用**（见 §6） |
| `models/routes.mjs` | 158 | 7 个 purpose 路由表；budget 优先级 env > pi-provider.json routes > 全局键 > `governance/manifests/ai/pi-model-routes.json` > 内嵌常量 |
| `models/persistent-config.mjs` | 120 | 读 `var/config/pi-provider.json`（schema `pi-provider-config-v1`）；DPAPI secret 解密 fallback（`var/secrets/dashscope.api.dpapi.txt`，存在，未读内容） |
| `models/runtime-provider.mjs` | 37 | adapter 工厂：replay（默认）/vertex_google/dashscope/openai-compatible |
| `models/provider-adapter.mjs` | 30 | ProviderAdapter：checksum 收据、cost ceiling、outcome_unknown 记账 |
| `models/dashscope-transport.mjs` | 120 | DashScope/OpenAI 兼容 chat completions（https 强制、超时 abort） |
| `models/vertex-google-transport.mjs` | 117 | Vertex via `gcloud auth print-access-token` + undici（支持代理） |
| `skills/registry.mjs` | 65 | `pi-project-skill-v1` 校验：checksum 绑定、profile、budget 上限、步骤/工具白名单、snapshot.activate/rollback 必须要求确认 |
| `skills/engine.mjs` | 67 | 技能步骤状态机（内存态；round/step 上限、confirmation checkpoint） |
| `control/runtime-control.mjs` + `control/operation-schema.mjs` | 96+124 | 操作控制平面（**内存** Map，非持久）：`op:task:*` 信封、合法迁移、禁内联 body/prompt 字段 |
| `tools/domain-bridge.mjs` | 75 | `createProjectDomainBridge`（在役）：操作白名单 + binding 三元组强制 + `POST /internal/pi-domain/dispatch`；`createDomainBridge`（Phase 48 四工具旧版）**遗留无调用方**（见 §6） |
| `tools/capability-registry.mjs` | 67 | 加载 `governance/manifests/capabilities/project-capabilities.json`（checksum 漂移即 fail-closed） |
| `transport/sse.mjs` | 140 | `GET /v1/events/stream` SSE（Last-Event-ID 游标、心跳） |

### 2.2 调用关系（文字结构图）

```text
runKernelServerCli (server.mjs:551)
  └─ createKernelHttpServer → attachRequestHandler（23 路由分发）
       └─ KernelHost (kernel-host.mjs:220)
            ├─ 持久层: EventJournal / TaskLedger / SessionStore / CandidateStore  (var/db/pi_kernel_*.sqlite)
            ├─ 控制面: KernelRuntimeControl（内存）
            ├─ 技能线: SkillRegistry(governance/manifests/ai/pi-skills.json) → SkillEngine → executor 闭包 → domainBridge
            ├─ 任务线: getModelRoute(models/routes) → ProviderAdapter(models/runtime-provider → dashscope/vertex transport)
            ├─ 对话线: deriveConversationLease(runtime/resource-policy) → conversationSessionFactory(runtime/conversation-session
            │          → @earendil-works/pi-coding-agent AgentSession) → runConversationTurn(conversation/turn-service)
            │          → invokeTool 闭包 → leaseBridge(domain-bridge) ──HTTP──▶ REST :8000 /internal/pi-domain/dispatch
            └─ 固定路由线: reviewCandidate / getModelProjection / proactive×4 → domainBridge（同一网关）
```

与主链路无关的模块：`runtime/containment-probe.mjs`、`reflection/conversation-delta-dispatcher.mjs`、`tools/domain-bridge.mjs` 内的 `createDomainBridge`——三者均无生产 import（§6）。

---

## 3. 技能与工具清单

### 3.1 技能（governance/manifests/ai/pi-skills.json，11 个全部 active 1.0.0）

| 技能 | allowed_tools |
|------|---------------|
| personal.daily_brief | system.health, state.current, knowledge.search, retrieval.status |
| knowledge.research | wiki.page, knowledge.search, evidence.resolve, knowledge.get, wiki.directory, external.list, evidence.sqlite_query |
| decision.support | state.current, decision.list, evidence.resolve, external.list |
| project.planning | knowledge.search, state.current, decision.list, action_outcome.list |
| outcome.reflection | action_outcome.list, evidence.resolve, knowledge.search |
| system.diagnosis | system.health, system.runtime, warehouse.inspect, warehouse.quality, warehouse.integrity |
| knowledge.maintenance | warehouse.inspect, knowledge.extract_l1, knowledge.repair_candidates, knowledge.detect_conflicts, knowledge.backfill, canonical.verify |
| warehouse.health | warehouse.inspect, warehouse.lineage, warehouse.quality, warehouse.freshness, warehouse.integrity, warehouse.failed_batches |
| warehouse.failed_batch_recovery | warehouse.failed_batches, ingestion.preview, ingestion.quarantine, ingestion.commit, canonical.verify |
| retrieval.rebuild | warehouse.inspect, index.build, index.reconcile, index.evaluate, snapshot.prepare |
| snapshot.release | warehouse.inspect, index.reconcile, index.evaluate, snapshot.prepare, snapshot.activate, snapshot.rollback |

技能经 `POST /v1/tasks`（带 skill_id）或 conversation turn（`skill_id` 参数）执行；两条线都落在上述 45 个 capability 操作上。

### 3.2 工具/操作覆盖（governance/manifests/capabilities/project-capabilities.json 45 个操作 → Python handler 全覆盖）

已验证：`registry ops NOT in gateway = []`（45/45 在 `pi_domain_gateway.py` 的 `OPERATIONS` ∪ `PROJECT_OPERATIONS` 中可 dispatch）。**没有"声明了但无实现"的操作**；`unsupported_read_operation` 仅对 registry 之外未知 read 触发（`pi_read_dispatch.py:700`）。

| 实现文件 | 覆盖操作 | 数量 |
|----------|----------|------|
| `src/personal_knowledge/services/pi_read_dispatch.py`（`_HANDLERS` :668-687） | state.current/changes, decision.list/get, external.list/get, action_outcome.list, knowledge.search/get, retrieval.status/search, wiki.page/directory, evidence.resolve, data_quality.report/failed_batches, system.health/runtime | 18 |
| `src/personal_knowledge/services/evidence_sqlite_tool.py` | evidence.sqlite_query（bounded descriptor-only，需 skill_id+manifest_checksum+privacy_ceiling 租约，`kernel-host.mjs:433-437`） | 1 |
| `src/personal_knowledge/services/warehouse_tools.py` | warehouse.inspect/lineage/quality/freshness/integrity/failed_batches | 6 |
| `src/personal_knowledge/services/semantic_maintenance_tools.py` | knowledge.extract_l1/extract_l2/repair_candidates/detect_conflicts/backfill | 5 |
| `src/personal_knowledge/services/retrieval_maintenance_tools.py` | index.build/reconcile/evaluate | 3 |
| `src/personal_knowledge/services/snapshot_release_tools.py` | snapshot.prepare/activate/rollback | 3 |
| `src/personal_knowledge/services/warehouse_mutations.py`（WarehouseOperationLedger） | ingestion.discover/preview/commit/quarantine, canonical.reconcile/deduplicate/link/apply_correction/verify（共 9 个独占；另冗余注册 semantic/retrieval/snapshot 的 11 个，dispatch 顺序使其永不命中，见 §7） | 9 独占 |

gateway 额外注册 16 个非 capability 操作（`OPERATIONS`，:36-215）：`conversation.thread.last/recent/select`、`conversation.project_scopes.list`、`conversation.project_scope.select`（实现 `harness_conversation_service.py`，HARNESS-01）、`conversation.reflection.stage`（→ `application/conversation/harness_reflection.py`）、`candidate.review`、`personal.model_projection.get`、`proactive.state.get/controls.update/dismiss/dismiss.undo`、`domain.inspect`、`domain.candidate`、`session.preview`、`session.confirm`。

---

## 4. REST 服务面（src/personal_knowledge/services/，26 个模块 + http/handlers/ 9 个）

### 4.1 api_server.py（:8000，纯标准库 ThreadingHTTPServer）路由状态

**在线 GET**（`api_server.py:529-616` do_GET）：
- `/health` `/stats` `/knowledge(+/status)` — 元信息
- `/ui/review` — 999.5 单人评审台（`eval_review.py`）；`POST /ui/review/labels`
- `/ui/topics` `/ui/topic` `/ui/topic/backlinks` `/ui/topic/resolve` — wiki 统合层（`topic_projection.py`，**当前产品方向**）
- `/intelligence/*` 4 条、`/decision/recommendation*` 5 条、`/proactive/*` 6 条、`/agent/*` 12 条 — 决策智能读面（`http/handlers/`，服务实现 `decision_intelligence_reads.py`、`orchestration_service.py`）
- `/api/pi/status|tasks|operations[/*]|events` — Pi 内核元数据投影（`pi_runtime_projection.py` / `pi_operation_projection.py`，转发 kernel :8790）
- `/categories` `/data/*` `/memory*` `/profile` `/event/*`、`POST /search/semantic` `/search/query` — 个人数据直接检索面

**在线 POST**（:628-684）：`/api/pi/cancel|resume`、`/api/pi/operations/*`、**`/internal/pi-domain/dispatch`**（域网关唯一入口）、`/agent/session/*`（SESSION_WRITE_ROUTES，Origin 门禁先行，`orchestration_service.py`）。

**FROZEN 2026-08-11（代码保留、分发注释，请求落 404）**：`GET /app[/<path>]`（cockpit SPA 托管）、`/ui/overview` `/ui/system/status` `/ui/personal-state` `/ui/external/delta` `/ui/decision-queue` `/ui/decision/workspace` `/ui/actions/recent` `/ui/proactive/summary` `/ui/calibration/overview` `/ui/evidence/resolve` 共 11 个入口（`api_server.py:542-601` 注释段；清单见 `apps/personal_decision_cockpit/FROZEN.md`）。

### 4.2 域网关（pi_domain_gateway.py，553 行）五道闸

1. 能力头 `X-PI-Domain-Capability`（默认 `pi-domain-local-capability-v1`，:29-30）
2. 操作注册表（61 个操作名 = 45 capability + 16 额外）
3. 参数白名单（每操作 `allowed` 字段集）
4. 绑定三元组 `task_id + idempotency_key + binding`（`domain.*` 免 task_id 例外，:298）
5. 隐私分级 R0/R1/R2（每操作 `privacy` 字段；proactive/reflection 为 R2）

### 4.3 其余服务模块角色

| 模块 | 角色 | 状态 |
|------|------|------|
| `mcp_server.py` (167) + `mcp_tools/`（tool_definitions 55 工具） | stdio MCP（`rag-mcp` console script） | 在役（本地 CLI/编辑器面；与 :8789 并存，§7） |
| `dashboard.py` (671) | `rag-dashboard` 交互仪表盘 | 在役（独立入口） |
| `eval_review.py` (306) | 999.5 评审台（/ui/review） | 在役 |
| `topic_projection.py` (851) | wiki P0 只读投影 | 在役（当前产品核心入口） |
| `harness_conversation_service.py` (809) | conversation.thread/project_scope 5 个 canonical read provider | 在役（被 kernel history 解析与 session 创建调用） |
| `pi_runtime_activation.py` (193) | runtime 模式权威（legacy/shadow/canary/primary 单向升级链 + 指针文件） | 在役，当前 primary |
| `pi_runtime_projection.py`/`pi_operation_projection.py` | /api/pi/* 元数据投影 | 在役 |
| `agent_contract.py`/`http_contracts.py` | 紧凑信封/REST 适配薄层 | 在役 |
| `ui_projection.py` (100) | Cockpit 专用投影层 | **部分冻结**——10 条 /ui 路由停用后无 GET 分发方；`未验证` 是否仍被 /ui/review 复用 |

无调用方的路由：FROZEN 的 11 个入口即全部（§4.1）。

---

## 5. 前端/客户端三件套

| App | 技术栈 | 规模 | 状态 | 与在线栈的连接 |
|-----|--------|------|------|----------------|
| `apps/personal_decision_cockpit` | React 18 + Vite + TS + Tailwind + @tanstack/react-query + zod（`package.json`） | 128 文件（不含 node_modules；含 `dist/` 构建产物） | **FROZEN 2026-08-11**（`FROZEN.md`）：产品方向调整为 wiki 统合层，web 不再是核心入口；源码/dist/工具链保留备查，恢复方式写在 FROZEN.md | 已断：REST `/app` 托管与 10 条 `/ui/*` 投影停用；其 `src/api/` 调用的 `/proactive/*`、`/agent/session/*`、`/api/pi/*` 等 REST 路由本身仍在线（只是无前端消费） |
| `apps/personal_data_chatgpt` | 纯 Node（零运行时依赖）HTTP server | 36 文件 | **在役**（start-agent-stack 第 3 服务 `mcp`） | MCP Apps adapter `server.mjs` :8789，端点 `/mcp`（协议 2025-06-18），后端固定 `PERSONAL_DATA_REST_URL` → :8000；core/full 双 profile；从 `governance/manifests/capabilities/generated/project-capability-descriptors.production.json` 读描述符并做 checksum 校验；`scripts/start-services.ps1` + `启动服务.bat` 为 canonical 启动器的薄包装 |
| `apps/personal_intelligence_desktop` | Electron 43.3.0（唯一 devDep），ESM | 12 文件（main/preload/renderer + schema + test） | 已实现可跑（Phase 61-11），使用度**未验证** | `src/main.mjs:286-287` 固定 `DEFAULT_KERNEL_BASE_URL=http://127.0.0.1:8790` + `DEFAULT_PYTHON_BASE_URL=http://127.0.0.1:8000`；仅 127.0.0.1/::1/localhost 放行（:437）；conversation-first renderer |

---

## 6. 孤儿与遗留清单

**内核内（apps/personal_intelligence_kernel/src/）**
- `tools/domain-bridge.mjs` 的 `createDomainBridge` + `PI_DOMAIN_TOOL_REGISTRY`（domain_inspect/domain_candidate/session_preview/session_confirm 四个 Phase 48 工具名）：文件内仅 `createProjectDomainBridge` 被 `kernel-host.mjs:21` 与测试 import；四工具旧桥**无生产调用方**（遗留）。
- `runtime/containment-probe.mjs`（317 行）：仅 `test/runtime-containment.test.mjs` 引用——资格验证探针，不在 serve 主链路（半孤儿，测试资产）。
- `reflection/conversation-delta-dispatcher.mjs`（98 行）：Plan 61-06 的"唯一消费路径"，但生产代码无启动点，仅 `test/conversation-delta-reflection.test.mjs` 引用；下游 `conversation.reflection.stage` provider（`pi_domain_gateway.py:68`）与 adapter（`src/personal_knowledge/application/conversation/harness_reflection.py`）已实现——**反思闭环整体已建成但未接线**（半孤儿，链路断在 kernel 侧无 dispatcher 启动器）。
- `server.mjs:294-338` 已实现 `GET /v1/operations`、`GET /v1/operations/:id`、`POST /v1/operations/:id/(cancel|resume|reconcile)` 分支，但 `ALLOWED_ROUTES`（:10-34）未声明这 5 条——文档/测试契约漂移（功能本身经 `control/runtime-control.mjs` 在役）。
- `events/schema.mjs` 事件类型中的 `started/completed/cancelled/failed/candidate_created/operation_*`（:652-661）为"原型兼容名"，项目自注非主用。

**Python 服务面**
- `ui_projection.py`：Cockpit 投影层，其 10 条路由 FROZEN 后无主分发方（部分冻结，`未验证`残留复用）。
- `http/handlers/meta_handlers.py` 的 `serve_cockpit_static`：随 /app 托管冻结而停用。

**数据/CLI/脚本**
- `rag-pipeline` console script：已退役（`pyproject.toml:15-16`），默认 exit 2 重定向，取证需 `PK_ALLOW_LEGACY_PIPELINE=1`（`README.md`、`AGENTS.md`）。
- `var/db/semantic_mvp.sqlite` / `semantic_mvp_v2.sqlite` / `semantic_mvp_v3.sqlite`：三个世代并存（v1/v2 疑似遗留，`未验证`读取方）。
- `var/db/conversation_graph.duckdb` 旧伪关系方案：`var/db/DEPRECATED.md` 明确废弃，仅新图流水线（8 步 judge 链）有效。
- `var/config/pi-provider.json.bak-20260809/-20260811/-20260829`：三份配置备份（存在，未读内容）。
- `ops/reports/`（plan35-* 系列 stdout/stderr 日志、证据 json）：历史验收证据归档，非运行资产。
- `ops/state/agent-stack.json` 记录 2026-08-23 一次运行、pid=null healthy=false——栈当前**未在运行**（快照性质，`未验证`实时端口）。
- `var/secrets/dashscope.api.dpapi.txt`：DPAPI 加密的 DashScope key 备用通道，与 pi-provider.json 明文 api_key 并存（仅记录存在；双通道见 §7）。

**已知缺陷（确认位置）**
- 内核 `include_response` 幂等重放：响应缓存仅内存 `this.ephemeralResponses = new Map()`（`kernel-host.mjs:246`）；重启后带 `include_response` 的重复请求抛 `provider_response_unavailable`（`kernel-host.mjs:530-533` executeTask 分支）/ `skill_response_unavailable`（:384-386 executeSkillTask 分支）。任务账本本身持久（`tasks/ledger.mjs`），二者不对称。

---

## 7. 平行设计 / 重复实现

1. **双 MCP server**：stdio `src/personal_knowledge/services/mcp_server.py`（`rag-mcp`，55 工具，本地 CLI 面）vs HTTP `apps/personal_data_chatgpt/server.mjs`（:8789，ChatGPT Apps 面，capability descriptors）。同一 capability bundle、两条暴露通道。
2. **双 provider 调用通道（内核内）**：`models/provider-adapter.mjs` + `dashscope/vertex transport`（executeTask 技能/任务线）vs `runtime/conversation-session.mjs` 的 pi `ModelRuntime`（opencode-go，对话回合线）。同一 `var/config/pi-provider.json` 的 key/model 喂两套 HTTP 客户端。
3. **双凭据通道**：`var/config/pi-provider.json` 明文 `api_key`（2026-08-11 起支持，`persistent-config.mjs:534-537` 注释自认）+ `var/secrets/dashscope.api.dpapi.txt` DPAPI 解密 fallback（`persistent-config.mjs:603-627` 仍保留）。
4. **双 domain bridge**：`tools/domain-bridge.mjs` 内 `createDomainBridge`（4 固定工具，遗留）与 `createProjectDomainBridge`（在役）同文件共存。
5. **mutation 操作冗余注册**：`warehouse_mutations.py` 的 `MUTATION_OPERATIONS`（20 个）包含 semantic/retrieval/snapshot 工具已实现的 `knowledge.extract_l1/l2/repair_candidates/detect_conflicts/backfill`、`index.build/reconcile/evaluate`、`snapshot.prepare/activate/rollback` 共 11 个；gateway dispatch 顺序（semantic→retrieval→snapshot→mutation，`pi_domain_gateway.py:318-334`）使冗余项永不命中——无功能缺陷，但注册表有双份真相。
6. **capability registry 双语言加载器**：`src/personal_knowledge/services/capability_registry.py`（Python）与 `apps/personal_intelligence_kernel/src/tools/capability-registry.mjs`（Node）各自实现同一 manifest 的 checksum/profile 校验。
7. **/api/pi/* 投影 vs 内核原生路由**：Python `pi_runtime_projection.py`/`pi_operation_projection.py` 转发 kernel :8790 元数据给 cockpit；同一数据 kernel 原生路由（`GET /v1/tasks` 等）也直接暴露——两个出口。
8. **会话/对话存储双轨**：kernel `pi_kernel_sessions.sqlite`（metadata-only 轨迹）vs Python canonical `data/canonical/agent/structured/db/agent_conversations.sqlite`（SSOT）+ `var/db/conversation_reflection.sqlite`（reflection ledger，`pi_domain_gateway.py:71`）。
9. **前端双世代**：cockpit web（React，冻结）vs desktop Electron（Phase 61）——同为"人的界面"的两个设计，前者代码完整保留。
10. **启动脚本双入口**：`ops/runtime/start-agent-stack.ps1`（canonical）vs `apps/personal_data_chatgpt/scripts/start-services.ps1`/`启动服务.bat`（薄包装转发，FROZEN.md 确认无 cockpit 逻辑——已消解为单一实现，仅入口名字面重复）。

---

## 8. 组件状态总表

| 组件 | 状态 | 证据 |
|------|------|------|
| Pi 内核 HTTP `server.mjs` | 在役 | `apps/personal_intelligence_kernel/src/server.mjs`（23+5 路由） |
| `kernel-host.mjs` executeTask/SkillTask/Turn | 在役 | `kernel-host.mjs:359/507/600` |
| 内核任务/事件/会话/候选账本 | 在役（持久） | `var/db/pi_kernel_{tasks,events,sessions,candidates}.sqlite`；各 store 文件 |
| 内核操作控制平面 | 在役（内存，非持久） | `control/runtime-control.mjs` |
| include_response 重放 | **有缺陷** | `kernel-host.mjs:246,530-533,384-386` |
| 技能清单 11 技能 45 工具 | 在役，全覆盖 | `governance/manifests/ai/pi-skills.json`；`pi_domain_gateway.py` diff 结果 registry 缺口=[] |
| conversation.thread 等 5 read provider | 在役 | `harness_conversation_service.py`；`pi_domain_gateway.py:36-62` |
| 反思闭环（delta→dispatcher→reflection.stage→harness_reflection） | **已建成未接线** | `reflection/conversation-delta-dispatcher.mjs` 仅测试引用；provider/adapter 在役待触发 |
| 域网关五道闸 | 在役 | `pi_domain_gateway.py:29-30,36-215,291-334` |
| REST 决策智能路由（/intelligence /decision /proactive /agent /ui/review /ui/topic*） | 在役 | `api_server.py:529-616` |
| REST 个人数据直接面（/search /memory /profile /data /categories /event） | 在役（并存设计#2） | `api_server.py:608-614,670-675`；`AGENTS.md` 检索 CLI 表 |
| /api/pi/* 投影 | 在役 | `pi_runtime_projection.py`、`api_server.py:537-541` |
| stdio MCP `rag-mcp` | 在役 | `pyproject.toml:19`；`mcp_server.py:105`（55 工具） |
| GPT Apps MCP :8789 | 在役 | `apps/personal_data_chatgpt/server.mjs`、`AGENTS.md` MCP 服务表 |
| Cockpit web + /app + 10 /ui 投影 | **冻结** | `apps/personal_decision_cockpit/FROZEN.md`；`api_server.py:542-601` 注释段 |
| ui_projection.py | 部分冻结 | `ui_projection.py`；分发方已注释（`未验证`残留引用） |
| Electron desktop | 可用（使用度未验证） | `apps/personal_intelligence_desktop/src/main.mjs:286-287,437` |
| wiki 统合层 /ui/topic* | 在役（当前产品方向） | `api_server.py:602-604`；`FROZEN.md` "保持可用"节 |
| runtime 模式 legacy/shadow/canary/primary | primary（指针） | `var/db/pi_runtime_activation.pointer.json`；`pi_runtime_activation.py` |
| start-agent-stack.ps1 | 在役 canonical 启动器 | `ops/runtime/start-agent-stack.ps1`（rest/pi-kernel/mcp/tunnel 4 服务，:162,223） |
| chatgpt start-services.ps1 / 启动服务.bat | 在役（薄包装） | `apps/personal_data_chatgpt/scripts/start-services.ps1:8-10` |
| smoke-agent-stack.py / live-agent-acceptance.py | 在役（验收工具） | `ops/runtime/*.py` docstring |
| register-native-sync.ps1 | 在役（计划任务注册器，每日 23:00 pk-sync --v2-native，metadata-only shadow） | `tools/register-native-sync.ps1:1-13` |
| createDomainBridge 四工具旧桥 | **遗留无调用方** | `tools/domain-bridge.mjs:4-9`；仅文件内自引用 |
| containment-probe | 测试专用 | `test/runtime-containment.test.mjs` |
| rag-pipeline CLI | 退役（exit 2） | `pyproject.toml:15-16`；`AGENTS.md` |
| semantic_mvp v1/v2、旧图流水线、pi-provider .bak×3、plan35 证据 | 遗留/归档 | `var/db/`、`var/db/DEPRECATED.md`、`var/config/`、`ops/reports/` |
| Kernel 19 个测试文件 | 在役（测试资产） | `apps/personal_intelligence_kernel/test/*.test.mjs` |

---

*Runtime map analysis: 2026-08-29*
