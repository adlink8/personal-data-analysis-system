---
phase: 05
name: memory_layer_hardening
title: 记忆层补强与契约测试
status: Completed
created: 2026-06-17
depends_on:
  - .gsd/phases/04_memory_layer_upgrade/05-CONSUMPTION-LAYER-PLAN.md
  - .planning/codebase/EXTERNAL_ALIGNMENT.md
autonomous: true
---

# Phase 05: 记忆层补强与契约测试

## Objective

把 Phase 04 已经跑通的记忆层从“功能可用”推进到“边界清晰、记忆可解释、入口可测试、具备深挖准入证据”。本阶段不追求新能力扩张，重点是降低后续改造和 Phase 06 深层图谱挖掘的漂移风险。

## Non-goals

- 不引入完整 mem0 / LangMem / GraphRAG runtime。
- 不做 dashboard。
- 不开放远程 MCP。
- 不全量重构所有数据源 adapter。
- 不让测试依赖外部网络、远程 API 或 LLM 非确定性输出。
- 不在本阶段生成深层人格/能力/因果洞察；只判断数据是否足以支撑后续深挖。

## Wave 1: Source Adapter Contract

### Goal

建立最小 source adapter 规范，为后续把 Google/GPT/Agent 等输入源逐步模块化做准备。

### Tasks

1. 新增 adapter contract 文档或代码模块，例如 `统合模块/脚本/source_adapters/README.md` 和 `base.py`。
2. 定义 canonical record 最小字段：
   - `source_type`
   - `source_id`
   - `title`
   - `content`
   - `created_at`
   - `updated_at`
   - `metadata`
   - `source_path`
   - `source_hash`
3. 选择一个低风险来源做样例 adapter，优先选已有结构稳定、数据读取简单的来源。
4. 保持现有 pipeline 行为不变，adapter 样例只作为可验证增量。

### Verification

- `python 统合模块\脚本\run_pipeline.py --dry-run`
- 新增 adapter smoke test 或脚本能输出 canonical record 样例。

### Acceptance Criteria

- 有明确 adapter contract。
- 至少一个样例 adapter 能产出 canonical record。
- 不破坏现有 `run_pipeline.py`。

## Wave 2: Memory Governance Metadata

### Goal

让长期记忆具备可解释性，降低错误记忆长期污染 profile 或 agent prompt 的风险。

### Tasks

1. 检查 `memory_items`、`memory_links`、`memory_relations` 当前字段和 metadata 内容。
2. 新增或标准化 governance metadata：
   - `evidence_ids`
   - `confidence`
   - `last_seen`
   - `source_hash`
   - `merge_key`
3. 优先改造生成记忆的脚本输出 metadata，不直接做破坏性 schema 迁移。
4. 让 `build_profile_from_memory.py` 输出关键结论来源摘要。
5. 让 memory subject / neighbor 查询能返回 relation confidence 或 evidence 摘要。

### Verification

- `python 统合模块\脚本\run_pipeline.py --only 12`
- `python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1`
- 抽查 `统合模块\分析数据\ai_context\person_profile_v2.md` 是否包含来源/证据提示。

### Acceptance Criteria

- 关键 memory item/relation 能解释来源。
- profile 不只输出结论，还能展示证据链摘要。
- 旧 memory 查询仍可运行。

## Wave 3: Transport Contract Tests

### Goal

防止 CLI / REST / MCP 三个入口在参数、字段、错误语义上继续漂移。

### Tasks

1. 建立测试目录，推荐 `tests/`。
2. 新增 memory contract test，至少覆盖：
   - core function: `get_memory_profile(memory_type="tooling")`
   - CLI: `unified_search.py memory --type tooling`
   - REST: `GET /memory?type=tooling&limit=2`
   - MCP: `get_memory_profile` tool handler 或 schema 层
3. 新增 subject query contract test，覆盖：
   - core function: `get_memory_by_subject("Codex")`
   - CLI: `memory --subject Codex --neighbors 1`
   - REST: `GET /memory/Codex?neighbors=1`
   - MCP: `get_memory_by_subject`
4. 统一最小输出 shape，例如：
   - `ok` 或成功状态
   - `items` / `memory`
   - `relations`
   - `neighbors`
   - `count`
5. 如果 pytest 不可用，先用 stdlib 脚本实现一条可执行验证命令。

### Verification

- `python -m py_compile 统合模块\脚本\unified_search.py 统合模块\脚本\api_server.py 统合模块\脚本\mcp_server.py`
- `python tests\test_memory_contracts.py` 或 `python -m pytest tests`

### Acceptance Criteria

- 一条命令能验证 memory 查询三入口 shape 一致。
- REST 服务能在测试中启动和关闭，不留下后台进程。
- MCP 测试不需要真实外部 client。

