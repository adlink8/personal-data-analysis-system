<!-- generated-by: gsd-doc-writer -->
# 快速开始

本指南把 Python 包安装到隔离环境中，验证命令行接口，并一键启动本地服务栈。
初始验证不读取、不修改私有项目数据。

## 前置条件

- Windows + PowerShell **7+**：本地服务监督脚本以 Windows 为主要运行环境（`ops/runtime/start-agent-stack.ps1` 声明 `#requires -Version 7.0`）。
- Python `>=3.11`（`pyproject.toml` 的 `requires-python`）；CI 当前验证 Python `3.12` 和 `3.14`。
- Node.js `>=22.19.0`（`apps/personal_intelligence_kernel/package.json` 的 `engines`，Kernel 应用要求）；ChatGPT MCP 应用（`apps/personal_data_chatgpt`）最低要求 Node.js `>=20`。仅运行或修改对应 Node 应用时需要。
- Git（克隆仓库）与 `pip`（随 Python 附带）。
- 本地 embedding 模型 `bge-small-zh-v1.5`（语义向量检索需要，见下文常见问题）。
- Docker 容器 `novel-mind-chroma-1`（宿主端口 `8001`，仅语义向量检索需要，可选）：本机 Chroma 服务 `127.0.0.1:8001` 的默认端点硬编码在 [`chroma_client.py`](../../src/personal_knowledge/core/chroma_client.py)。该容器借用 novel-mind 项目的 compose，不在本仓库内；不可达时检索自动回退关键词，核心流程不受影响。
- 对话同步需要本地只读的 AgentsView 源库 `%USERPROFILE%/.agentsview/sessions.db`。

初始验证使用默认 replay provider，不需要外部模型凭据。

## 安装步骤

1. 克隆并进入仓库：

   ```powershell
   git clone https://github.com/adlink8/personal-data-analysis-system.git
   cd personal-data-analysis-system
   ```

2. 创建并激活虚拟环境（PowerShell）：

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

3. 安装受约束的开发依赖与可编辑包：

   ```powershell
   python -m pip install -r requirements-dev.txt
   python -m pip install -e .
   ```

`requirements-dev.txt` 包含 `constraints.txt`（版本锁定）、运行时依赖与测试依赖，
并提供 `pk-sync` / `pk-ku` / `rag-search` 等 CLI 入口。仅运行不开发时，可改为
`python -m pip install -c constraints.txt -r requirements.txt` 后再安装可编辑包。

仓库不自动加载 `.env` 文件。需要覆盖配置时，在启动命令前设置进程环境变量；
详见[配置参考](../configuration/overview.md)。

## 首次运行

先做只读自检——不需要私有数据、运行中的服务或 LLM 调用：

```powershell
pk-ku workflow
```

安装正常时会输出编号的增量工作流，以 `pk-sync conversations [--write]` 与
`pk-ku inspect` 开头。

