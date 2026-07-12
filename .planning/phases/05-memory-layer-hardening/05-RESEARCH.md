# Phase 05 Research: Hardening and Contract Testing

Status: Done
Date: 2026-06-17
Basis: `.gsd/phases/04_memory_layer_upgrade/RESEARCH.md` and `.planning/codebase/EXTERNAL_ALIGNMENT.md`

## Research Summary

Phase 05 不需要重新选择技术栈。前一轮对 HPI / mem0 / LangMem / mcp-memory-service / GraphRAG 的调查已经给出明确方向：当前仓库应借鉴模式，而不是引入完整外部平台。

## Borrowed Patterns

| Source | Pattern for Phase 05 | Local interpretation |
| --- | --- | --- |
| HPI | Source modules expose stable typed objects | 定义 source adapter contract，先迁移一个样例 |
| mem0 | Memory levels and memory search API | 明确 memory type/level，补 governance metadata |
| LangMem | Hot path tools vs background manager | Phase 05 先做 background 结果可解释，不做自动写入 |
| mcp-memory-service | One backend, multiple transports | 核心函数/CLI/REST/MCP 做 contract tests |
| GraphRAG | Relation evidence and graph context packing | 保持轻量 graph query，先测 relation 质量和可解释性 |

## Standard Stack

- Python stdlib + existing dependencies first。
- SQLite remains the source of truth。
- Chroma remains vector search, but Phase 05 不新增向量能力。
- pytest can be introduced only if it is added to `requirements.txt` or already available；否则先用 stdlib `unittest`/scripts级 smoke tests。
- REST tests should run against localhost only。

## Architecture Constraints

- 不新增外部服务。
- 不引入 LangGraph/mem0/GraphRAG 作为 runtime dependency。
- 不大规模重构 `build_integrated_system.py`。
- 不让测试依赖非确定性 LLM 输出。
- 不在无认证情况下开放远程服务。

## Planning Implication

Phase 05 应拆成 4 个 wave：

1. Adapter contract skeleton。
2. Memory governance metadata。
3. Transport contract tests。
4. Documentation and codebase map refresh。

## Source References

- HPI: https://github.com/karlicoss/HPI
- mem0: https://github.com/mem0ai/mem0
- LangMem: https://github.com/langchain-ai/langmem
- mcp-memory-service: https://github.com/doobidoo/mcp-memory-service
- Microsoft GraphRAG: https://github.com/microsoft/graphrag

