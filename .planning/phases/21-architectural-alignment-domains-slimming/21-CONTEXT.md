# Phase 21: Architectural Alignment - Domains Slimming - Context

**Gathered:** 2026-07-14
**Status:** Ready for planning

<domain>
## Phase Boundary

把 `src/personal_knowledge/domains/` 下 63 个 build/eval 脚本(29 个 build_*.py + 10 个 evaluate_*.py + 4 个 compare/analyze/audit)按 `governance/policies/architecture.yaml` 的分层规则归位到 `application/`(build 编排)和 `evaluation/`(评测),删除已确认的死代码,并消除跨域中心节点耦合。完成后 domains/ 只剩纯 domain 规则/模型/常量。

**承上启下:** 这是「架构对齐重组」的阶段 2。阶段 1(已完成)用 facade 模式拆了 retrieval/unified_search.py(3221 行 → 7 模块 + facade),本阶段把同样手法应用到 domains 层。

**In scope:**
- 删 `domains/graph/build_graph_relation_candidates_v2.py`(死代码)
- 拆 `domains/conversation/build_conversation_summary.py` → LLM helper 下沉 core/,build 编排移 application/conversation/
- 按子域(conversation→graph→knowledge→memory)批次迁移 build 脚本到 application/{子域}/
- 按 eval/compare/analyze/audit 类型迁移到 evaluation/{子域}/
- retrieval 层遗留的 4 个 eval/compare 脚本迁到 evaluation/
- 所有迁移在 domains/ 原位置留 re-export facade(保留 30 天)
- 更新 7 个跨域 caller 的 import
- 更新 `governance/policies/architecture.yaml` + domains 各 `__init__.py` docstring

**Out of scope:**
- 删 `.bak-phase20` 6GB 备份(等 2026-08-13 窗口期,属阶段 3)
- 扩大 L2 抽取、换 embedding/model(Phase 17 范畴)
- 写 live AgentsView
- 重写 build 脚本的内部逻辑(只搬位置,不改行为)
</domain>

<decisions>
## Implementation Decisions

### 中心节点处理(LLM 调用原语)
- **D-01:** `build_conversation_summary.py` 拆分——LLM 调用原语下沉到 `core/llm.py`(共享库层),build 编排逻辑移到 `application/conversation/summary.py`。
- **D-02:** 6 个跨域 peer(graph/judge_graph_relations, memory/build_memory_relation_candidates, memory/compare_memory_experiments, memory/extract_memory_candidates_from_bundles, memory/repair_memory_promotion_candidates, conversation/build_gpt_conversation_summary)+ 1 sibling(conversation/build_conversation_eval_set)的 import 改指向 `core.llm`。

### 迁移节奏
- **D-03:** 按子域分 4 批迁移,顺序 conversation → graph → knowledge → memory。每批迁完跑全量测试作为守门。每批可独立验证/回滚。
- **D-04:** 每批内,先迁 build 脚本,再迁 evaluate/compare 脚本,保持子域内聚。

### 死代码与向后兼容
- **D-05:** `build_graph_relation_candidates_v2.py` 直接删,不留 shim(已确认死代码:src/tests/apps 0 引用,且其内部 import 路径写错 `from conversation` 非 `from personal_knowledge.domains.conversation`)。
- **D-06:** 所有迁移的 build/eval 脚本在 domains/ 原位置留 re-export facade(`from ...new_path import *` 模式,与阶段一 unified_search facade 一致)。facade docstring 标注「保留至 2026-08-13 后清理」。
- **D-07:** facade 必须重新导出所有公开符号(函数/类/常量),保证 caller 的 `from ...domains.X.build_Y import Z` 零改动。

### 验收标准
- **D-08:** 三重门禁:(1) `python -m pytest tests/ -q` 全过(允许与当前基线相同的 17 个已知 fail);(2) `governance/preflight --ci` 通过;(3) REST :8000 + MCP :8789 健康端点 200。

