<!-- generated-by: gsd-doc-writer -->
# 配置参考

本项目主要通过进程环境变量和仓库内 JSON 配置文件进行配置。仓库没有 `.env.example`、`.env.development`、`.env.test` 或 `.env.production`，代码也没有发现自动加载 `.env` 文件的逻辑；在 Windows 上应在启动进程前通过 PowerShell 设置变量。路径常量统一由 [`project_paths.py`](../../src/personal_knowledge/core/project_paths.py) 从源码位置推导，不依赖当前工作目录。

## 环境变量

表中的“必需”指缺失时会使对应启动或功能失败，而不是所有命令都必须设置。凭据值不得写入本文档、提交到仓库或输出到日志。

### 本地服务栈

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `CONTROL_PLANE_API_KEY` | 启用 Tunnel 时必需 | 无 | `start-agent-stack.ps1` 的预检项；缺失时报 `CONTROL_PLANE_API_KEY_missing`。使用 `-SkipTunnel` 时不检查。 |
| `HOST` | 否 | `127.0.0.1` | ChatGPT MCP HTTP 服务监听地址。 |
| `PORT` | 否 | `8789` | ChatGPT MCP HTTP 服务端口；监督脚本会按 `-McpPort` 注入。 |
| `PERSONAL_DATA_REST_URL` | 否 | `http://127.0.0.1:8000` | MCP 调用的 REST 基础地址；监督脚本根据 `-RestPort` 注入。 |
| `PERSONAL_DATA_MCP_PROFILE` | 否 | `core` | MCP 工具档位；`full` 启用完整工具集，其他值归一为 `core`。 |
| `PERSONAL_DATA_ORCHESTRATION_SECRET` | 编排确认操作时必需 | 无 | REST 编排确认用 HMAC 材料。监督脚本每次运行在内存中随机生成并只传给 REST 子进程。 |
| `PI_KERNEL_INTERNAL_CAPABILITY` | 内部 Kernel 路由和 AI 工作流时必需 | 无 | 监督脚本每次运行在内存中随机生成，并同时传给 REST 与 PI Kernel。 |
| `PI_KERNEL_AI_WORKFLOW` | 否 | 未设置 | `1` 表示 Python LLM 兼容层走 PI Kernel；监督脚本为 REST 子进程设置为 `1`。 |
| `PI_KERNEL_URL` | 否 | `http://127.0.0.1:8790` | Python REST/Provider 调用 PI Kernel 的基础地址；监督脚本按 `-KernelPort` 注入。 |
| `PI_KERNEL_HOST` | 否 | `127.0.0.1` | PI Kernel 监听地址。 |
| `PI_KERNEL_PORT` | 否 | `8790` | PI Kernel 监听端口；也供同步代码构造 Kernel URL。 |
| `PI_KERNEL_SHUTDOWN_TIMEOUT_MS` | 否 | `1000` | Kernel CLI 关闭等待时间，单位毫秒。 |
| `PI_DOMAIN_HOST` | 否 | `127.0.0.1` | PI Kernel 访问 Python domain gateway 的地址。 |
| `PI_DOMAIN_PORT` | 否 | `8000` | PI Kernel 访问 Python domain gateway 的端口。 |
| `PI_DOMAIN_CAPABILITY` | 否 | 内置本地开发能力值 | Domain gateway 请求能力材料。不要把该值当作可公开的认证凭据。 |
| `PI_CONVERSATION_HISTORY_TURNS` | 否 | `0`（关闭） | 大于 `0` 时启用有界会话历史；默认启用时使用 8 轮，代码上限为 20 轮。 |
| `PK_COCKPIT_DEV_ORIGINS` | 否 | 空 | 逗号分隔的额外 Cockpit 开发 Origin。内置允许 `http://127.0.0.1:5173` 与 `http://localhost:5173`。 |

`start-agent-stack.ps1` 还读取 Windows 提供的 `USERPROFILE` 和 `APPDATA`，用于定位 Tunnel 可执行文件目录与 profile；Vertex 的批处理启动路径会读取系统 `ComSpec`。这些变量由操作系统提供，不是项目配置。脚本为 Tunnel 子进程设置 `NO_PROXY=127.0.0.1,localhost`，并仅在传入 `-TunnelProxy` 时设置 `HTTP_PROXY` 和 `HTTPS_PROXY`。

