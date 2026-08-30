<!-- generated-by: gsd-doc-writer -->
# 测试指南

## 测试框架与准备

Python 测试使用 pytest `9.0.2`，异步测试使用 pytest-asyncio `1.4.0`；精确版本由 [`constraints.txt`](../../constraints.txt) 锁定，[`requirements-dev.txt`](../../requirements-dev.txt) 引用该约束并安装测试依赖。项目要求 Python 3.11 或更高版本，CI 当前验证 Python 3.12 和 3.14。

从仓库根目录准备 Python 测试环境：

```bash
python -m pip install -r requirements-dev.txt
python -m pip install -e .
```

[`pytest.ini`](../../pytest.ini) 将发现范围限制到 `tests/`，匹配 `test_*.py`、`Test*` 和 `test_*`，以 `importlib` 模式导入，并把 `src/` 加入 Python 路径。pytest 缓存写入 `var/cache/pytest`；归档、私有导入、日志、Node modules 和构建产物不会被递归收集。

仓库还包含三类 JavaScript 测试：

| 包 | 框架 | 版本或运行时 | 测试命令 |
|---|---|---|---|
| `apps/personal_data_chatgpt` | Node.js 内置 `node:test` | Node.js >= 20 | `npm test` |
| `apps/personal_intelligence_kernel` | Node.js 内置 `node:test` | Node.js >= 22.19.0 | `npm test` |
| `apps/personal_intelligence_desktop` | Node.js 内置 `node:test` | Node.js >= 22.19.0 | `npm test` |
| `apps/personal_decision_cockpit` | Vitest | `^3.0.2` | `npm test` |

每个包都有自己的 `package-lock.json`。进入对应包目录后运行 `npm ci` 安装依赖；CI 对 ChatGPT MCP 包使用 `npm ci --ignore-scripts`。

## 运行测试

### Python

运行完整 Python 测试集：

```bash
python -m pytest
```

`pytest.ini` 已默认加入 `-q`。CI 会先验证收集，再运行完整测试：

```bash
python -m pytest --collect-only -q
python -m pytest -q
```

按测试层运行子集：

```bash
python -m pytest tests/unit/
python -m pytest tests/contract/
python -m pytest tests/integration/
python -m pytest tests/e2e/
python -m pytest tests/governance/
python -m pytest tests/security/
python -m pytest tests/ops/
python -m pytest tests/eval/
```

运行单个文件、单个测试或按名称筛选：

```bash
python -m pytest tests/unit/test_budget_config.py
python -m pytest tests/unit/test_budget_config.py::test_budget_env_beats_config_file
python -m pytest tests/contract/ -k privacy
```

仓库没有配置 pytest watch 命令。需要快速反馈时，重复运行最小的文件或 node id，而不是先跑整个套件。

### JavaScript

在各包目录运行其锁定的测试命令：

```bash
cd apps/personal_data_chatgpt
npm ci --ignore-scripts
npm test
```

其他包使用相同方式，将目录替换为 `apps/personal_intelligence_kernel`、`apps/personal_intelligence_desktop` 或 `apps/personal_decision_cockpit`。Kernel 的 `npm test` 只匹配 `test/*.test.mjs`，不会运行 `test/manual/` 下的人工外部-provider 测试。

Kernel 套件当前为 101 个用例，`node --test test/*.test.mjs` 全量通过（101 pass / 0 fail / 0 skipped；用例数会随开发增长）。两个契约守卫值得关注：

- [`test/task-response-replay.test.mjs`](../../apps/personal_intelligence_kernel/test/task-response-replay.test.mjs)：重启重放回归。基于真实 `startKernelServer` 与 `KernelHost`，验证 task `include_response` 与 skill report 在 host 重启后从持久化 ledger 原样重放，且 ledger 重开后保留有界响应、跳过超限响应。
- [`test/server.test.mjs`](../../apps/personal_intelligence_kernel/test/server.test.mjs) 中的 `ALLOWED_ROUTES declares the operations control-plane routes it dispatches`：白名单契约守卫。5 条 operations 分派路由（list/get/cancel/resume/reconcile）必须逐条出现在 `src/server.mjs` 导出的 `ALLOWED_ROUTES` 冻结数组中；新增分派分支必须在同一次变更中登记进白名单，防止发布路由契约静默漂移。

