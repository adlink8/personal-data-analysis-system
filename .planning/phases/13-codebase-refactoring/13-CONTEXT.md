---
phase: 13
name: codebase_refactoring
title: 代码库基础层重构 — 消除重复、统一路径、提取公共层
status: Complete — Wave 1-5 verified 2026-07-10
updated: 2026-07-10
---

# Phase 13 执行上下文

## 已完成工作

### Wave 1：扫描（workflow 子代理完成）

- 扫描 47 个脚本，41 个有问题
- 产物：`integration/analysis/refactoring/phase13_verification.md`
- 扫描结论：
  - `sha256_text` / `norm` / `short` / `event_id` / `entity_id` 在 13+ 文件中重复定义
  - `TOPIC_RULES` / `TOOL_NAMES` 在至少 2 个文件中重复定义
  - `Path.cwd().resolve()` 作为 ROOT 在多处使用（脆弱）

### Wave 2：创建 `core/` 包（workflow 子代理完成）

- 新建 `integration/scripts/core/__init__.py`（空）
- 新建 `integration/scripts/core/project_paths.py`：
  - `ROOT = Path(__file__).resolve().parents[3]`（正确：core→scripts→integration→项目根）
  - 导出：`ROOT`, `INTEGRATION_DIR`, `DB_DIR`, `SCRIPTS_DIR`, `ANALYSIS_DIR`, `AI_CONTEXT_DIR`
  - 导出：`UNIFIED_DB`, `CONV_GRAPH_DB`, `GOOGLE_DB`, `GPT_DB`, `AGENT_DB`, `SOURCE_DBS`

### Wave 3：迁移 `build_integrated_system.py`（手动完成）

**迁移前**：本地定义了 9 个重复项，ROOT 依赖 `Path.cwd()`。

**迁移后（逐项）**：

| 项目 | 迁移方式 |
|------|---------|
| `sha256_text` | 删除，从 `common` 导入 |
| `norm` | 删除，从 `common` 导入 |
| `short` | 删除，从 `common` 导入 |
| `event_id` | 删除，从 `common` 导入 |
| `entity_id` | 删除，从 `common` 导入 |
| `extract_domain` | 删除，从 `common` 导入 |
| `extract_tools` | 删除，从 `common` 导入；调用点改为 `extract_tools(text, TOOL_NAMES)` |
| `write_csv` | 删除，从 `common` 导入（行为差异已确认以 common.py 为权威） |
| `TOOL_NAMES` | 删除，从 `rules` 导入 |
| `TOPIC_RULES` | 删除，从 `rules` 导入（内容差异已确认以 rules.py 为权威） |
| `ROOT = Path.cwd().resolve()` | 改为 `Path(__file__).resolve().parents[2]` |
| `import csv` | 删除（write_csv 已由 common 提供，无其他使用） |
| `import hashlib` | 删除（sha256_text 已由 common 提供） |
| `from urllib.parse import urlparse` | 删除（extract_domain 已由 common 提供） |

**TOPIC_RULES 内容差异处理**：
- 旧本地版："编程/调试/工具"含 `"scripts"`，"数据分析/个人系统"含 `"sqlite"`
- rules.py 版："编程/调试/工具"含 `"脚本"`（不含 "scripts"），无 `"sqlite"` in 数据分析条目
- **决策**：以 rules.py 为权威（用户确认），`build_integrated_system.py` 的历史分类结果可能小幅变化

**write_csv 行为差异处理**：
- 旧本地版：空 rows 写 `""`（空字符串），`extrasaction="raise"`
- common.py 版：空 rows 仍调用 `writeheader()`，`extrasaction="ignore"`
- **决策**：以 common.py 为权威（用户确认），空 CSV 行为统一

### Wave 3（附）：迁移 `build_deep_profiles.py`（手动完成）

- 已有 `import rules as _rules`（Wave 1 之前已迁移）
- 本次：删除本地 `def norm()`，添加 `from common import norm`

## Wave 4-5 完成结果（2026-07-10）

### Wave 4：批量迁移验证

扫描 11 个 PLAN 列出的目标文件，发现**已无可安全迁移残留**：

- 7 个文件已正确 `from common/rules import`，无本地重复定义。
- `enrich_unified_events.py` 已 `import common` / `import rules`，用模块访问方式。
- 3 个文件（`build_triple_store.py` / `build_vector_store.py` / `build_conversation_graph.py`）不使用 common/rules 符号。

**ESCALATE（5 处有意本地特化，签名/行为不同，按 Escalation gate 保留）**：

| 文件 | 函数 | 差异 |
|------|------|------|
| `visualize_conversation_graph.py` | `short` | limit=180，加省略号，不调 norm |
| `build_deep_profiles.py` | `write_csv` | fieldnames 用 `sorted({...})`（所有行 key 并集）vs common 的 `list(rows[0].keys())` |
| `build_deep_profiles.py` | `write_json` | 行为等价但实现不同，按严格逐行规则 ESCALATE |
| `build_deep_profiles.py` | `ensure_dirs` | 无参版本，创建特定项目目录 |
| `build_integrated_system.py` | `ensure_dirs` | 无参版本，创建 INPUT_INDEX/STRUCTURED 等 |

### Wave 5：验证通过

- `sha256_text` / `norm` / `event_id` / `entity_id` / `extract_tools` / `extract_domain` — 仅 common.py 定义
- `TOPIC_RULES` / `TOOL_NAMES` / `THINKING_RULES` / `PURE_TOPIC_RULES` — 仅 rules.py 定义
- `extract_tools` 所有调用点均传 `tool_names`
- 69 个 .py 文件 py_compile 全 PASS
- `pytest tests/test_memory_contracts.py` — 4 passed
- `run_pipeline.py --dry-run` — 12 步全部正常

### 路径迁移（可选后续）

`core/project_paths.py` 已创建，但多数脚本仍用 `_THIS_DIR = Path(__file__).resolve().parent` + `_THIS_DIR.parents[N]` 方式。
可以在稳定后逐步切换到 `from core.project_paths import ROOT`，但优先级低于消除重复定义。

## 验证状态

| 检查 | 状态 |
|------|------|
| 69 个 .py 文件 py_compile | ✅ 全 PASS |
| 单一定义检查（sha256_text/norm/event_id/entity_id 等）| ✅ 仅 common.py |
| 常量单一定义（TOPIC_RULES/TOOL_NAMES 等）| ✅ 仅 rules.py |
| extract_tools 调用点签名检查 | ✅ 全部传 tool_names |
| `tests/test_memory_contracts.py` | ✅ 4 passed |
| `run_pipeline.py --dry-run` | ✅ 12 步正常 |

建议手动在项目根执行：
```powershell
python -m py_compile integration\scripts\build_integrated_system.py
python -m py_compile integration\scripts\build_deep_profiles.py
python tests\test_memory_contracts.py
```

## 决策记录

| 决策 | 结论 | 理由 |
|------|------|------|
| TOPIC_RULES 权威版本 | `rules.py` | 以 Phase 13 计划为标准 |
| write_csv 权威版本 | `common.py` | 以 Phase 13 计划为标准；`extrasaction="ignore"` 更健壮 |
| ROOT 解析方式 | `Path(__file__).resolve().parents[N]` | 不依赖运行目录，可在任意位置调用 |
