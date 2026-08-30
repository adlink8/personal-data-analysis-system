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

`pytest.ini` 注册了 `live` 标记（"requires private local data or a running live service; excluded from offline CI"）。远程 CI 用 `python -m pytest -m "not live" -q` 排除它们；本地裸跑 `python -m pytest -q` 会包含这些用例——缺少对应私有产物时由 `skipif` 自动跳过，存在时对真实数据做只读冒烟。

日常同步使用 `pk-sync conversations`，知识更新使用 `pk-ku` 增量流程。`rag-pipeline` 已退役，不是开发或产品主路径。

## 语义层开发须知（tools/semantic/）

2026-08-29 起仓库新增离线语义知识层：管线全貌与规模基线见 [`../architecture/overview.md`](../architecture/overview.md) 的"语义知识层管线"一节。修改 `tools/semantic/` 下脚本时遵守以下约定（均已在脚本头部 docstring 与实现中固化）。

### 工具与读写边界

| 脚本 | 作用 | LLM/内核依赖 | 读 | 写 |
|---|---|---|---|---|
| `mvp_semantic_compress.py` | 会话压缩为 session_cards + ku_facts | pilot/scale 需 pi 内核；`report` 纯只读 | canonical 会话库（`file:...?mode=ro`） | `var/db/semantic_mvp_v3.sqlite` |
| `export_ku_staging.py` | ku_facts → staging 导出 | 无（纯本地） | `semantic_mvp_v3.sqlite` | `var/db/semantic_ku_staging.sqlite` |
| `classify_ku_staging.py` | 九类枚举分类 | 需 pi 内核 | staging 库 | staging 库（仅 `unclassified` 行） |
| `promote_ku_formal.py` | 正式层升格 | 无 | staging 库 | `var/db/personal_system.sqlite`（UNIFIED_DB）、`var/db/semantic_index_registry.json` |
| `dedup_canonical_ku.py` | canonical 层语义收敛 | 无（本地 embedding） | UNIFIED_DB（只读阶段） | UNIFIED_DB 的 `canonical_knowledge_units` + members |
| `build_semantic_vector_store.py` | 向量化 + 构建登记 | 无（本地 embedding） | `semantic_mvp_v3.sqlite` | Chroma collection、`var/db/semantic_index_registry.json` |
| `materialize_wiki.py` | `subject:` 主题 wiki 物化 | 无（纯本地确定性） | UNIFIED_DB、`semantic_mvp_v3.sqlite`（均 `mode=ro`） | `var/db/personal_wiki_projection.sqlite` |

硬边界：

- `data/canonical/` 一律只读。`mvp_semantic_compress.py` 以 `file:...?mode=ro` URI 打开 canonical 会话库；任何脚本不得写 canonical。
- UNIFIED_DB（`var/db/personal_system.sqlite`）只允许 `promote_ku_formal.py` 与 `dedup_canonical_ku.py` 两个脚本写入。promote 刻意不写 canonical 层（由 `dedup_canonical_ku.py` 独占语义收敛，避免升格用精确分组覆盖收敛结果）；dedup 只重写 promote 运行产出的行。
- `materialize_wiki.py` 唯一可写库是可再生的 `var/db/personal_wiki_projection.sqlite`。

### 幂等约定

所有脚本必须可重跑且重跑不产生重复数据：

- 确定性 id：staging 导出 `unit_id = 'stg|' + sha256(fact_key)`；promote 的 `run_id`（内容哈希前缀 `pm_`）与正式 `v1|` unit id 均由 staging 内容派生，与运行时间无关，增量刷新后重跑按同一身份 upsert。
- Upsert 写入：promote 对 `knowledge_build_runs`、`knowledge_units`、`knowledge_unit_evidence`、`knowledge_index_versions`（status='candidate'）用 `insert or replace`；`materialize_wiki.py` 页面行主键 `(topic_id, projection_version)` 唯一并 INSERT OR REPLACE，永不产生同版本重复行。
- 全量重建：`export_ku_staging.py` 在单事务内 DELETE 全量 + 重新 INSERT；promote 重跑前先清空历史 promote 运行的行（含旧 canonical 行）；`dedup_canonical_ku.py` 删除 promote 运行的 canonical 行后整体重建。
- wiki 物化：重跑时与最新存储页 `page_checksum` 相同的主题整体跳过（不新增版本、行数不变）；只有源内容变化才追加新的不可变版本（`pv_N` 递增）——重跑产生新版本而非重复行。

