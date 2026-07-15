---
mapped: 2026-07-13
focus: concerns
scope: full-repository
---

# 全仓治理风险与分级处置

## 总体判断

项目核心测试当前全绿，主要风险不是功能立即失效，而是规模扩大后事实源漂移、兼容层永久化、私人数据误入版本库，以及环境不可复现。应先建立自动门，再分批搬迁；禁止一次性大重构或直接删除历史/私人文件。

## P0 — 必须始终阻断

### 私密数据或凭据进入 Git/公开报告

- 仓库同时处理 `Google/raw/`、AgentsView 会话、SQLite/Chroma、private eval，风险面天然较大。
- `.gitignore` 已覆盖大部分私有/生成物，但 JSON/JSONL 使用“全局忽略 + eval 例外”，新增例外容易误放真实正文。
- 治理门：每次提交执行 secret/PII scan、tracked artifact scan、文件大小门；公开 eval 只允许 synthetic schema 并人工抽查。

### 绕过评测直接 promote

- Knowledge index、Google assertions 都是用户可见知识事实源。
- 治理门：生产写路径必须绑定 immutable eval run/checksum；gate fail、缺报告、过期报告均 fail closed；active 不变和 rollback 是强制测试。

## P1 — Phase 18 必须解决

### 规划状态漂移

- `.planning/STATE.md` 写 Phase 17 为 4/4 code complete、85%；`.planning/ROADMAP.md` 的进度表仍写 0/4 Planned。
- `gsd-sdk query progress` 将 Phase 17 识别为 Executed，但旧 Phase 01–04、07、10 因缺 SUMMARY 仍被识别为 Planned；总进度显示 86%，与 ROADMAP 的历史完成声明冲突。
- 处置：确定唯一关闭契约；为 legacy phase 使用 migration/cancelled/verified summary，不伪造执行证据；CI 加 planning consistency gate。

### 工作树未形成可审计发布单元

- 扫描时有 22 个 modified、67 个 untracked：其中 30 个在 `integration/`、29 个在 `.planning/`、7 个在 `tests/`，另有新 `pytest.ini`。
- 这不代表文件应删除，但当前难以区分 Phase 17 交付、治理文档、实验探针和本地生成物。
- 处置：生成 inventory，按 keep/ignore/archive/review 分类；按 phase/concern 拆分提交；任何删除、归档或覆盖需用户确认。

### 兼容 shim 面过大

- `integration/scripts/` 根目录有 86 个明确 compatibility shim；另有 `build_google_light_assertions.py` 和 `build_google_normalized_events.py` 同名根/包文件但未被标准 shim 识别。
- 兼容入口多会扩大导入路径组合、重复测试面和模块身份风险；`test_knowledge_unit_llm.py` 也同时存在根 shim 与 `knowledge/` 实现。
- 处置：建立 shim manifest（target、consumer、deprecated_since、remove_after）；禁止新增；先迁移调用方和文档，再按使用证据逐批退役。

### 绝对路径与本机 SDK 假设

- `integration/scripts/knowledge/build_knowledge_units.py`、`build_knowledge_units_prod.py`、`test_knowledge_unit_llm.py` 硬编码 `C:/Users/li/google-cloud-sdk`。
- `integration/scripts/services/mcp_server.py` 与根 `README.md` 示例硬编码当前 Desktop 路径。
- `_tools/compare_l1_l2_retrieval.py` 固定写 `Path.home()/Desktop`，与项目内 report policy 冲突。
- 处置：统一环境变量/discovery + `project_paths`；CI path-policy 阻断新增绝对路径。Eval fixture 中作为历史 query 内容的路径需标记为 fixture exception，而非机械替换。

### 依赖不可完全复现

- `requirements.txt` 主要使用最低版本范围；torch/sentence-transformers 依赖本机预装且被注释；CI 只测 Python 3.12，本机事实为 Python 3.14。
- 处置：生成 constraints/lock，区分 core、AI/vector、app、dev extras；3.12/3.14 双矩阵；缺可选依赖时输出可操作错误。

