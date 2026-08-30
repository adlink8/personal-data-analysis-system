<!-- generated-by: gsd-doc-writer -->
# Pi 内核运维手册（runbook）

PI Kernel 是监听 loopback 的 Node 服务（`apps/personal_intelligence_kernel/`），承载任务/会话/事件账本、provider 路由与 Python 侧的 OpenAI 兼容调用面。本手册覆盖启动/停止、HTTP 面、持久化账本、故障排查与 Python 契约。端口与全部环境变量语义见 [`docs/configuration/overview.md`](../configuration/overview.md)，本文不重复展开。

## 0. 组件与端口速览

| 服务 | 端口 | 健康端点 | 启动方 |
|---|---|---|---|
| REST（`personal_knowledge.services.api_server`） | 8000 | `GET /health` | 监督脚本 |
| PI Kernel（`apps/personal_intelligence_kernel/src/server.mjs`） | 8790 | `GET /ready`（另有 `GET /health` 存活探针） | 监督脚本 / 手工 node |
| ChatGPT MCP（`apps/personal_data_chatgpt/server.mjs`） | 8789 | `GET /health` | 监督脚本 |
| Tunnel（可选） | 8081 | `GET /readyz` | 监督脚本（`-SkipTunnel` 关闭） |

内核只允许绑定 `127.0.0.1`（非 loopback 报 `non_loopback_bind`）。运行时依赖：Node ≥ 22.19.0（使用内置 `node:sqlite`）、决策文件 `governance/manifests/ai/pi-package-decision.json` 处于 accepted 且未过期状态、技能清单 `governance/manifests/ai/pi-skills.json` 非空。

## 1. 启动与停止

### 1.1 正式入口：`ops/runtime/start-agent-stack.ps1`

```powershell
# 完整栈（REST + Kernel + MCP + Tunnel；Tunnel 需 CONTROL_PLANE_API_KEY）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1

# 开发常用：跳过 Tunnel
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -SkipTunnel
```

`-Mode` 取值（默认 `Run`）：

| Mode | 行为 |
|---|---|
| `Run` | 前台监督：预检 → 生成密钥 → 拉起子进程 → 每 `-HealthIntervalSeconds`（默认 5s）轮询健康端点，故障按 `-MaxRestarts`（默认 3）指数退避重启（延迟 `min(2^(n-1), 8)` 秒） |
| `Check` | 只跑预检，零写入后返回 |
| `Probe` | 对已启动服务做一次就绪探测，全部健康返回，否则 `readiness_failed:<unhealthy>` |
| `Stop` | 读取 `ops/state/agent-stack.json`，校验进程所有权后停止 supervisor 与自有子进程 |
| `Status` | 打印 state 文件中各服务的 pid / adopted / healthy / health_url |

常用参数：`-RestPort 8000 -McpPort 8789 -KernelPort 8790 -TunnelHealthPort 8081`、`-SkipTunnel`、`-RunForSeconds`（限时运行后退出）、`-DryRun`。四个端口必须互不相同，否则预检报 `ports_must_be_unique`。

**子进程注入**（脚本每次运行在内存随机生成，不要手工持久化）：

| 子进程 | 注入的环境变量 |
|---|---|
| REST | `PERSONAL_DATA_ORCHESTRATION_SECRET`（编排确认 HMAC 材料）、`PI_KERNEL_INTERNAL_CAPABILITY`、`PI_KERNEL_URL=http://127.0.0.1:8790`、`PI_KERNEL_AI_WORKFLOW=1` |
| PI Kernel | `PI_KERNEL_PORT`、`PI_KERNEL_INTERNAL_CAPABILITY`（与 REST 同值） |
| MCP | `PORT`、`PERSONAL_DATA_REST_URL` |

启动前脚本还会对 `var/db/decision_orchestration.sqlite` 应用编排 schema（失败报 `orchestration_schema_provision_failed`）。日志写 `ops/logs/agent-stack.jsonl`（10 MB 轮转归档），状态写 `ops/state/agent-stack.json`。

**端口占用行为**：健康端点已通 → 复用既有服务（`service_reused`，标记 `adopted`）；端口被监听但健康探测不通 → `unhealthy_port_conflict:<service>:<port>` 终止。

### 1.2 开发/离线最小启动（只跑内核）

跳过监督脚本、单独启动内核进程即可（离线/零费用场景配合 `PI_KERNEL_PROVIDER_MODE=replay`）：

