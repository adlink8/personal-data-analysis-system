---
mapped: 2026-07-13
focus: quality
scope: full-repository
---

# 项目约定与可持续治理规则

## 当前事实

- 主体是 Python 项目：已跟踪 473 个文件，其中 262 个 Python 文件；应用侧另有 Node.js/MCP widget，入口位于 `integration/apps/personal_data_chatgpt/`。
- 生产实现按领域位于 `integration/scripts/{core,conversation,knowledge,memory,graph,vector,pipeline,services,evaluation,source_adapters}/`。
- `integration/scripts/` 根目录仍保留旧命令兼容层；扫描到 86 个明确的 compatibility shim。真实实现应以领域包内模块为准。
- 路径解析已有中心入口 `integration/scripts/core/project_paths.py`，但仍存在少量脚本自行计算根目录、修改 `sys.path` 或硬编码用户目录。
- 测试集中在 `tests/`；私有数据、数据库、运行时输出和评测报告由 `.gitignore` 隔离。

## 权威目录分类

所有目录和最末级文件都必须能归入下列一种类型。治理不是为每个叶目录堆一个 README，而是用机器可读 inventory 覆盖每个文件，再在稳定模块边界写 README。

| 类型 | 典型位置 | 版本控制 | 生命周期 |
|---|---|---|---|
| source | `integration/scripts/*/`, `integration/apps/` | 必须跟踪 | 评审、测试、兼容策略后变更 |
| tests | `tests/`, app 内 `test/` | 必须跟踪 | 与公共契约同步 |
| public fixtures | `integration/evals/knowledge_units/*.synthetic.jsonl`, YAML、rubric | 必须跟踪 | 版本化、不得含私人正文 |
| docs | `README.md`, `integration/docs/`, `.planning/` | 必须跟踪 | 与代码和验证结果同步 |
| private source | `Google/raw/`, AgentsView 数据库、private eval | 禁止跟踪 | 本机保留、只读导入 |
| generated | `integration/analysis/`, `integration/structured/`, HTML/PNG/JSON 报告 | 默认忽略 | 可重建、设保留期 |
| runtime state | `integration/db/`, `integration/runtime/`, Chroma、SQLite journal | 默认忽略 | 备份、迁移、回滚规则 |
| archive | `_recycle/`, legacy `.gsd/` | 不参与运行和测试 | 只读、设退役/保留说明 |
| tooling scratch | `integration/scripts/_tools/`, `logs/`, `.ai-bridge/` | 逐项分类 | 有 owner/用途/到期日，否则归档 |

## Python 代码约定

- 新实现放到领域包，不再向 `integration/scripts/` 根目录增加真实业务实现。
- 根级脚本只允许薄 CLI shim；shim 必须包含目标模块、弃用状态和计划移除版本，不得复制业务逻辑。
- 公共路径、规则、数据库连接和验证 helper 优先复用 `integration/scripts/core/`，禁止新增 `C:/Users/<name>`、Desktop 或当前工作目录假设。
- 模块/函数使用 `snake_case`，类使用 `PascalCase`，常量使用 `UPPER_SNAKE_CASE`；测试文件与被测领域同名映射。
- 对生产写操作采用 `stage -> validate/gate -> promote -> journal -> rollback`；默认 dry-run，commit/promote 必须显式确认并校验 checksum。
- 所有权威记录保留 source/evidence/run/version 字段；禁止通过删除历史来模拟更新。
- 错误必须区分输入错误、可重试外部错误、gate failure 和内部一致性错误；CLI 失败返回非零退出码并输出结构化摘要。
- 私人正文、密钥、token、cookie 不进入日志、测试 fixture、规划文档或公开 eval 报告。

## 文档约定

- 根 `README.md` 只承担入口、快速开始、架构导航和安全边界；领域细节下沉到对应目录。
- 需要模块 README 的稳定边界：`integration/apps/`、`db/`、`docs/`、`evals/`、`lib/`、`prompts/`、`runtime/`，以及 `scripts/` 下所有领域包、`tests/`。
- 每个模块 README 至少写：职责、允许/禁止内容、权威入口、输入输出、数据敏感级、测试命令、owner/维护状态。
- 叶文件由 `project-inventory.yaml`（建议新增）逐项记录：`path, class, owner, status, source_of_truth, generated_by, retention, sensitivity, replacement`。这才是“直到最后一级文件”的可持续覆盖方式。
- 文档事实优先级：运行时/数据库真实状态与测试 > verification/UAT > SUMMARY > STATE > ROADMAP > README > 历史设计稿。
- Phase 状态只在 SUMMARY、VERIFICATION、UAT 达到关闭条件后标 complete；ROADMAP、STATE 与 GSD SDK 结果必须一致。

## 依赖与版本约定

- 生产依赖位于 `requirements.txt`，测试工具位于 `requirements-dev.txt`；Node 依赖由 app 自己的 `package.json`/lockfile 管理。
- 当前 Python 依赖多为最低版本范围，不能保证长期可复现。治理目标应增加锁文件或 constraints，并明确支持 Python 3.12（CI）与 3.14（本机）矩阵。
- 本机预装但未声明的 `torch`、`sentence-transformers` 属于隐式依赖，必须改成可选 extra/安装文档并增加缺失时的明确错误。
- 外部 CLI/SDK 路径通过环境变量和 discovery 获取，不允许在代码内固定 `C:/Users/li/google-cloud-sdk`。

## 自动约定门

1. `inventory-check`：所有非忽略文件必须出现在分类规则或 inventory 中；未知文件阻断合并。
2. `path-policy`：扫描源码/文档中的用户名、Desktop、绝对盘符和裸 `sys.path.insert`；新增命中阻断。
3. `shim-budget`：现有 86 个 shim 建 baseline，新增 shim 阻断；每次 release 只允许下降。
4. `docs-coverage`：稳定模块必须有 README；README 中入口和测试命令必须存在且可执行。
5. `planning-consistency`：比较 ROADMAP、STATE、PLAN/SUMMARY/VERIFICATION/UAT 与 `gsd-sdk query progress`。
6. `generated-artifact-policy`：大文件、数据库、个人数据、报告不得误跟踪；公开 fixture 必须经过隐私扫描。