### 模型提供商与预算

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `PI_PROVIDER_MODE` | 否 | `replay` | Provider 模式；代码接受 replay、DashScope/Aliyun、OpenAI-compatible 和 Vertex Google 路径。 |
| `PI_KERNEL_PROVIDER_MODE` | 否 | 未设置 | Kernel host 的 provider-mode 覆盖；未设置时由 provider 配置链最终回落到 `replay`。 |
| `PI_PROVIDER_MODEL` | 否 | 随 provider 模式选择 | 覆盖实时 provider 模型名。 |
| `PI_PROVIDER_BASE_URL` | 实时 OpenAI-compatible 配置可能必需 | DashScope 默认 `https://dashscope.aliyuncs.com/compatible-mode/v1` | 覆盖实时 provider 基础 URL；自定义 OpenAI-compatible provider 应显式设置。 |
| `PI_PROVIDER_CONFIG` | 否 | `var/config/pi-provider.json` | 本地 provider JSON 路径。文件缺失、JSON 无效或 schema 不匹配时按空配置处理。 |
| `PI_MODEL_ROUTES_MANIFEST` | 否 | `governance/manifests/ai/pi-model-routes.json` | 按用途定义模型预算的 manifest 路径。 |
| `PI_PROVIDER_COST_CEILING` | 否 | provider 配置值，否则 `0` | 全局调用成本上限；无效负值回落为 `0`。 |
| `PI_PROVIDER_MAX_TEMPERATURE` | 否 | `0.3` | Python provider 温度上限；必须为非负数。 |
| `PI_PROVIDER_MAX_OUTPUT_TOKENS` | 否 | `4096` | Python 与 Kernel route 的全局输出 token 上限覆盖；必须大于等于 1。 |
| `PI_PROVIDER_TIMEOUT_SECONDS` | 否 | `120` | Python provider 超时上限，单位秒；必须大于等于 `0.1`。 |
| `PI_PROVIDER_MAX_ATTEMPTS` | 否 | route 配置，否则 `1` | Kernel route 全局重试次数覆盖；有效范围为 1–3。 |
| `PI_PROVIDER_NO_FALLBACK` | 否 | route 配置 | Kernel route 的全局禁止 fallback 开关，接受 `1/true` 或 `0/false`。 |
| `PI_BUDGET_CONFIG` | 否 | `governance/config/pi-budget.json` | Python provider/analysis 预算 JSON 路径；缺失或无效时使用内置默认值。 |
| `PI_ANALYSIS_MAX_ATTEMPTS` | 否 | `2` | 决策分析最大尝试次数，有效范围为 1–3。 |
| `PI_ANALYSIS_TEMPERATURE_MAX` | 否 | `0.3` | 决策分析温度上限，必须为非负数。 |
| `PI_ANALYSIS_MAX_OUTPUT_TOKENS` | 否 | `4096` | 决策分析输出 token 上限，必须大于等于 1。 |
| `DASHSCOPE_API_KEY` | DashScope/Aliyun 模式必需 | 无 | DashScope 凭据；也可从受保护的本地 provider 配置读取。 |
| `OPENCODE_API_KEY` | 实时会话 provider 条件必需 | provider 配置中的凭据 | 会话运行时使用的 provider 凭据。 |
| `PERSONAL_DATA_GCLOUD` | Vertex 且 `gcloud` 不在 `PATH` 时必需 | 自动发现 `gcloud` | `gcloud` 可执行文件路径。 |
| `PERSONAL_DATA_GCP_PROJECT` | Vertex 时必需 | `project-c5cbd608-1b00-454e-80f` | Vertex Google Cloud 项目。部署时应显式设置，避免依赖开发机默认值。 |
| `PERSONAL_DATA_VERTEX_LOCATION` | 否 | `global` | Vertex 区域。 |
| `PERSONAL_DATA_VERTEX_MODEL` | 否 | `gemini-3.5-flash-lite` | Python Vertex 默认模型；Kernel route 在 Vertex 模式下也读取它。 |
| `CLOUDSDK_ROOT_DIR` | 否 | 无 | 可选 Google Cloud SDK 根目录。取 token 时子进程还会固定设置 `CLOUDSDK_CORE_DISABLE_PROMPTS=1`。 |
| `OPENAI_API_KEY` | 仅 legacy OpenAI 或评测路径条件必需 | 无 | Legacy OpenAI、memory 分析和可选 LLM judge 使用的凭据。 |
| `MEM0_API_KEY` | 否 | 无 | `OPENAI_API_KEY` 的 legacy/memory fallback。 |
| `OPENAI_BASE_URL` | 否 | `https://token-plan-cn.xiaomimimo.com/v1` | Legacy OpenAI-compatible 基础 URL。 |
| `OPENAI_MODEL` | 否 | 随命令回落 | Memory/KU 评测模型覆盖。 |
| `MEM0_LLM_MODEL` | 否 | 命令相关，常见回落为 `gpt-4o-mini` 或 `gpt-5.4` | Memory 与评测脚本模型覆盖。 |
| `EVAL_JUDGE_MODEL` | 否 | `MEM0_LLM_MODEL` 的解析值 | 对话评测 judge 模型。 |
| `HTTP_PROXY` / `HTTPS_PROXY` | 否 | 无 | Legacy OpenAI、Vertex 和 Tunnel 的出站代理。REST/MCP 本地通信不应经代理。 |