本地服务栈通过 `ops/runtime/start-agent-stack.ps1` 一键启动并监督（默认前台运行，
支持 `-Mode Run/Check/Probe/Stop/Status`）：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -SkipTunnel
```

`-SkipTunnel` 跳过可选的 Tunnel 服务（接 ChatGPT 用，需 `CONTROL_PLANE_API_KEY`
与 tunnel-client.exe）。各服务健康检查：

| 服务 | 端口 | 健康检查 |
|------|------|----------|
| REST API | 8000 | `/health` |
| Pi Kernel | 8790 | `/ready` |
| GPT Apps MCP | 8789 | `/health` |
| Tunnel（可选） | 8081 | `/readyz` |

```powershell
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8790/ready
curl.exe --noproxy "*" http://127.0.0.1:8789/health
```

已配置本地数据时，下一步安全的只读检查是：

```powershell
pk-ku inspect
```

在 review 相关 runbook 与报告的增量之前，不要给同步或生命周期命令加 `--write`。

## 常见问题

### `pk-ku` 未被识别

激活安装时使用的同一虚拟环境，再从仓库根目录重装可编辑包：

```powershell
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
pk-ku workflow
```

### PowerShell 阻止虚拟环境激活

仅对当前 PowerShell 进程放行脚本，然后重新激活：

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

该设置在当前 PowerShell 进程关闭后失效。

### 端口被占用

监督脚本启动每个服务前探测健康端点：端点健康则直接复用已有实例；
端口被其他进程占用且端点不健康时，报 `unhealthy_port_conflict:<service>:<port>`
并退出。脚本自身管理的服务优先用 `-Mode Stop` 停止；残留进程手动定位并结束：

```powershell
netstat -ano | findstr :8000
taskkill.exe /F /T /PID <pid>
```

### 对话或规范数据缺失

仓库不包含生产数据库或原始导出。保持 AgentsView 源库位于
`%USERPROFILE%/.agentsview/sessions.db` 并视为只读。发布前先用
`pk-sync conversations` 做 dry-run 清点；不要创建占位数据库绕过缺源错误。

### 向量检索静默回退关键词（找不到 embedding 模型）

`search_cards` 向量优先、失败静默回退纯 sqlite 关键词打分。模型目录解析顺序
（[`runtime_config.py`](../../src/personal_knowledge/core/runtime_config.py) 的
`embedding_model_path()`）：`PERSONAL_DATA_EMBED_MODEL_PATH` →
`SENTENCE_TRANSFORMERS_HOME/bge-small-zh-v1.5` → 用户目录 `~\models\...` 与
modelscope / huggingface 缓存 → 各盘符根下的 `<X>:\models\bge-small-zh-v1.5`。

若用户目录（通常在 C 盘）残留损坏的 modelscope / huggingface 旧缓存
（`~\.cache\modelscope\hub\models\BAAI\...` 或 `~\.cache\huggingface\hub\models--BAAI--...`），
它们会先于 `D:\models\bge-small-zh-v1.5` 被命中，导致向量路径加载失败并回退关键词。
显式指定模型目录即可修复：

```powershell
$env:PERSONAL_DATA_EMBED_MODEL_PATH = 'D:\models\bge-small-zh-v1.5'
```

路径必须指向本地已存在的 `bge-small-zh-v1.5` 目录。检索代码默认离线
Hugging Face/Transformers 行为，不会在安装时下载模型。

### 内核重启后任务响应无法重放

旧版任务账本不持久化 provider 响应，内核重启后对已完成任务的重复请求
（同一 `idempotency_key` + `include_response`）拿不到原响应。现版本通过迁移
`002_pi_kernel_task_responses_v1` 引入 `pi_kernel_task_responses` 表
（[`ledger.mjs`](../../apps/personal_intelligence_kernel/src/tasks/ledger.mjs)）持久化
任务响应：重启后重放直接返回已存响应，无需重新执行；旧版 v1 账本在内核启动时自动
迁移。单条响应上限 1 MB，超限不持久化，重放按 fail-closed 语义返回
`provider/skill_response_unavailable`。

## Next steps

- 阅读[开发指南](development.md)了解本地构建与贡献流程。
- 阅读[测试指南](../testing/overview.md)了解测试选择与 CI 行为。
- 阅读[语义检索指南](semantic-search.md)（生成中，尚未发布）了解向量检索的使用方式。
- 阅读[语义知识管线](../architecture/semantic-knowledge-pipeline.md)（生成中，尚未发布）
  了解语义知识生产链路。
- 在改动权威边界或数据流之前，先阅读[架构总览](../architecture/overview.md)。
- 启用本地服务、模型 provider 或语义检索时，参考[配置参考](../configuration/overview.md)。
- 写入私有规范数据或知识状态之前，遵循[对话同步 runbook](../runbooks/product-sync.md)
  与 [KU 增量 runbook](../runbooks/ku-incremental.md)。