ChatGPT MCP 还提供一个定向 widget 命令：

```bash
cd apps/personal_data_chatgpt
npm run test:widgets
```

## 语义层与 wiki 物化测试

语义检索（semantic cards）与 wiki 物化链路由以下测试覆盖，默认全部离线可跑（live 冒烟除外，见下文 [live 标记](#live-标记)）：

| 文件 | 用例 | 覆盖内容 |
|---|---:|---|
| [`tests/unit/test_semantic_cards.py`](../../tests/unit/test_semantic_cards.py) | 13 | `search_cards` / `get_card` 的关键词打分与会话聚合；夹具库按 `tools/semantic/mvp_semantic_compress.py` 的 DDL 自建，不依赖真实卡库。 |
| [`tests/unit/test_semantic_cards_vector.py`](../../tests/unit/test_semantic_cards_vector.py) | 12 | 向量打分、距离截断、端点解析，以及无登记、chroma 不可达、collection 或 embed 模型缺失、登记无 active build、登记损坏时的关键词回退。 |
| [`tests/contract/test_semantic_cards_wiring.py`](../../tests/contract/test_semantic_cards_wiring.py) | 11 | `search_cards` 工具在 `ALL_TOOLS` 的 schema 注册，schema 面与 handler 分派表的双向一致性（反向多出的只能是文档化的 `data_export_all` / `data_export_query` 兼容别名），以及 MCP render 与 REST 分支的输出契约。 |
| [`tests/unit/test_materialize_wiki.py`](../../tests/unit/test_materialize_wiki.py) | 14 | 实体归一化与非法主题键丢弃、KU 经卡到实体的主题绑定与噪声阈值、确定性 `wiki_page_body_v1` 正文、物化幂等（同内容重跑不新增版本/行，内容变化才追加 `pv_N` 版本）、dry-run 与 limit。 |
| [`tests/unit/test_wiki_consolidation.py`](../../tests/unit/test_wiki_consolidation.py) | 11 | `wiki_projection_pages` schema 往返、bucket 归一化、`consolidate_wiki` 确定性与幂等、缺 store 时 fail-safe、page-first `topic_get` / `topic_list` 读取回退的回归。 |

用例数以 `python -m pytest --collect-only -q` 为准（parametrize 展开计入）。

语义层的离线稳定性来自 [`tests/conftest.py`](../../tests/conftest.py) 的 autouse 夹具：把 `semantic_cards.SEMANTIC_INDEX_REGISTRY` monkeypatch 到 `tmp_path` 下不存在的路径，使所有测试默认走关键词回退路径，不依赖 chroma 服务、登记文件或本机 embedding 模型。需要测向量路径的用例在测试体内再次 monkeypatch 该常量覆盖默认（后设置的生效）；`test_semantic_cards_vector.py` 的向量场景即按此方式构造。

## live 标记

`pytest.ini` 注册了 `live` marker：需要私有本地数据或运行中服务的用例。它的生效分两层：

- CI 层：`ci.yml` 用 `python -m pytest -m "not live" -q` 显式排除，live 用例永不进入 CI。
- 本地层：裸跑 `python -m pytest` 不会自动排除 live，是否执行由用例自行判断。`test_semantic_cards.py::test_real_db_smoke` 与 `test_semantic_cards_vector.py::test_real_vector_smoke` 都带 `@pytest.mark.skipif`，在真实产物（`var/db/semantic_mvp_v3.sqlite`、含 active build 的 `var/db/semantic_index_registry.json`）缺失时跳过；`tests/integration/test_target_d_acceptance.py` 的 live 用例不带 skipif，只在拥有真实产物的本机上执行。

## 编写新测试

新 Python 测试放在与行为层级对应的目录中：

| 目录 | 适用范围 |
|---|---|
| `tests/unit/` | 纯规则、状态转换和数据变换。 |
| `tests/contract/` | schema、receipt、状态、错误，以及 provider/consumer 兼容性。 |
| `tests/integration/` | 真实本地 adapter、临时 SQLite 和事件 journal 的组合行为。 |
| `tests/e2e/` | 关键能力的一条完整用户路径。 |
| `tests/governance/` | 机器可读策略、目录边界、入口和仓库约束。 |
| `tests/security/` | 隐私、授权、隔离和工具 containment。 |
| `tests/ops/` | PowerShell 启动栈及运维脚本。 |
| `tests/eval/` | 数据技能与个人技能的评估行为。 |

文件和测试函数必须使用 `test_*.py` / `test_*` 命名。顶层共享 conftest 只有 [`tests/conftest.py`](../../tests/conftest.py)，且只承载语义层的 autouse 离线夹具（见下文[语义层与 wiki 物化测试](#语义层与-wiki-物化测试)）；其余 fixture 通常在拥有行为的测试文件内定义。优先使用 pytest 的 `tmp_path`、`monkeypatch`、临时 SQLite、确定性 replay provider 和本地 stand-in。`tests/fixtures/` 只存放最小、脱敏、确定性的公共夹具；不得复制真实个人数据。

对生产行为的修改遵循 [`governance/policies/testing.yaml`](../../governance/policies/testing.yaml)：

1. 先声明公开 seam、可观察行为、不变量和定向测试命令。
2. 先让定向测试因预期的行为原因失败，再实施最小改动使同一测试通过。
3. 运行相关回归测试和 `git diff --check`。
4. Bug 修复必须新增回归测试；公共接口修改需要 provider contract、consumer contract 和真实 adapter integration 测试。
5. Mock 只用于外部 API、模型 provider、时钟、随机性和文件系统边界。不要 mock 项目内部模块、私有方法、调用次数或调用顺序。
6. 新增 `skip` 或 `xfail` 必须写明原因、跟踪引用和移除条件；不能用重试掩盖 flaky failure。

Node 内置测试使用 `*.test.mjs`；Cockpit 使用 Vitest 的 `*.test.ts` 或 `*.test.tsx`。测试名称应描述公开可观察行为和结果，而不是实现细节。

## 覆盖率要求

仓库策略定义了以下变更级覆盖目标：

| 类型 | 阈值 | 当前自动化执行 |
|---|---:|---|
| 变更行覆盖率 | 85% | 未在 pytest/CI 中测量 |
| 关键策略分支覆盖率 | 100% | 未在 pytest/CI 中测量 |
| 仓库总体覆盖率 | 不得下降 | 未配置基线比较 |

这些目标来自 `governance/policies/testing.yaml`，并被 governance 测试校验为策略值；它们是行为映射的辅助门槛，不能代替 requirement、decision 和 negative case 的测试映射。

当前仓库没有 `pytest-cov`、Coverage.py、c8 或 Vitest coverage 配置，也没有 `--cov` CI 步骤。因此不存在由测试运行器自动强制的覆盖率阈值；提交者需要用定向行为测试满足策略目标，直到覆盖率采集接入 CI。

## CI 集成

唯一的 GitHub Actions 工作流是 [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)，名称为 `governed-ci`，在每次 `push` 和 `pull_request` 时运行。

| Job | 运行环境 | 主要步骤 |
|---|---|---|
| `python` | `windows-latest`，Python 3.12 与 3.14 matrix | 安装受约束开发依赖；运行 `python integration/scripts/governance/preflight.py --ci`；执行 pytest 收集和全部离线测试（排除标记为 `live` 的私有数据/服务验收）。 |
| `node` | `windows-latest`，Node.js 20 | 在 `apps/personal_data_chatgpt` 执行 `npm ci --ignore-scripts` 和 `npm test`。 |
| `cockpit` | `windows-latest`，Node.js 20 | 在 `apps/personal_decision_cockpit` 执行 `npm ci --ignore-scripts`、`npm test` 和生产 `npm run build`。 |
| `desktop` | `windows-latest`，Node.js 22.19.0 | 在 `apps/personal_intelligence_desktop` 执行 `npm ci --ignore-scripts` 和 `npm test`。 |
| `kernel` | `windows-latest`，Node.js 22.19.0 | 在 `apps/personal_intelligence_kernel` 执行 `npm ci --ignore-scripts` 和 `npm test`。 |

CI 的 Python matrix 设置 `fail-fast: false`，因此一个版本失败不会取消另一个版本的结果。Kernel 的 `npm run qualify` 仍是联网的依赖资格检查，不属于上述离线 PR 测试 job。
