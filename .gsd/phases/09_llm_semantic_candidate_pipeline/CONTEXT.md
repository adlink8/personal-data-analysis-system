---
phase: 09
name: llm_semantic_candidate_pipeline
title: LLM 语义候选生成与直通证据链删除
status: Discussed
created: 2026-07-01
depends_on:
  - .gsd/phases/08_memory_experiment_consolidation/PLAN.md
  - integration/analysis/ai_context/memory_mechanism_matrix.md
  - integration/analysis/ai_context/memory_pipeline_target_design.md
  - integration/db/personal_system.sqlite
---

# Phase 09 Context: LLM 语义候选生成与直通证据链删除

## User Correction

用户明确指出两条 Phase 08 后仍不理想的机制：

1. 图谱候选生成不能只靠脚本、向量 top-k、相邻 turn。LLM 应参与候选生成，因为只有 LLM 才能判断语句之间可能是什么关系，以及这种关系是否值得进入候选层。
2. `legacy_evidence_candidate` 第二路逻辑应直接删除，不再保留。旧 `memory_items` 不能再作为 promotion candidate 的入口。

因此 Phase 09 的核心不是继续“对旧机制做兼容”，而是扩大 LLM 的参与范围，把语义候选生成从脚本规则中拿出来。

## Current Problem

当前图谱链路：

```text
conversation_turns
-> build_graph_relation_candidates.py
   - semantic_candidate: Chroma vector top-k
   - temporal_candidate: same-session adjacent turns
-> graph_relation_candidates
-> judge_graph_relations.py
-> graph_relation_judgments
-> evaluate_graph_relation_judgments.py
-> accepted/review/rejected
```

问题：

- `graph_relation_candidates` 的候选 pair 由脚本和向量产生，LLM 只在后面判边。
- 向量相似只能说明“文本可能相近”，不能说明“关系是什么”。
- 相邻 turn 只能说明“时间上相邻”，不能说明“语义上是否有因果、补充、冲突、偏好信号”。
- 这会让候选层缺少关系意图，后续 LLM 判边只能在脚本给出的 pair 上工作，召回边界偏浅。

当前 promotion 候选链路：

```text
graph_relation_judgments accepted
-> graph_relation_candidate
-> memory_promotion_candidates

memory_items
-> memory_links
-> unified_events_rich
-> legacy_evidence_candidate
-> memory_promotion_candidates
```

问题：

- `legacy_evidence_candidate` 仍以旧 `memory_items` 作为候选入口，即使标注为 historical reference，也会把第一代规则实验结果带进新主线。
- 结构化 evidence 不应直接成为候选；它应先被组装成 evidence bundle，再由 LLM 重新提炼 candidate claim。

## Locked Decisions

1. 删除 `legacy_evidence_candidate` 入口。
   - `memory_items` 只能作为冲突/重复检查对象。
   - `memory_items` 不能作为新候选生成源。

2. 删除“脚本结构化 evidence 直接进入候选”的链路。
   - `unified_events_rich` / `memory_links` 可以作为证据来源。
   - 但它们必须先进入 evidence bundle。
   - evidence bundle 必须经过 LLM candidate extractor 才能形成 `memory_promotion_candidates`。

3. 图谱候选生成加入 LLM。
   - 脚本负责 coarse recall：向量 top-k、时间邻近、同主题、工具共现。
   - LLM 负责 semantic candidate proposal：判断 pair 是否值得进入候选，以及候选关系类型、理由、证据 refs。
   - 脚本再做 schema/evidence/duplicate gate。

4. Gate 失败要可反馈给 LLM。
   - gate 不只是 reject，也要输出 failure reasons。
   - LLM repair loop 只能基于已有 evidence_refs/source_refs 修复、降级或拒绝，不能编造证据。

5. 自动入库只能发生在加权评分之后。
   - LLM 不直接写 `memory_items`。
   - 脚本计算 score，硬风险一票否决。
   - 自动 apply 只允许处理 `approved && human_review_required=false`。

## Desired Pipeline

```text
raw events / conversations
-> deterministic parsing and source refs
-> turn-level LLM compression
-> vector store conversation_turns
-> script coarse recall packages
-> LLM graph candidate proposal
-> graph candidate schema/evidence gate
-> LLM relation judgment
-> graph evidence gate + repair loop
-> accepted graph analysis layer
-> evidence bundles
-> LLM memory candidate extraction
-> promotion evidence gate + weighted score
-> human review or auto-approved
-> controlled apply to long-term memory
```

## Scope Boundary

Phase 09 changes candidate generation mechanics. It should not delete or rewrite the existing long-term memory store.

- Allowed:
  - Add new prompts for LLM graph candidate proposal and memory candidate extraction.
  - Add new scripts or v2 scripts that run beside current scripts.
  - Remove `legacy_evidence_candidate` from the active promotion candidate builder.
  - Add tests that assert no candidate has `source_system='legacy_evidence_candidate'`.
  - Add feedback loop report fields.

- Not allowed:
  - Directly delete `memory_items`, `memory_links`, or `memory_relations`.
  - Let LLM write SQLite directly.
  - Auto-apply without score gate and hard-risk gate.
  - Use old `memory_items` as candidate source.
  - Treat vector similarity as truth.

## Success Shape

Phase 09 succeeds when:

- Graph candidate generation includes an LLM proposal step.
- Promotion candidates no longer include `legacy_evidence_candidate`.
- Evidence bundles become the only path from structured data into memory candidate extraction.
- Gate failure reasons can be fed back into an LLM repair loop.
- Long-term memory tables remain unchanged unless an explicit approved apply path is tested in dry-run.
