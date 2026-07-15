---
phase: 17
status: complete
type: local-eval-architecture-research
---

# Phase 17 Research

## Recommendation

复用现有 Python、SQLite、Chroma 与 JSON evaluator，不引入 LangChain/LlamaIndex 或托管 tracing。建立一个薄的 eval harness：adapter 负责五种模式，scorer 负责统一指标，registry 负责不可变 run，reporter 负责 HTML/PNG，gate 负责发布决策。

## Reuse

- `evaluate_knowledge_unit_rag.py`：已有 Raw/KU 指标模式。
- `phase15_02_holdout_eval.py`：layer telemetry 与 abstain 观察。
- `compare_l1_l2_retrieval.py`：A/B 与图表原型，但需去硬编码并移除 Desktop 副作用。
- `promote_knowledge_index.py`：active/previous/rollback journal。
- `canonical_messages`、`canonical_knowledge_units`、Chroma collections：事实与检索面。

## Critical pitfalls

1. 不同数据集、match rule、top-k 的数字不能直接宣称为阶段提升。
2. lexical snippet 命中会造成数据泄漏式高分，必须区分 exact-evidence 与 paraphrase。
3. L2-only collection 不存在时，需从 canonical members/merge_reason 构建隔离 candidate，不可把 L1+L2 当 L2-only。
4. LLM judge 若未和人工标签校准，不得作为 hard gate。
5. eval 必须只读 active；失败不得留下 pointer、canonical status 或 collection 变化。

