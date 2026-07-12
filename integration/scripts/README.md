# integration/scripts 布局

按领域**分包存放实现**；根目录 `*.py` 为**兼容入口 shim**（旧命令与测试仍可 `import xxx` / `python xxx.py`）。

## 包结构

| 包 | 职责 | 约略模块数 |
|----|------|-----------|
| `core/` | 路径、common、chroma、embed、规则、repository | 共享 |
| `knowledge/` | 知识单元抽取 / inventory / canonical / 索引 / gate / promote | ~18 |
| `memory/` | 记忆层构建、评估、晋升 | ~22 |
| `conversation/` | 会话摘要 / 图 / AgentView | ~15 |
| `graph/` | 关系候选 / 判定 / 三元组 | ~7 |
| `vector/` | 向量库、统一检索（knowledge-first）、评估 | ~5 |
| `services/` | REST API / MCP / dashboard（语义=知识混合；`/knowledge`） | 3 |
| `pipeline/` | 全量管道、导入、画像、schema | ~8 |
| `source_adapters/` | 源适配器 | 已有 |
| `examples/` | 接入示例 | 已有 |
| `_tools/` | 结构整理 / 测试缺漏审计等辅助脚本（非业务） | 3 |

## 调用方式

```powershell
# 兼容入口（推荐日常用，路径不变）
python integration/scripts/build_knowledge_units_prod.py --status run_xxx
python integration/scripts/unified_search.py --help

# 包路径（新代码可直接 import）
python -m knowledge.build_knowledge_units_prod --status run_xxx
from knowledge.build_knowledge_units_prod import process_run
from vector.unified_search import search_knowledge_units
```

## 设计说明

1. **实现**只在分包目录；根目录 shim 在 import 时 `sys.modules[__name__] = real_module`，测试可导入 `_private` 符号；CLI 调用 `main()`。
2. **run_pipeline** 仍按「脚本名.py」调用根目录入口，无需改步骤表。
3. 新增功能请写入对应包内，并用 `_tools/_fix_shims.py` 重生成 shim。
4. 包内模块 `ROOT = Path(__file__).resolve().parents[3]`（项目根）；勿再用 parents[2]。

## 测试

```powershell
python -m pytest tests -q          # 全量（当前 353 passed）
python -m pytest tests -k knowledge -q
python integration/scripts/_tools/_audit_test_gaps.py   # 刷新缺漏报告
```

测试缺漏（强引用/import 级，非 line coverage）：`integration/analysis/ai_context/test_coverage_gaps.md`

## 本轮移动