## Wave 4: Documentation and Codebase Map Refresh

### Goal

把补强后的真实状态同步到 README、统合模块 README、`.planning/codebase`，避免 Phase 04/05 后文档继续漂移。

### Tasks

1. 更新 `README.md`：
   - pipeline 入口
   - memory governance 说明
   - 测试命令
2. 更新 `统合模块/README.md`：
   - adapter contract
   - memory metadata
   - CLI/REST/MCP contract
3. 刷新 `.planning/codebase/ARCHITECTURE.md`、`INTEGRATIONS.md`、`TESTING.md` 中过期内容。
4. 在 Phase 05 目录补执行总结模板或验证记录。

### Verification

- `git diff --check`
- README 中列出的核心命令至少抽样执行。

### Acceptance Criteria

- 文档中的 pipeline 步数、endpoint、MCP tools 与代码一致。
- `.planning/codebase` 不再保留 Phase 04 Wave 5 前的过期数量。
- 用户能从文档知道如何验证记忆层。

## Wave 5: Depth Readiness Gate

### Goal

给 Phase 06 深层图谱挖掘建立准入门槛，避免把浅层统计、共现关系或 LLM 推测误当成深层洞察。

### Tasks

1. 新增 `统合模块/脚本/evaluate_memory_depth.py` 或等价脚本，抽样评估当前 memory graph。
2. 对至少 20 条 memory item / relation 做质量检查，维度包括：
   - `evidence_count`: 是否有足够原始证据或 memory_links。
   - `time_span`: 是否跨越多个时间点，而不是单次出现。
   - `recurrence`: 是否重复出现或有稳定模式。
   - `relation_strength`: 关系是否有 confidence/权重/来源。
   - `contradiction_check`: 是否存在明显反例或冲突记忆。
   - `depth_candidate`: 是否适合进入 Phase 06 做深层挖掘。
3. 输出 `统合模块/分析数据/ai_context/memory_depth_readiness.md`。
4. 在报告中明确列出：
   - 可以深挖的候选主题。
   - 暂不可信的浅层主题。
   - 缺失的证据字段。
   - Phase 06 的输入限制。

### Verification

- `python 统合模块\脚本\evaluate_memory_depth.py`
- 检查 `统合模块\分析数据\ai_context\memory_depth_readiness.md` 存在且包含候选主题和阻塞项。

### Acceptance Criteria

- 至少 20 条 memory/relation 被抽样评估。
- 报告明确区分“可深挖候选”和“浅层不足候选”。
- Phase 06 的 plan 不直接依赖未经 readiness 标记的记忆。

## Execution Order

1. Wave 3 可以先行做最小测试骨架，锁住现有行为。
2. Wave 1 再做 adapter contract，避免补强时破坏 pipeline。
3. Wave 2 做 governance metadata，并用 Wave 3 的测试防回归。
4. Wave 5 做 depth readiness，判断是否具备深挖条件。
5. Wave 4 最后同步文档。

推荐实际执行顺序：Wave 3 -> Wave 1 -> Wave 2 -> Wave 5 -> Wave 4。

## Phase Verification

本阶段完成前必须至少运行：

```powershell
python -m py_compile 统合模块\脚本\unified_search.py 统合模块\脚本\api_server.py 统合模块\脚本\mcp_server.py 统合模块\脚本\run_pipeline.py
python 统合模块\脚本\run_pipeline.py --dry-run
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1
python 统合模块\脚本\run_pipeline.py --only 12
python 统合模块\脚本\evaluate_memory_depth.py
python tests\test_memory_contracts.py
git diff --check
```

## Success Criteria

- Phase 05 不新增大功能，但显著降低漂移风险。
- 有 adapter contract 和至少一个样例。
- memory profile / relation 具备基础证据解释能力。
- CLI/REST/MCP memory 查询有 contract test 覆盖。
- `memory_depth_readiness.md` 明确 Phase 06 能深挖什么、不能深挖什么。
- README、统合模块 README、codebase map 与当前代码一致。

## Risk Register

| Risk | Impact | Mitigation |
| --- | --- | --- |
| 过早大规模 adapter 重构 | 破坏现有 pipeline | 只做 contract + 一个样例 |
| governance 字段引入 schema 迁移风险 | 数据库兼容性问题 | 优先用 metadata 扩展，不破坏旧字段 |
| REST 测试留下后台进程 | 本地端口污染 | 测试中显式启动/停止进程 |
| MCP 测试依赖真实 client | 验证脆弱 | 先测 handler/schema 层 |
| 深挖准入报告变成主观评价 | Phase 06 输入不可靠 | 使用抽样表格和明确评分维度 |
| 文档数字再次漂移 | 后续执行误判 | Phase 05 最后刷新 codebase map |

---

## PLANNING COMPLETE