```powershell
cd <project-root>
$env:PI_KERNEL_PROVIDER_MODE = 'replay'                      # 离线 replay；缺省读 var/config/pi-provider.json 的 mode
$env:PI_KERNEL_INTERNAL_CAPABILITY = '<本地任意能力值>'        # 仅 include_response 与 /internal 路由需要；Python 侧必须同值
node apps\personal_intelligence_kernel\src\server.mjs --port 8790
```

- CLI 参数：`--port`（或 `PI_KERNEL_PORT`）、`--project-root`、`--decision-path`、`--database-path`、`--provider-mode`（或 `PI_KERNEL_PROVIDER_MODE`）、`--shutdown-timeout-ms` 等。
- 默认监听 `127.0.0.1:8790`；`--port 0` 时随机挑一个 loopback 端口。
- 启动即依次执行：决策文件校验 → 事件/任务/会话/候选四个 SQLite 迁移 → provider 适配器构建（配置缺失回落 replay）→ 资源策略断言（必须是空的 Capability Registry 会话）→ 监听。任一步失败即退出，stderr 输出一行 `{"ok":false,"error":{"code":"..."}}`。
- 就绪校验：`Invoke-WebRequest -Uri http://127.0.0.1:8790/ready -NoProxy` 返回 200。
- 前台进程随 Ctrl+C（SIGINT）优雅停止；supervisor 场景交给 `-Mode Stop`。

注意：`include_response: true` 的调用者必须带 `X-PI-Internal-Capability` 头且与 `PI_KERNEL_INTERNAL_CAPABILITY` 一致；Python 侧（`make_llm_client` / `PiKernelProvider`）同样读这两个值，两边必须一致。

### 1.3 停止