| 模块 | 包 | 状态 |
|------|----|------|
| `common` | `core` | moved+shim |
| `chroma_client` | `core` | moved+shim |
| `local_embed` | `core` | moved+shim |
| `rules` | `core` | moved+shim |
| `conversation_repository` | `core` | moved+shim |
| `memory_governance` | `core` | moved+shim |
| `knowledge_unit_pipeline` | `knowledge` | moved+shim |
| `build_knowledge_units` | `knowledge` | moved+shim |
| `build_knowledge_units_prod` | `knowledge` | moved+shim |
| `build_knowledge_inventory` | `knowledge` | moved+shim |
| `build_canonical_knowledge_units` | `knowledge` | moved+shim |
| `build_knowledge_unit_vector_store` | `knowledge` | moved+shim |
| `evaluate_knowledge_unit_extraction` | `knowledge` | moved+shim |
| `evaluate_knowledge_unit_rag` | `knowledge` | moved+shim |
| `evaluate_knowledge_canary` | `knowledge` | moved+shim |
| `promote_knowledge_index` | `knowledge` | moved+shim |
| `reconcile_knowledge_index` | `knowledge` | moved+shim |
| `refresh_knowledge_units` | `knowledge` | moved+shim |
| `rollback_knowledge_checkpoint` | `knowledge` | moved+shim |
| `migrate_add_knowledge_unit_tables` | `knowledge` | moved+shim |
| `build_pilot_sample` | `knowledge` | moved+shim |
| `build_pilot_report` | `knowledge` | moved+shim |
| `backfill_loop` | `knowledge` | moved+shim |
| `test_knowledge_unit_llm` | `knowledge` | moved+shim |
| `build_memory_store` | `memory` | moved+shim |
| `build_memory_graph` | `memory` | moved+shim |
| `build_memory_evidence_bundles` | `memory` | moved+shim |
| `build_memory_promotion_candidates` | `memory` | moved+shim |
| `build_memory_relation_candidates` | `memory` | moved+shim |
| `build_capability_memory` | `memory` | moved+shim |
| `build_preference_memory` | `memory` | moved+shim |
| `build_context_memory` | `memory` | moved+shim |
| `build_mem0_candidate_memory` | `memory` | moved+shim |
| `build_profile_from_memory` | `memory` | moved+shim |
| `build_deep_memory_profile` | `memory` | moved+shim |
| `extract_memory_candidates_from_bundles` | `memory` | moved+shim |
| `apply_memory_promotions` | `memory` | moved+shim |
| `repair_memory_promotion_candidates` | `memory` | moved+shim |
| `sync_memory_lifecycle` | `memory` | moved+shim |
| `audit_memory_experiments` | `memory` | moved+shim |
| `compare_memory_experiments` | `memory` | moved+shim |
| `analyze_memory_mechanisms` | `memory` | moved+shim |
| `evaluate_memory_depth` | `memory` | moved+shim |
| `evaluate_memory_promotion_candidates` | `memory` | moved+shim |
| `evaluate_memory_relation_candidates` | `memory` | moved+shim |
| `mine_deep_memory_graph` | `memory` | moved+shim |
| `build_conversation_segments` | `conversation` | moved+shim |
| `build_conversation_summary` | `conversation` | moved+shim |
| `build_conversation_graph` | `conversation` | moved+shim |
| `build_conversation_vector_store` | `conversation` | moved+shim |
| `build_conversation_eval_set` | `conversation` | moved+shim |
| `build_gpt_conversation_summary` | `conversation` | moved+shim |
| `build_agentsview_normalized` | `conversation` | moved+shim |
| `evaluate_conversation_prompt` | `conversation` | moved+shim |
| `evaluate_conversation_quality` | `conversation` | moved+shim |
| `evaluate_agent_conversation_cutover` | `conversation` | moved+shim |
| `query_conversation_graph` | `conversation` | moved+shim |
| `visualize_conversation_graph` | `conversation` | moved+shim |
| `rollback_agent_conversation_source` | `conversation` | moved+shim |
| `compare_summaries` | `conversation` | moved+shim |
| `patch_summary_meta` | `conversation` | moved+shim |
| `build_graph_relation_candidates` | `graph` | moved+shim |
| `build_graph_relation_candidates_v2` | `graph` | moved+shim |
| `judge_graph_relations` | `graph` | moved+shim |
| `evaluate_graph_relation_judgments` | `graph` | moved+shim |
| `query_graph` | `graph` | moved+shim |
| `build_triple_store` | `graph` | moved+shim |
| `build_merge_layer` | `graph` | moved+shim |
| `build_vector_store` | `vector` | moved+shim |
| `search_vectors` | `vector` | moved+shim |
| `evaluate_vector_collections` | `vector` | moved+shim |
| `evaluate_vector_retrieval` | `vector` | moved+shim |
| `unified_search` | `vector` | moved+shim |
| `api_server` | `services` | moved+shim |
| `mcp_server` | `services` | moved+shim |
| `dashboard` | `services` | moved+shim |
| `run_pipeline` | `pipeline` | moved+shim |
| `run_import_pipeline` | `pipeline` | moved+shim |
| `enrich_unified_events` | `pipeline` | moved+shim |
| `build_integrated_system` | `pipeline` | moved+shim |
| `build_deep_profiles` | `pipeline` | moved+shim |
| `build_context_doc` | `pipeline` | moved+shim |
| `dump_schema` | `pipeline` | moved+shim |
| `probe_codex_node` | `pipeline` | moved+shim |
