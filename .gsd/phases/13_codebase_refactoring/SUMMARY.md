---
phase: 13
name: codebase_refactoring
status: Complete
verified: 2026-07-10
---

# Phase 13 执行摘要

## 目标

消除 `integration/scripts/` 70+ 个脚本中因历史积累形成的结构性重复：工具函数多处重复定义、分类规则未统一、路径解析方式不一致。

## 交付

- **Wave 1**：扫描 47 个脚本，生成 `integration/analysis/refactoring/phase13_verification.md`
- **Wave 2**：创建 `core/project_paths.py` 统一路径常量（`ROOT` 从 `__file__` 派生，不依赖 `Path.cwd()`）
- **Wave 3**：迁移 `build_integrated_system.py`（删除 10 个重复定义 + ROOT 修复）和 `build_deep_profiles.py`（删除本地 `norm`）
- **Wave 4**：验证 11 个 PLAN 列出的目标文件 — 已无可安全迁移残留。5 处同名函数为有意本地特化（签名/行为不同），按 Escalation gate 保留
- **Wave 5**：全链路验证通过

## 验证结果

| 检查 | 结果 |
|------|------|
| 单一定义（sha256_text/norm/event_id/entity_id/extract_tools/extract_domain）| ✅ 仅 common.py |
| 常量单一定义（TOPIC_RULES/TOOL_NAMES/THINKING_RULES/PURE_TOPIC_RULES）| ✅ 仅 rules.py |
| extract_tools 调用点签名 | ✅ 全部传 tool_names |
| 69 个 .py 文件 py_compile | ✅ 全 PASS |
| `test_memory_contracts.py` | ✅ 4 passed |
| `run_pipeline.py --dry-run` | ✅ 12 步正常 |

## ESCALATE 决策

5 处同名函数因签名/行为差异保留不迁移：

1. `visualize_conversation_graph.py::short` — limit=180，加省略号
2. `build_deep_profiles.py::write_csv` — fieldnames 用 `sorted({...})`（并集 key）
3. `build_deep_profiles.py::write_json` — 行为等价但实现不同
4. `build_deep_profiles.py::ensure_dirs` — 无参版本
5. `build_integrated_system.py::ensure_dirs` — 无参版本

这些是正确的设计决策，不是遗漏。`ensure_dirs()` 无参与 `ensure_dirs(paths)` 是不同契约。

## 未修改

- 不重构 memory pipeline 逻辑
- 不修改数据库 schema
- 不重命名对外 CLI / MCP 接口
- 不删除任何脚本