### 成本与模型护栏

- LLM 调用（`mvp_semantic_compress.py` 的 pilot/scale、`classify_ku_staging.py`）经 `personal_knowledge.core.llm.make_llm_client`（purpose=`conversation_summary`）走 pi 内核通道：内核须在跑，且进程前设置 `PI_KERNEL_INTERNAL_CAPABILITY`。
- scale 模式硬性成本上限：环境变量 `PK_MVP_COST_CAP`（默认 `8`，单位 ¥），达到即停，不为跑数调大代码里的预算。
- embedding 一律本机模型（`personal_knowledge.core.local_embed`，bge-small-zh-v1.5，512 维），不经联网 LLM。`build_semantic_vector_store.py` 与 `dedup_canonical_ku.py` 在 import `local_embed` 之前用 `os.environ.setdefault("PERSONAL_DATA_EMBED_MODEL_PATH", r"D:\models\bge-small-zh-v1.5")` 兜底（runtime_config 默认候选路径指向 C 盘残缺缓存，实测加载失败；`setdefault` 不覆盖调用方已显式设置的值）。新脚本需要 embedding 时沿用同一兜底模式，且必须在 import 前设置。
- Chroma collection 按 `semantic_mvp_v1_<UTC时间戳>` 版本化：每次构建产生新版本，旧版本一律保留、绝不删除（脚本无任何删除路径）。构建登记写 `var/db/semantic_index_registry.json`，status 取 candidate | active | superseded，`--activate` 保证 active 至多一个。

### 测试指引

语义层测试全部零 LLM、零网络、零真实模型：

- [`tests/unit/test_semantic_cards.py`](../../tests/unit/test_semantic_cards.py)：检索适配器。夹具库用自建 DDL（复刻 `mvp_semantic_compress.py` 的 init_db）；真实库只留一条 `@pytest.mark.live` 冒烟（`var/db/semantic_mvp_v3.sqlite` 不存在时 skipif 跳过）。
- [`tests/unit/test_semantic_cards_vector.py`](../../tests/unit/test_semantic_cards_vector.py)：向量优先路径。假登记文件 + monkeypatch 假 chroma 客户端与假 embedding；回退路径验证任一环节失败时无声回退且与关键词结果一致；真实向量层冒烟同样标记 `live`。
- [`tests/contract/test_semantic_cards_wiring.py`](../../tests/contract/test_semantic_cards_wiring.py)：MCP render 分支 + REST `/search/cards` handler 接线；用桩 handler 直调函数，不启服务。
- [`tests/unit/test_materialize_wiki.py`](../../tests/unit/test_materialize_wiki.py)：实体归一化、主题绑定与 `--min-claims` 阈值、`wiki_page_body_v1` 契约（确定性、无时间戳、无原始对话正文）、物化幂等与 page-first 读路径。直接把 `tools/semantic` 加入 `sys.path` 导入被测脚本。
- [`tests/unit/test_wiki_consolidation.py`](../../tests/unit/test_wiki_consolidation.py)：Phase 4 wiki 统合页 page store、`consolidate_wiki` 分桶/确定性正文/幂等、page-first `topic_get`。

离线夹具约定：[`tests/conftest.py`](../../tests/conftest.py) 的 autouse 夹具把 `semantic_cards.SEMANTIC_INDEX_REGISTRY` monkeypatch 到 `tmp_path` 下不存在的路径，使 `search_cards` 在所有测试里稳定走关键词回退——不依赖真实 chroma 服务、登记文件与本机 embedding 模型。需要测向量路径的用例在测试体内再次 monkeypatch 覆盖该默认（后设置的生效），真实登记冒烟即按此还原。

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

## 提交纪律

- 仓库规则：`data/`、`var/` 私有库、运行报告、凭据与个人对话正文不得提交（根 [`AGENTS.md`](../../AGENTS.md) Agent 硬约束第 4 条；`docs/AGENTS.md` 标准 checklist 同项）。
- Agent 工作流约定：只在用户明确要求时执行 git commit / push，不由 Agent 自行提交。通过 `gsd:docs-update` 产生的文档变更，由该技能流程的 commit 步骤统一提交，不走临时散提交。
