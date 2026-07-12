---
phase: 05.5
name: ponytail_project_optimization
title: Ponytail 项目瘦身与最小化优化
status: Completed
created: 2026-06-18
depends_on:
  - .gsd/phases/05_memory_layer_hardening/EXECUTION.md
autonomous: false
---

# Phase 05.5: Ponytail 项目瘦身与最小化优化

## Objective

在 Phase 06 深层图谱挖掘开始前，用 Ponytail 原则对当前项目做一次最小化优化：删除不必要复杂度、压低过度抽象、收口重复逻辑、保留必要验证。

## Scope

- 只优化现有代码，不新增业务能力。
- 优先删减、合并、简化；不为了“架构感”新增层。
- 不改 Phase 05 已完成状态。
- 不动raw和已验证输出，除非发现明确错误。

## Ponytail Rules

- 标准库优先，已有依赖优先，不新增依赖。
- 一个实现够用时，不新增 interface/factory/plugin 点。
- 删除优先于新增。
- 每个非平凡改动必须保留一条最小可运行验证。
- 改动后 Phase 06 的输入契约不能变差。

## Tasks

1. 审查当前高复杂度文件：
   - `integration/scripts/unified_search.py`
   - `integration/scripts/api_server.py`
   - `integration/scripts/mcp_server.py`
   - `integration/scripts/run_pipeline.py`
   - `integration/scripts/*memory*.py`
2. 找出并处理：
   - 未使用代码
   - 重复转换逻辑
   - 过度包装的 helper
   - 无必要配置
   - 可用标准库替代的小工具逻辑
3. 不做大型重构；每次改动必须能用现有测试或 smoke command 验证。
4. 输出 `EXECUTION.md`，记录删了什么、保留了什么、为什么没继续优化。

## Verification

```powershell
python tests\test_memory_contracts.py
python integration\scripts\run_pipeline.py --dry-run
python integration\scripts\unified_search.py memory --subject Codex --neighbors 1
python integration\scripts\evaluate_memory_depth.py
git diff --check
```

## Success Criteria

- 没有新增外部依赖。
- 没有破坏 Phase 05 contract tests。
- Phase 06 依赖的 `memory_depth_readiness.md` 仍可生成。
- 至少清理一个真实复杂度来源；如果没有可安全清理项，`EXECUTION.md` 明确说明。

## Out of Scope

- 深层图谱挖掘实现。
- 图数据库接入。
- LLM 提炼层接入。
- dashboard。

---

## PLANNING COMPLETE