真实 provider 模式还要求外部身份认证或凭据可用；仓库只能验证变量名和加载顺序，不能验证部署账号、配额或外部服务可用性。<!-- VERIFY: 实际部署所使用的 provider 账号、配额与外部端点可用性 -->

### 检索、向量与隐私

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `PERSONAL_DATA_EMBED_MODEL_PATH` | 自动发现失败时必需 | 扫描本机约定缓存目录 | `bge-small-zh-v1.5` 本地模型目录；无法找到时抛出 `Local embedding model not configured`。 |
| `SENTENCE_TRANSFORMERS_HOME` | 否 | 无 | 本地模型缓存根目录；代码会在其下查找 `bge-small-zh-v1.5`。 |
| `PERSONAL_DATA_EMBED_DEVICE` | 否 | 通常为 `cuda`；MCP 进程设为 `cpu` | Sentence Transformers 设备；GPU 加载失败时回退 CPU。 |
| `TRANSFORMERS_OFFLINE` | 否 | `1` | 本地 embedding 模块通过 `setdefault` 禁止 Transformers 在线检查。 |
| `HF_HUB_OFFLINE` | 否 | `1` | 本地 embedding 模块通过 `setdefault` 禁止 Hugging Face Hub 在线检查。 |
| `PERSONAL_DATA_SEMANTIC_API` | 否 | `http://127.0.0.1:8000/search/semantic` | 语义检索 API URL。 |
| `PERSONAL_DATA_FALLBACK_POLICY` | 否 | `layered` | 混合检索 fallback 策略；有效值为 `layered` 或 `legacy`，非法值回落到 `layered`。 |
| `PERSONAL_DATA_ALLOW_LEGACY_PAD` | 否 | `true` | 是否允许 layered 模式用 legacy 数据补足结果；接受 `1/true/yes/on`。 |
| `PERSONAL_DATA_PRIVACY_GUARD` | 否 | `1` | 出站隐私防护开关；`0/false/no/off` 关闭。 |
| `PERSONAL_DATA_PRIVACY_MODE` | 否 | `redact` | `redact` 或 `encrypt`；非法值回落到 `redact`。 |
| `PERSONAL_DATA_PRIVACY_SCOPE` | 否 | `credentials,pii,fields` | 逗号分隔的扫描范围；支持 `credentials`、`pii`、`fields`。 |
| `PERSONAL_DATA_PRIVACY_SEAL_KEY` | 生产 encrypt 模式应设置 | 内置开发盐 | HMAC/Fernet 密钥材料。不要依赖开发默认值，也不要提交实际值。 |

### 受控兼容、取证与测试变量

这些变量不是日常产品配置。开启兼容或强制开关会绕过正常产品保护，只应按对应 runbook 使用。

| 变量 | 必需 | 默认值 | 说明 |
|---|---|---|---|
| `PI_KERNEL_LEGACY_MODE` | 否 | 未设置 | `1` 才允许 legacy OpenAI 回滚路径。 |
| `PK_ALLOW_LEGACY_PIPELINE` | 否 | 未设置 | `1/true/yes/on` 才允许退役 pipeline 的取证入口。 |
| `PK_KU_ALLOW_FULL_INVENTORY_START` | 否 | 未设置 | `1` 才允许从全量 inventory 启动 KU 生产抽取。 |
| `PK_KU_ALLOW_NON_INCREMENTAL_RUN` | 否 | 未设置 | `1/true/yes/on` 才允许强制非增量 KU run。 |
| `PK_KU_DOCTOR_JSON_SIDE` | 否 | 未设置 | `1` 时输出 doctor 的附加 JSON。 |
| `PI_DOMAIN_TEST_LEDGER_PATH` | 否 | 无 | 测试专用 ledger 路径覆盖。 |
| `PI_CONTAINMENT_FIXTURE_SECRET` | 否 | 测试临时值 | containment probe 测试夹具变量，不应在产品环境设置。 |
| `PERSONAL_API` | 否 | `http://127.0.0.1:8000` | `tools/forensics/examples/rag_inject.py` 的 REST 基础地址，仅用于取证示例脚本。 |

## 配置文件格式

### Provider 与分析预算

[`governance/config/pi-budget.json`](../../governance/config/pi-budget.json) 使用 `pi-budget-config-v1` schema。环境变量优先于文件；文件缺失、无效或数值越界时使用内置默认值。

