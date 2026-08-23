<!-- generated-by: gsd-doc-writer -->
# 开发指南

## Local setup

### 前置条件

- Python `>=3.11`。CI 当前验证 Python `3.12` 和 `3.14`。
- 修改任一 Node 应用时，建议使用 Node.js `>=22.19.0`：Kernel 和 Desktop 明确要求该版本；ChatGPT MCP 应用最低要求 Node.js `>=20`。
- Windows PowerShell。仓库的本地服务监督脚本和桌面密钥保护路径以 Windows 为主要运行环境。
- Git。

### 获取代码

有仓库写权限时可直接克隆；否则先在 GitHub 上 fork，再把下面 URL 替换为 fork URL。

```powershell
git clone https://github.com/adlink8/personal-data-analysis-system.git
cd personal-data-analysis-system
```

### 安装 Python 开发环境

在仓库根目录创建隔离环境，并安装受约束的运行与测试依赖：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

`requirements-dev.txt` 已引用 `constraints.txt` 和 `requirements.txt`。Editable install 提供 `pk-sync`、`pk-ku`、`rag-search`、`rag-api`、`rag-mcp` 与 `rag-dashboard` 命令。

### 安装 Node 应用依赖

只需为正在修改的应用安装依赖。每个应用都有独立的 `package-lock.json`，应在对应目录运行安装命令：

```powershell
cd apps\personal_intelligence_kernel
npm install

cd ..\personal_intelligence_desktop
npm install

cd ..\personal_data_chatgpt
npm install

cd ..\personal_decision_cockpit
npm install
```

### 本地配置与首次检查

仓库没有 `.env.example`，也不会自动加载 `.env` 文件。默认 `replay` provider 不需要外部模型凭据；需要覆盖配置时，在启动进程前设置 PowerShell 环境变量。完整变量和配置优先级见 [`../configuration/overview.md`](../configuration/overview.md)。不要把数据库、原始导出、运行报告、凭据或私有评测样例提交到 Git。

先运行不写数据的检查：

```powershell
python -m pytest -q
python -m personal_knowledge.governance.preflight --ci
pk-ku doctor --skip-ports
pk-ku inspect
```

