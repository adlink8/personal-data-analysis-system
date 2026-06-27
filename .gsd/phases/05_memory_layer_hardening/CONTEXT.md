# Phase 05: 记忆层补强与契约测试 - Context

**Gathered:** 2026-06-17
**Status:** Ready for planning
**Source:** Phase 04 execution results + external alignment review

<domain>
## Phase Boundary

Phase 05 不是继续扩展新功能，而是把 Phase 04 已打通的记忆层变成可维护、可验证、可防漂移的底座。

本阶段聚焦三件事：

1. 输入边界补强：明确 source adapter / canonical record 契约。
2. 记忆治理补强：让 memory item / relation 能解释来源、置信度和合并语义。
3. 消费入口测试：让 CLI / REST / MCP 对同一能力保持一致输出。
4. 深挖准入评估：证明当前记忆图谱已经具备进入 Phase 06 深层挖掘的证据质量。

</domain>

<decisions>
## Implementation Decisions

### Scope

- 本阶段优先补强和测试，不引入 dashboard、完整 GraphRAG、外部托管记忆服务。
- 保持本地优先架构：SQLite + Chroma + CLI/REST/MCP。
- 任何新增抽象必须先服务于现有 pipeline，不做空泛平台化。
- 只迁移或示范 1-2 个 adapter，不对 Google/GPT/Agent 全量重构。

### Testing

- 仓库当前没有正式测试目录，因此本阶段需要先建立轻量测试入口。
- 测试应覆盖真实本地数据路径，但不能依赖网络或外部服务。
- REST 测试可使用本地临时端口启动服务；MCP 测试优先测 handler/schema 层，避免强依赖外部 MCP client。
- 验证命令必须能在 Windows PowerShell 下复现。

### Memory Governance

- 记忆不应只有结论文本，应保留 `source`、`evidence`、`confidence`、`last_seen`、`source_hash` 或等价字段。
- profile 输出必须能解释关键结论来自哪些 memory item / relation。
- 不允许 LLM 在无证据链的情况下自动改写长期记忆。

### Depth Readiness

- 当前图谱的浅层输出是合理 demo，但不能直接当成深层洞察。
- 深挖前必须先验证每条候选洞察是否有证据链、时间跨度、重复出现、关系强度和反例检查。
- Phase 05 只建立深挖准入门槛，不实现复杂推理和洞察生成。
- Phase 06 只有在 depth readiness 通过后才执行。

### Transport Contract

- `unified_search.py` 是核心业务函数边界。
- `api_server.py` 和 `mcp_server.py` 应尽量只做 transport adapter。
- CLI/REST/MCP 的 memory 查询语义必须一致，至少覆盖 `type` 查询和 `subject + neighbors` 查询。

</decisions>

<canonical_refs>
## Canonical References

### Phase 04

- `.gsd/phases/04_memory_layer_upgrade/PLAN.md` — Phase 04 原始范围和架构目标。
- `.gsd/phases/04_memory_layer_upgrade/05-CONSUMPTION-LAYER-PLAN.md` — Wave 5 记忆消费层实际交付范围。
- `.gsd/phases/04_memory_layer_upgrade/RESEARCH.md` — 外部项目借鉴方向。

### Codebase Map

- `.planning/codebase/EXTERNAL_ALIGNMENT.md` — HPI/mem0/LangMem/mcp-memory-service/GraphRAG 对齐结果。
- `.planning/codebase/ARCHITECTURE.md` — 当前架构地图，需注意部分 Phase 04 Wave 5 后可能过期。
- `.planning/codebase/INTEGRATIONS.md` — 当前集成入口地图，需在本阶段后刷新。
- `.planning/codebase/TESTING.md` — 当前测试/验证现状。

### Implementation Entry Points

- `统合模块/脚本/run_pipeline.py` — 12-step pipeline 编排入口。
- `统合模块/脚本/unified_search.py` — CLI 和核心查询函数。
- `统合模块/脚本/api_server.py` — REST 入口。
- `统合模块/脚本/mcp_server.py` — MCP 入口。
- `统合模块/脚本/build_profile_from_memory.py` — 图谱记忆画像生成。
- `统合模块/分析数据/personal_system.sqlite` — 当前本地事实源。

</canonical_refs>

<specifics>
## Specific Ideas

- 新增 `统合模块/脚本/source_adapters/`，但第一阶段只放 contract 和一个样例 adapter。
- 新增 `统合模块/脚本/memory_governance.py` 或等价模块，集中处理 evidence/confidence/source_hash/merge_key。
- 新增 `统合模块/脚本/evaluate_memory_depth.py` 或等价脚本，抽样评估 memory graph 是否具备深挖条件。
- 新增 `tests/` 或 `统合模块/测试/`，优先选择简单可运行结构。
- 新增一个 contract test，验证核心函数、CLI、REST、MCP 对 memory 查询的 shape 一致。
- 更新 README 和 `.planning/codebase` 中过期的 endpoint/tool/pipeline 数量。

</specifics>

<deferred>
## Deferred Ideas

- Dashboard / HTML graph explorer。
- 完整 GraphRAG pipeline。
- 深层洞察生成和长期模式挖掘。
- 自动写入长期记忆的 hot path 工具。
- 远程 MCP / OAuth / 多用户权限。
- 全量 adapter 重构。

</deferred>

---

*Phase: 05-memory-layer-hardening*
*Context gathered: 2026-06-17*