### the agent's Discretion
- core/llm.py 的具体拆分边界(LLM 调用原语 vs build 编排)由 plan 阶段据代码实际决定。
- evaluation/{子域}/ 的子目录结构(conversation/graph/knowledge/memory 各建子目录还是平铺)由 plan 据文件数决定。
- retrieval 层 4 个 eval/compare 脚本迁到 evaluation/ 的具体子目录归属。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 架构策略(分层规则来源)
- `governance/policies/architecture.yaml` — **MUST READ**。定义 6 层(foundation/infrastructure/domain/application/evaluation/delivery/control)及 modules 段。line 17-24 是各模块的 layer 与 may_import 约束;line 28-31 明确禁止 domain 层 import application/evaluation(当前违例根源)。
- `docs/architecture/` — SSOT 文档目录(plan 阶段需确认 repository-zones.md 现状)。

### 前序阶段先例(facade 模式范本)
- `src/personal_knowledge/retrieval/unified_search.py` — 阶段一 facade 范本,re-export 拆分模块的公开符号。本阶段 domains facade 照此模式。
- `src/personal_knowledge/retrieval/_constants.py` — 路径常量 SSOT 范本。

### 迁移登记与治理
- `integration/scripts/README.md` — 历史迁移登记表(含 v2 标记行)。
- `governance/manifests/source_migration.json` — 物理源迁移清单(plan 阶段需用 `source_manifest.py --cohort all` 重建以反映新位置)。

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- **retrieval facade 模式**:`unified_search.py` 已证明 re-export facade 能让 caller 零改动。本阶段每个迁移的 build 脚本照搬此模式。
- **governance preflight**:`governance/preflight --ci` 是现成的分层违例检测器,每批迁移后即跑。
- **source_manifest.py**:`--cohort all` 重建物理源清单,迁移后必须重跑以保持治理清单一致。

### Established Patterns
- **路径常量 SSOT**:子模块通过 `_C.UNIFIED_DB`(模块属性访问)而非值绑定读取路径常量,使 monkeypatch 生效。本阶段若引入新的路径常量,照此模式。
- **lazy import 收敛违例**:retrieval/memory.py 仍有 3 处对 domains.graph 的 lazy import(阶段一隔离,未消除)。本阶段重组 domains 时顺带评估是否消除。

### Integration Points
- **跨域中心节点**:`build_conversation_summary.py` 被 7 个跨域 peer import,是本阶段最复杂的拆分点。拆分后 6 个 peer 改 import 指向 core/llm。
- **subprocess 路径**:调研确认 domains/ 和 application/ 无硬编码路径字面量(仅 `run_pipeline.py` 用 `__file__` 推导 ROOT),迁移无进程层耦合。
- **__init__.py 定位**:4 个子域 __init__.py docstring 都写 "integration scripts",迁移后需改为各自子域职责说明。

</code_context>

<specifics>
## Specific Ideas

- 用户明确偏好「可控破坏」(架构对齐风险偏好已确认):允许在迁移过程中短暂破坏,但每批必须有测试守门和回滚能力。
- 用户要求 facade 保留 30 天后清理(与 .bak-phase20 窗口期对齐),避免永久债务。
- 迁移顺序 conversation→graph→knowledge→memory 的依据:conversation 是被依赖最多的中心域,先迁它能让后续 graph/memory 的 import 改动更早稳定。

</specifics>

<deferred>
## Deferred Ideas

- **消除 retrieval/memory.py 的 3 处 domains.graph lazy import**(阶段一隔离的分层违例):完整消除需要把 graph 查询下沉或反转依赖,属较大改动。留到 domains 重组完成、依赖图稳定后单独评估。
- **删 .bak-phase20 6GB 备份**:等 2026-08-13 窗口期(阶段 3),不在本 phase。
- **domains/ LOC 硬指标**(如 <5000 LOC):讨论时未选,避免某子域规则文件过大卡住交付。
- **conversation/__init__.py 等的 docstring 重写为子域职责说明**:已在 In scope,但具体措辞由 execute 阶段定。

</deferred>

---
*Phase: 21-Architectural Alignment - Domains Slimming*
*Context gathered: 2026-07-14*