需要本地 REST、MCP 和 Kernel 服务但不需要 Tunnel 时，可从仓库根目录运行：

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\ops\runtime\start-agent-stack.ps1 -SkipTunnel
```

`%USERPROFILE%\.agentsview\sessions.db` 是受保护的外部只读数据源。开发代码和测试不得移动或写入该数据库。

## Build commands

Python 根项目使用 setuptools，但没有仓库级 build、lint 或 format 脚本。以下命令覆盖当前项目定义的验证命令以及四个 Node 包的全部 `package.json` scripts。

| Command | Description |
|---|---|
| `python -m pytest -q` | Python：按 `pytest.ini` 收集并运行 `tests/` 下的测试。 |
| `python -m personal_knowledge.governance.preflight --ci` | Python：检查治理、路径和架构策略。 |
| `npm --prefix apps/personal_intelligence_kernel test` | Kernel：运行 Node test runner 套件。 |
| `npm --prefix apps/personal_intelligence_kernel run qualify` | Kernel：检查固定 Pi 依赖包资格。 |
| `npm --prefix apps/personal_intelligence_desktop start` | Desktop：启动 Electron 桌面壳；固定本地 Provider 应先可用。 |
| `npm --prefix apps/personal_intelligence_desktop test` | Desktop：运行 main/preload/renderer 契约测试。 |
| `npm --prefix apps/personal_decision_cockpit run dev` | Decision Cockpit：启动 Vite 开发服务器。当前 Python 服务未启用 `/app` 静态托管和 Cockpit 专用投影路由。 |
| `npm --prefix apps/personal_decision_cockpit run build` | Decision Cockpit：清理 `dist/`，执行 TypeScript 检查并构建 Vite 产物。 |
| `npm --prefix apps/personal_decision_cockpit run preview` | Decision Cockpit：本地预览已构建的 Vite 产物。 |
| `npm --prefix apps/personal_decision_cockpit test` | Decision Cockpit：运行 Vitest 测试。 |
| `npm --prefix apps/personal_data_chatgpt start` | ChatGPT MCP：启动本地 HTTP MCP adapter。 |
| `npm --prefix apps/personal_data_chatgpt test` | ChatGPT MCP：运行该包的全部 Node 测试。 |
| `npm --prefix apps/personal_data_chatgpt run test:widgets` | ChatGPT MCP：仅运行 widget 渲染测试。 |
| `npm --prefix apps/personal_data_chatgpt run snapshot:tools` | ChatGPT MCP：校验/输出工具 descriptor snapshot。 |
| `npm --prefix apps/personal_data_chatgpt run snapshot:tools:update` | ChatGPT MCP：更新工具 descriptor snapshot；提交前必须审查生成差异。 |

日常同步使用 `pk-sync conversations`，知识更新使用 `pk-ku` 增量流程。`rag-pipeline` 已退役，不是开发或产品主路径。

## Code style

仓库当前没有 ESLint、Prettier、Biome、Ruff、Black 或 EditorConfig 配置，也没有 `lint`/`format` package script；CI 不执行独立的自动格式检查。因此不存在可声称为权威的自动格式化命令。

提交代码时遵守以下已记录的工程约束：

- 新产品代码从 `personal_knowledge.application.*`、`personal_knowledge.evaluation.*` 或 `personal_knowledge.core.*` 导入；不要新增对兼容层 `personal_knowledge.domains.*` 的依赖。
- 一个模块只承担一个主要变化原因。新增独立状态机、数据权威或权限所有者前先拆分模块。
- 行为、Bug、公共接口、数据转换或安全策略变更先声明公开 seam、可观察行为和不变量，再执行 Red → Green → 定向回归。
- 测试通过公开 seam 观察行为；内部模块优先使用真实实现和临时 SQLite，只在外部 API、模型 Provider、时钟、随机性或必要文件系统边界使用 mock。
- 提交前运行受影响测试、相关回归和 `git diff --check`。详细规则见 [`../architecture/engineering-and-testing-contract.md`](../architecture/engineering-and-testing-contract.md)。

## Branch conventions

默认分支是 `main`，远程 HEAD 也指向 `origin/main`。仓库没有文档化的分支命名规则；现有少量 `codex/...` 分支不足以构成通用约定。创建短生命周期功能分支时应使用团队明确认可的名称，不要从当前仓库推断 `feat/`、`fix/` 或其他前缀为强制格式。

## PR process

仓库目前没有 `CONTRIBUTING.md` 或 Pull Request 模板，因此没有额外的必填清单或提交消息格式。按当前工程和 CI 契约提交变更：

- 从最新 `main` 创建范围单一的分支，避免混入无关重构、格式化或私有运行产物。
- 在 PR 描述中说明公开 seam、用户可观察行为、不变量、修改范围和实际运行的验证命令。
- Bug 修复附上修复前可失败、修复后通过的回归测试；公共接口变更同时覆盖 Provider、Consumer 和一个真实适配器。
- 本地运行受影响的 Python/Node 套件、治理预检和 `git diff --check`。远程 CI 会在 push 和 pull request 上运行 Python `3.12`/`3.14` 全部离线测试与治理预检（`live` 私有数据/服务验收单独执行），并覆盖 ChatGPT MCP、Decision Cockpit、Electron Desktop 和 PI Kernel 的锁定依赖测试；Cockpit 还执行生产构建。
- 确认差异不包含 `data/`、`var/` 私有内容、数据库、凭据、原始 SQL、个人正文或私有评测案例，再请求审查。

评审重点是正确性、权限与隐私边界、数据权威一致性、失败语义、回归风险和测试证据。Kernel 的联网依赖资格检查仍需单独执行并记录结果。
