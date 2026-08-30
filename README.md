<!-- generated-by: gsd-doc-writer -->

# 数据分析（Personal Knowledge System）

本地、隐私优先的个人知识 / 决策智能系统：把本机对话与活动数据归一为带出处的规范记录，
蒸馏出经评测把关的知识单元（KU），并通过 CLI、REST、MCP 和 Pi Kernel 提供检索与智能服务。
这是**本地个人项目**——不是开源库，也不发布 PyPI / npm 包。

仓库：`https://github.com/adlink8/personal-data-analysis-system`

## 环境要求

| 依赖 | 版本 | 说明 |
|------|------|------|
| Windows + PowerShell | 7+ | 启动脚本以 Windows 为主环境（`#requires -Version 7.0`） |
| Python | ≥ 3.11（CI 验证 3.12 与 3.14） | `pyproject.toml` |
| Node.js | Kernel / Desktop ≥ 22.19.0；ChatGPT MCP 应用 ≥ 20 | 各 `apps/*/package.json` engines |

## 安装

```powershell
git clone https://github.com/adlink8/personal-data-analysis-system.git
cd personal-data-analysis-system

python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt   # 含 constraints.txt 锁定的运行 + 测试依赖
python -m pip install -e .                      # 提供 pk-sync / pk-ku / rag-search 等 CLI
```

Node 依赖按应用目录独立安装（仅当运行或修改对应应用时需要），例如：

```powershell
cd apps\personal_intelligence_kernel; npm ci
```

仓库不自动加载 `.env`；需要覆盖配置时在启动前设置环境变量（见配置参考）。

## 快速开始

```powershell
# 1) 只读自检：不需要私有数据、运行服务或 LLM 凭据
pk-ku workflow

# 2) 一键启动本地服务栈（默认不带 Tunnel；需 pwsh 7）
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -SkipTunnel

# 3) 健康检查
curl.exe --noproxy "*" http://127.0.0.1:8000/health
curl.exe --noproxy "*" http://127.0.0.1:8790/ready
curl.exe --noproxy "*" http://127.0.0.1:8789/health

# 4) 运行测试
python -m pytest -q
```

服务栈由 `ops/runtime/start-agent-stack.ps1` 监督（支持 `-Mode Run/Check/Probe/Stop/Status`）：

| 服务 | 端口 | 健康检查 | 进程 |
|------|------|----------|------|
| REST API | 8000 | `/health` | `python -m personal_knowledge.services.api_server` |
| Pi Kernel | 8790 | `/ready` | `node apps/personal_intelligence_kernel/src/server.mjs` |
| GPT Apps MCP | 8789 | `/health` | `node apps/personal_data_chatgpt/server.mjs` |
| Tunnel（可选，接 ChatGPT） | 8081 | `/readyz` | `tunnel-client.exe`（需 `CONTROL_PLANE_API_KEY`） |

不带 Tunnel 时使用 `-SkipTunnel`；`apps/personal_data_chatgpt/scripts/启动服务.bat` 是同一
实现的双击入口（薄包装）。

## 使用示例

预览本地新对话（dry-run，不写入；确认后加 `--write` 发布对话 SSOT）：

```bash
pk-sync conversations
```

检查知识单元增量（只读，无 LLM 调用、无写入）：

```bash
pk-ku inspect
```

以 JSON 输出当前生效知识索引的检索统计：

```bash
rag-search stats --json
```

> `rag-pipeline` 已退役（exit 2）；日常流程一律走 `pk-sync` / `pk-ku`。

## 测试

```powershell
python -m pytest -q                                  # 全部可离线运行
python -m pytest -m "not live" -q                    # CI 离线子集（live 标记需本地私有数据）
python -m personal_knowledge.governance.preflight --ci
cd apps\personal_data_chatgpt; npm test              # node --test；cockpit 为 Vitest
```

## 文档索引

| 文档 | 内容 |
|------|------|
| [架构总览](docs/architecture/overview.md) | 分层架构、权威边界与组件图 |
| [语义知识管线](docs/architecture/semantic-knowledge-pipeline.md) | 语义知识生产链路（生成中） |
| [快速上手](docs/guides/getting-started.md) | 安装、隔离环境与首次运行 |
| [开发指南](docs/guides/development.md) | 环境、构建命令与开发约定 |
| [测试指南](docs/testing/overview.md) | pytest / node:test / Vitest 全量说明 |
| [配置参考](docs/configuration/overview.md) | 环境变量、配置文件与优先级 |
| [Pi Kernel 运维手册](docs/runbooks/pi-kernel.md) | 内核服务运维（生成中） |
| [Agent 操作手册](docs/AGENTS.md) | AI / 人类操作者的完整产品流程 |
| [对话同步 runbook](docs/runbooks/product-sync.md) | `pk-sync conversations` 详解 |
| [KU 增量 runbook](docs/runbooks/ku-incremental.md) | 知识单元增量抽取流程 |

## 许可说明

本项目为私有个人项目，未附带 LICENSE，不授权公开分发。生产数据私有：`data/`、`var/`
下的数据库、原始导出、运行报告与凭据一律不得提交到 Git。