**监督脚本启动的栈**：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -Mode Stop
```

脚本会校验 supervisor 与各子进程的命令行所有权（不匹配报 `supervisor_ownership_mismatch` / `child_ownership_mismatch:<service>`），只停自己拉起的进程，不会误杀手工启动的同名服务。

**单独启动的内核 node 进程**（Windows）：

```powershell
netstat -ano | findstr :8790      # 拿 LISTENING 行末列的 PID
taskkill.exe /F /T /PID <pid>     # /T 连子进程树一起终止
```

## 2. 内核 HTTP 面

路由白名单 `ALLOWED_ROUTES` 定义在 [`apps/personal_intelligence_kernel/src/server.mjs`](../../apps/personal_intelligence_kernel/src/server.mjs)；未登记路径返回 404 `route_not_found`，登记路径用错方法返回 405 `method_not_allowed`。错误响应统一为 `{"ok":false,"error":{"code":"<safe_code>"}}`。

### 2.1 `GET /health` 与 `GET /ready`

- `/health`：存活探针，恒 200，返回 host/port 与累计 `provider_calls`。
- `/ready`：就绪断言，返回 `checks`（全部通过才 200，否则 503）：
  - `package_decision`：决策文件 accepted 且未过期；
  - `resource_registry`：资源策略为空集 + 工具集与 Capability Registry 完全一致；
  - `schema_migration`：事件账本 schema 为 `pi_kernel_events_v1`；
  - `sqlite_integrity`：事件账本 `PRAGMA integrity_check` 为 ok。

### 2.2 `POST /v1/tasks`

```json
{
  "task_id": "pi_task_demo_001",
  "session_id": "pi_session_demo_001",
  "idempotency_key": "pi-idem-demo-001",
  "purpose": "structured_analysis",
  "prompt": "……",
  "include_response": true
}
```

- `idempotency_key` 必填（缺失报 `task_identity_invalid`）；`task_id` / `session_id` 建议显式提供，缺省时由 `idempotency_key` 的 sha256 派生（`pi_task_…` / `pi_session_…`）。Python 适配器总是显式提供三者。
- `purpose` 决定模型与预算路由：`structured_analysis`（1024）、`guarded_generation`（2048）、`extraction_summary`（1024）、`generic_generation`（4096）、`conversation_summary`（4096）、`memory_candidate_extraction`（4096）、`memory_repair`（4096，单位 max_output_tokens）。route 的 `model` 来自 `var/config/pi-provider.json` 的 `model`（或 `PI_PROVIDER_MODEL` 覆盖）；未知 purpose 报 `model_route_unknown`。
- `prompt` 必须非空且 ≤ 48 KB，否则 `task_prompt_invalid`；请求体整体 ≤ 64 KB（超限 `event_too_large`）。
- `include_response: true` 需要内部能力头 `X-PI-Internal-Capability`，否则 `internal_capability_invalid`。
- 返回：新任务 201、幂等重放 200；`receipt` 内含 `response_checksum`、token 用量与 provider/model/cost 元数据。prompt 明文只在内存，不落任何账本。

### 2.3 `POST /v1/conversations/turn`

一次模型自主调工具的真实对话轮：请求必须带 `skill_id`（技能清单中的技能，如 `knowledge.research`）与 `prompt`，加 `task_id` / `session_id` / `idempotency_key`。可选 `history_turns`（显式历史数组）或 `enable_history`（按 `PI_CONVERSATION_HISTORY_TURNS` 的轮数上限拉取规范化历史，默认 8、上限 20）。返回 `turn.state`（`settled` / `cancelled` / `outcome_unknown` / 失败）。幂等重放返回 `turn: null`（该路径不持久化响应报告）。

### 2.4 `/v1/operations` 五条路由

| 路由 | 语义 |
|---|---|
| `GET /v1/operations` | 列出运行时操作登记 |
| `GET /v1/operations/:operation_id` | 查询单个（不存在 404 `operation_not_found`） |
| `POST /v1/operations/:operation_id/cancel` | 请求取消（幂等，同键重放返回上次结果） |
| `POST /v1/operations/:operation_id/resume` | 恢复；`outcome_unknown` 态拒绝并要求先 reconcile（`reconcile_before_resume`） |
| `POST /v1/operations/:operation_id/reconcile` | 仅能收敛 `outcome_unknown` 操作（否则 `reconcile_state_required`）；不带 receipt/fingerprint 证据时转 `manual_review` |

这五条路由已登记进 `ALLOWED_ROUTES`，并有契约断言守住：`apps/personal_intelligence_kernel/test/server.test.mjs` 中 `ALLOWED_ROUTES declares the operations control-plane routes it dispatches` 逐条断言五条路由都在白名单内。

### 2.5 其余路由（简表）

`GET /v1/tasks`、`GET /v1/tasks/:task_id`、`POST /v1/tasks/:task_id/{cancel,resume}`、`POST /v1/conversations/{session,cancel,resume,reconcile}`、`GET /v1/skills`、`POST /v1/events`、`GET /v1/events/stream`（SSE）、`POST /internal/v1/candidates` 与 `POST /internal/v1/conversation-deltas`（需能力头）、`POST /v1/candidates/review`、`GET /v1/personal/model-projection`、`POST /v1/proactive/{state,controls,dismiss,undo}`。最后四组固定路由在 KernelHost 内做字段白名单校验，声明外字段一律 `undeclared_input`。

## 3. 持久化账本

内核在 `<project-root>/var/db/` 下维护四个 SQLite（`var/**` 为本机私有数据，不入库）：

| 文件 | 写入方 | 内容 |
|---|---|---|
| `pi_kernel_tasks.sqlite` | `tasks/ledger.mjs` | 任务账本 + 响应报告表 |
| `pi_kernel_sessions.sqlite` | `sessions/store.mjs` | 会话轨迹（仅元数据，字段含 prompt/body 类键直接拒绝写入） |
| `pi_kernel_events.sqlite` | `events/journal.mjs` | 追加式事件账本（`pi_kernel_events_v1`） |
| `pi_kernel_candidates.sqlite` | `candidates/store.mjs` | 候选暂存元数据 |

**任务账本**（`apps/personal_intelligence_kernel/src/tasks/ledger.mjs`）：

- 迁移 `001_pi_kernel_tasks_v1` 建 `pi_kernel_tasks`（状态机 `queued → claimed → running → succeeded/failed/cancel_requested/outcome_unknown`，迁移 checksum 不符即 `migration_checksum_mismatch`）、`pi_kernel_task_outbox` 与 `pi_kernel_migrations`。
- 迁移 `002_pi_kernel_task_responses_v1` 增设 `pi_kernel_task_responses`（task_id 主键、response_json、response_checksum），承接 `include_response` 重放。
- 响应体 **1 MB 有界**：序列化超过 `MAX_RESPONSE_BYTES = 1024*1024` 时不持久化（`{stored:false, reason:"response_too_large"}`），账本无界增长被排除；代价是这类任务的重放 fail-closed（见下）。
- 认领带租约（默认 30 s，实际用 route/skill 超时 + 5 s）；乐观版本号 `stale_version` 守护并发转移。

**重启后幂等重放语义**：任务以 `idempotency_key` 唯一索引落账。重启后重发同一 `POST /v1/tasks`（同键同输入）命中 `duplicate: true`；若带 `include_response: true` 且原任务成功时响应 ≤ 1 MB，内核直接从 `pi_kernel_task_responses` 读回持久响应返回——不需要重新调 provider。该语义有回归测试：`test/task-response-replay.test.mjs`（"task include_response replay is served from the persisted ledger across a host restart"）。差异：

- 任务路由（provider 报告）：无持久响应时报 `provider_response_unavailable`；
- 技能路由（`pi_skill_report_v1` 报告）：无持久报告时报 `skill_response_unavailable`；
- 对话轮路由：重放只返回任务态，`turn: null`，不提供响应重放。

## 4. 故障排查

| 错误码 | 触发场景 | 处置 |
|---|---|---|
| `host_bind_failed` | 内核监听 `--port`/`PI_KERNEL_PORT` 失败（典型为端口被占用） | `netstat -ano \| findstr :8790` 找占用者；停止旧进程或改 `-KernelPort`/`--port` |
| `unhealthy_port_conflict:<svc>:<port>` | 监督脚本发现端口被监听但健康端点不通 | 杀掉占位的僵尸进程后重跑；或用健康的那套服务（`service_reused` 会自动收养） |
| `startup_readiness_failed:<svc>` | 子进程在 `-StartTimeoutSeconds`（默认 30）内未就绪 | 看 `ops/logs/agent-stack.jsonl` 的 `config_loaded`/`preflight_failed` 条目定位 |
| `package_decision_missing` / `package_decision_not_accepted` / `package_decision_expired` | 决策文件 `governance/manifests/ai/pi-package-decision.json` 缺失、状态非 accepted 或 `expiry` 已过（撰写时该文件 expiry 为 2026-09-03，过期会随时间轮换） | 按 governance 流程重新生成/续期决策文件后重启；不要手工改 run_id（`piq_f7896e839999ed2eac87ebd4`） |
| `provider_response_unavailable` | `POST /v1/tasks` 幂等重放且 `include_response: true`，但无持久响应：旧版内核（002 迁移前）写下的任务重启后重放，或响应 > 1 MB 被 002 的有界存储拒收（fail-closed） | 预期内的安全失败：换新的 `idempotency_key` 重新发起任务即可；不要为"找回"大响应而放宽 1 MB 上限 |
| `skill_response_unavailable` | 同上，技能任务报告无持久化 | 同上 |
| `model_route_unknown` | Python 侧 `PiKernelProvider` 的 `purpose` 不在 `_MAX_OUTPUT` 七用途内；或 Kernel 侧 `purpose` 不在 route 表（两者口径一致）。另：显式传的 `model` 与 route 的 `model` 不一致也抛同名错误 | 改用上表七个 purpose 之一；`var/config/pi-provider.json` 改 `model` 后重启内核生效 |
| `undeclared_input` / `binding_required` / `idempotency_key_required` | 固定路由（review/projection/proactive）或域网关工具调用的绑定三元组不全：内核注入三元组为 `task_id` + `idempotency_key`（`<idemKey>:<toolCallId>`）+ `binding`（`pi_kernel_conversation_turn` / `pi_kernel_skill`），声明外字段/缺 binding 即失败 | 客户端代码不要自带 binding 字段交给模型；对话轮内网关报 `undeclared_input` 时内核会自动用纯三元组重试一次，无需人工干预 |
| `internal_capability_invalid` | `include_response` / `/internal` 路由的 `X-PI-Internal-Capability` 头缺失或与 `PI_KERNEL_INTERNAL_CAPABILITY` 不一致 | 确认调用方与内核进程拿到同一能力值；监督脚本场景两者由脚本注入同值，手工双端启动时须自行对齐 |
| `non_loopback_bind` / `invalid_port` | 试图绑定非 127.0.0.1，或端口不在 1–65535 | 内核设计上仅 loopback；外部访问走 Tunnel |
| `task_identity_invalid` / `task_prompt_invalid` / `event_too_large` | 标识符不符合 `[A-Za-z0-9][…]{0,255}`；prompt 空或 > 48 KB；请求体 > 64 KB | 修正请求体 |
| `task_busy` / `stale_version` / `task_not_resumable` / `reconcile_not_required` | 任务被活跃租约持有；expected_version 过期；对非 `outcome_unknown` 任务 reconcile | 读取 `GET /v1/tasks/:task_id` 以账本当前 version/state 为准再操作；租约到期后可重新 claim |
| `provider_timeout` / `provider_transport_error` | 上游 provider 超时/传输失败，任务转 `outcome_unknown` | 用 `POST /v1/tasks/:task_id/resume`（内部走 reconcile，需显式 `state: succeeded/failed` + `expected_version`）或 `/v1/conversations/{resume,reconcile}` 以显式终态收敛；内核从不隐式重试 |
| `provider_mode_unknown` / `provider_credential_missing` / `provider_transport_missing` | `var/config/pi-provider.json` 的 mode 不在白名单，或实时模式缺凭据/transport | 修正配置或回落 `PI_KERNEL_PROVIDER_MODE=replay`；配置字段校验规则见 [configuration/overview.md](../configuration/overview.md) |

错误码全集见 `server.mjs` 的 `SAFE_ERROR_CODES`；不在白名单的内部异常统一折叠为 `internal_error`（400）。

## 5. 与 Python 侧契约

Python 侧经由 [`src/personal_knowledge/core/providers.py`](../../src/personal_knowledge/core/providers.py) 的 `PiKernelProvider` 访问内核：

- **端点**：`POST {PI_KERNEL_URL|http://127.0.0.1:8790}/v1/tasks`；base_url 必须是 loopback http（否则 `provider_endpoint_invalid`）。
- **能力头**：`X-PI-Internal-Capability`，取自 `PI_KERNEL_INTERNAL_CAPABILITY`；缺失报 `provider_internal_capability_missing`（fail-closed）。
- **确定性幂等键**：`pi-idem-py-{purpose}-{request_checksum 前 40 位}`，其中 `request_checksum = sha256(规范化 {purpose, messages, temperature, max_tokens})`；task_id / session_id 同理派生（`pi_task_py_…` / `pi_session_py_…`）。同一逻辑请求 → 同一键 → 命中内核账本幂等重放。
- **请求体**：恒带 `include_response: true`，从 `response` + `receipt` 字段还原 `ProviderResult`（payload/checksum/telemetry）；HTTP 错误时透传内核 `error.code`，`provider_timeout` / `provider_transport_error` 归一为可重试的 `ProviderTimeout`。
- **候选暂存**：`stage_candidate()` 调 `POST /internal/v1/candidates`（同一能力头），依赖上一次 `generate()` 的 task/session/receipt，缺失报 `provider_receipt_missing`。

Python 侧用途白名单 `_MAX_OUTPUT`（七 purpose）与 Kernel route 表口径一致；`purpose` 不在其中在发请求前就报 `model_route_unknown`，不会打到内核。

入口门禁在 [`src/personal_knowledge/core/llm.py`](../../src/personal_knowledge/core/llm.py) 的 `make_llm_client`：

- `PI_KERNEL_LEGACY_MODE=1` → legacy OpenAI 兼容客户端（显式回滚专用）；
- `PI_KERNEL_AI_WORKFLOW=1` **或** `PI_KERNEL_INTERNAL_CAPABILITY` 已设置 → 返回由 `PiKernelProvider` 支撑的 OpenAI 兼容 facade（每个 completion 一个 Pi task）;
- 两者都缺 → 直接 `sys.exit("[error] Pi Kernel 未启动或缺少内部能力；请先启动 agent stack")`。

即：经监督脚本启动的 REST 子进程（被注入 `PI_KERNEL_AI_WORKFLOW=1` 与能力值）会自动走内核；绕过脚本单独跑 Python 进程时，至少要自己设置其中之一，且能力值与内核一致。

## 6. 日常验证与巡检

```powershell
# 内核单元/契约测试（含 ALLOWED_ROUTES 契约断言与重启重放测试）
cd apps\personal_intelligence_kernel
node --test test/*.test.mjs

# 全栈健康探测（栈已在跑时）
pwsh -File .\ops\runtime\start-agent-stack.ps1 -Mode Probe -SkipTunnel

# MCP/REST 冒烟
python ops\runtime\smoke-agent-stack.py --snapshot <snapshot.json> --out <out.json>
```

巡检要点：`GET /ready` 的四个 checks 全绿；`ops/state/agent-stack.json` 中各服务 `healthy: true`；`var/db/pi_kernel_tasks.sqlite` 用 `sqlite3` 抽查 `pi_kernel_migrations` 两条记录（001/002）在位、`pi_kernel_tasks` 无长期滞留 `running` 的任务（有则按第 4 节 `outcome_unknown` 流程收敛）。
