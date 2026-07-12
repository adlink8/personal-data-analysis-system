---
gsd_state_version: 1.0
milestone: v1.0
milestone_name: milestone
status: executing
stopped_at: knowledge distribution adapted (CLI/REST/MCP) + docs
last_updated: "2026-07-12T07:20:00.000Z"
last_activity: 2026-07-12 -- 分发接口知识层适配：knowledge_status / GET /knowledge / stats.knowledge
progress:
  total_phases: 16
  completed_phases: 14
  total_plans: 23
  completed_plans: 22
  percent: 90
---

# Project State

## Project Reference

See: `.planning/PROJECT.md` (updated 2026-07-10)

**Core value:** 把个人数字足迹整理成隐私安全、证据可回查、可检索的本地知识系统。  
**Current focus:** Phase 14 近完成（KU-08 生产非空增量 E2E 可选）；工程结构已重整。

## Current Position

Phase: 14 of 16 (Knowledge Unit Layer)

Plan: 14-01..06 complete; **14-07 partial**（契约测试绿；生产 delta no_op）

Status: Production knowledge online; **repo layout cleaned**; **full pytest 307 passed**

Progress: [█████████░] ~93% (Phase 14)

## Repo layout (2026-07-12)

### Main tree
- `integration/` — 主工程（scripts 已分包）
- `Agent/structured/db/` — 会话证据库（保留）
- `Google/` — raw + structured（analysis 归档）
- `tests/`、`imports/`、`.planning/`

### Soft archive
- `_recycle/2026-07-12_structure_cleanup/` — GPT 整模块、Agent 闲置/分析、Google analysis、根目录垃圾桩、过时测试

### scripts package layout
```
integration/scripts/
  core/ knowledge/ memory/ conversation/
  graph/ vector/ services/ pipeline/
  source_adapters/ examples/ _tools/
  *.py   # compatibility shims
```
详见 `integration/scripts/README.md`。

## Performance Metrics

### Knowledge production
- Run `run_76c6259e9ed09d5b` gate **PASSED**（yield 91.4%, fail 0.41%）
- Active index: **`knowledge_units_run_76c6259e_20260712062418`**（**30,012**）
- Reconcile PASS；pure-KU / hybrid frozen Recall@5 **0.65**（secret 0）

### Distribution surfaces (Phase 14 knowledge)
- CLI: `semantic` → `search_knowledge_units`；新增 `knowledge` 状态子命令；`stats` 含 knowledge 块
- REST: `POST /search/semantic` 混合检索；`GET /knowledge`；`/health` 带 knowledge 摘要
- MCP: `search_semantic` 文案更新；新增 `knowledge_status`（18 tools）
- 契约测试: `tests/test_knowledge_distribution_contracts.py`

### Automated tests
- Full suite: **353 passed**（知识分发契约 +6）
- Collect-only: clean
- 强引用模块覆盖：**54.5%+**（见 `test_coverage_gaps.md`）
- 功能域知识检索 / 数据访问：covered

## Pending Todos
- 14-07 非空 delta 生产 E2E（KU-08）
- 可选：hybrid 质量回升 ~0.85；canary 人工 label
- 可选：P2 管道 builder smoke（enrich / integrated_system / memory builders）
- Phase 08 延后

## Evidence
- `integration/analysis/ai_context/test_coverage_gaps.md`（+ `.json`）
- `integration/analysis/ai_context/phase14_wrapup_test_report.md`
- `integration/scripts/README.md`
- `integration/scripts/_tools/_audit_test_gaps.py`
- `_recycle/2026-07-12_structure_cleanup/MANIFEST.md`