## P2 — 近期持续治理

### 探针与一次性工具没有生命周期

- `integration/scripts/_tools/` 有 22 个脚本，包含 `_probe_*`、`_inspect_*`、`_fix_*`、重组脚本和旧 phase eval。
- 有些是有价值的审计工具，有些是迁移后残留；目前缺 owner、输入风险、是否生产安全、到期日。
- 处置：分类为 supported-tool / migration / forensic / obsolete-candidate；supported 工具补 `--help`、dry-run 和测试，其余移入只读 archive 前先确认。

### 模块文档覆盖不足

- `integration/{apps,db,docs,evals,lib,prompts,runtime}` 一级边界无 README；`scripts/` 的 core、knowledge、conversation、memory、graph、vector、services、pipeline、evaluation 无领域 README；`tests/` 也无测试导航。
- 处置：只在稳定模块边界补 README；叶文件通过 inventory 全覆盖，避免“每层每目录 README”造成新的文档债务。

### `sys.path` 注入与执行上下文不统一

- 多个领域模块和 `_tools` 直接修改 `sys.path`，部分使用相对字符串 `integration/scripts`，使从不同 cwd 启动时行为不同。
- 处置：逐步包化/模块入口 `python -m ...`；保留 shim 期间用统一 bootstrap helper；新增裸注入由 lint 门阻断。

### CI 质量门仍偏窄

- 当前 `.github/workflows/ci.yml` 只有 pytest；覆盖缺口审计为 `continue-on-error`；Node widget、lint/typecheck、安全、依赖和 planning drift 未覆盖。
- 处置：先以 baseline 模式引入，不要求旧债一次归零，但任何新增回归阻断；逐阶段降低 baseline。

## P3 — 观察项

- 根 README 已较长，继续增长会产生重复事实；治理后应只保留导航与 quickstart。
- `.gsd/` 与 `.planning/` 双历史目录可能让工具/人员选错事实源；明确 `.planning/` authoritative，`.gsd/` 只读迁移历史。
- `_recycle/` 和 `.ai-bridge/` 体量可能显著干扰磁盘扫描、IDE 索引和误检；保持从测试/搜索/治理 inventory 默认排除，同时单独维护 archive manifest。
- 行尾转换警告显示部分 Markdown/Python 将 LF 转 CRLF；建议增加 `.gitattributes`，避免无意义 diff。

## 分阶段治理门

| 门 | 阻断条件 | 允许以 baseline 迁移的旧债 |
|---|---|---|
| P0 security | secret/PII、私人 DB、未授权生产写入 | 无 |
| P1 correctness | 测试失败、planning 状态冲突、gate/rollback 缺失 | legacy SUMMARY 可用 migration 记录收口 |
| P1 reproducibility | 未声明依赖、硬编码新增路径、lock 漂移 | 现有硬编码建清单并逐步归零 |
| P2 architecture | 新增根业务脚本、新增 shim、跨域循环依赖 | 现有 86 shim 建 baseline |
| P2 maintainability | 未分类文件、缺 owner/生命周期、文档入口失效 | 67 untracked 必须人工分类，不自动删除 |

## 推荐 Phase 18 验收结果

- 所有非忽略文件由 inventory 分类；所有关键模块有边界 README；生成物/私有数据规则可机器验证。
- bare pytest、Python 3.12/3.14、Node app tests、lint/security/dependency/planning checks 全绿。
- shim 数量不增加且有退役清单；硬编码本机路径归零（fixture exception 除外）。
- ROADMAP、STATE、GSD progress、SUMMARY/VERIFICATION/UAT 一致。
- 治理 dashboard 可展示未分类文件、shim、测试、依赖、文档覆盖、planning drift 与评测发布门趋势。