```json
{
  "schema": "pi-budget-config-v1",
  "provider": {
    "max_temperature": 0.3,
    "max_output_tokens": 4096,
    "timeout_seconds": 120
  },
  "analysis": {
    "max_attempts": 2,
    "temperature_max": 0.3,
    "max_output_tokens": 4096
  }
}
```

### PI provider 本地配置

默认路径是 `var/config/pi-provider.json`，schema 必须是 `pi-provider-config-v1`。`provider` 接受 `dashscope` 或 `openai-compatible`；`mode`、`model`、成本字段和 route override 会逐项校验。下面是无外部调用的最小示例：

```json
{
  "schema": "pi-provider-config-v1",
  "provider": "dashscope",
  "mode": "replay",
  "model": "replay-v1",
  "cost_ceiling": 0,
  "input_price_per_million": 0,
  "output_price_per_million": 0,
  "currency": "CNY"
}
```

可选顶层键包括 `base_url`、`secret_path`、`max_output_tokens`、`max_attempts`、`no_fallback`、`timeout_ms` 和 `routes`。代码也能读取 `api_key`，但明文凭据不应写入可提交文件；优先使用进程环境变量或 Windows DPAPI 保护的本地 secret 文件。`var/` 下配置与 secret 均应保持为本机私有内容。

### 模型路由 manifest

[`governance/manifests/ai/pi-model-routes.json`](../../governance/manifests/ai/pi-model-routes.json) 使用 `pi-model-routes-v1` schema。每个 `routes` 条目以 `purpose` 为键，并定义 `timeout_ms`、输入/输出 token 限额、成本上限、最大尝试次数和 fallback 策略。解析优先级为：全局环境变量 → `pi-provider.json` 的 route override → provider 全局配置 → manifest → 代码内最后默认值。

## 必需与可选设置

- 标准本地栈启用 Tunnel 时，`CONTROL_PLANE_API_KEY` 是唯一由 `start-agent-stack.ps1` 直接判定为缺失并终止预检的环境变量。Tunnel 可执行文件和 profile 也是必需依赖，但通过脚本参数和文件路径配置，不是环境变量。
- 监督脚本自动生成 `PERSONAL_DATA_ORCHESTRATION_SECRET` 与 `PI_KERNEL_INTERNAL_CAPABILITY`；使用该脚本启动时不要手工持久化它们。绕过监督脚本单独启动服务时，调用内部/确认路由的操作者必须自行提供一致的值。
- 实时模型模式按 provider 条件要求凭据：DashScope/Aliyun 需要可用的 provider key；Vertex 需要可执行且已认证的 `gcloud`；legacy OpenAI 需要 `OPENAI_API_KEY` 或 `MEM0_API_KEY`。默认 `replay` 模式不需要外部凭据。
- 使用本地向量模型时，若约定模型目录和 `SENTENCE_TRANSFORMERS_HOME` 均无法解析模型，必须设置 `PERSONAL_DATA_EMBED_MODEL_PATH`。
- 其余变量均可选；非法预算值会回落到文件或内置默认值，非法检索/隐私枚举会回落到安全默认值。

## 默认值

默认配置面向仅监听 loopback 的本地运行：REST `8000`、MCP `8789`、PI Kernel `8790`，provider 为 `replay`，检索策略为 `layered`，隐私防护启用且模式为 `redact`。路径默认由项目根派生到 `data/`、`var/` 和 `archive/`；当新布局尚不存在时，部分数据库和报表路径会回落到 legacy `integration/` 路径。

预算值的解析顺序是“环境变量 → JSON 配置 → 内置默认值”。这意味着临时环境覆盖不会修改仓库配置，而无效覆盖也不会使模块导入失败。Provider route 另有更细的配置层级，见上文“模型路由 manifest”。

## 按环境覆盖

项目没有按开发、测试、生产自动切换的配置文件。环境差异由启动进程显式注入，所有覆盖都应在进程启动前完成；修改后需重启对应进程。

```powershell
# 当前 PowerShell 会话内的开发覆盖示例（不包含凭据）
$env:PERSONAL_DATA_EMBED_DEVICE = 'cpu'
$env:PK_COCKPIT_DEV_ORIGINS = 'http://127.0.0.1:5174'
$env:PI_PROVIDER_MODE = 'replay'

pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -SkipTunnel
```

测试应使用测试框架的临时环境覆盖，并在用例结束后恢复变量；不要创建包含真实凭据的 `.env.test`。生产或远程部署的实际 secret 注入方式未在仓库中定义。<!-- VERIFY: 生产环境使用的 secret manager、账号作用域与轮换流程 -->
