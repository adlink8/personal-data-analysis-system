# Phase 06 Research: Deep Memory Graph Mining

Status: Planned
Date: 2026-06-17
Basis: Phase 04 external research and Phase 05 depth readiness design

## Research Summary

Phase 06 的关键不是换框架，而是把当前本地 memory graph 增加“深度评估和洞察生成”能力。外部项目的启发如下：

| Source | Relevant idea | Local use |
| --- | --- | --- |
| HPI | 个人数据要先以稳定对象暴露，才能可靠分析 | Phase 06 只消费 Phase 05 标准化后的 memory/evidence |
| mem0 | 长期记忆需要跨会话积累和召回 | 用 recurrence/time_span 判断记忆是否稳定 |
| LangMem | 后台记忆管理比交互时即兴总结更可靠 | 深层洞察走离线 pipeline，不在查询时即兴生成 |
| mcp-memory-service | 共享记忆应有实体、关系、因果知识图谱 | 增强 relation strength 和 contradiction checks |
| GraphRAG | 图结构能增强全局/局部问题回答，但索引成本高 | 不引入完整 GraphRAG，先做轻量主题簇和关系摘要 |

## Depth Model

深层洞察至少需要五类证据：

1. Evidence: 有可回溯来源，不是裸结论。
2. Recurrence: 多次出现，而不是一次性事件。
3. Time span: 跨时间成立，能观察演化。
4. Relation strength: 与其他实体的关系有权重或置信度。
5. Contradiction check: 能标记冲突、衰减、过时或反例。

## Insight Scoring

建议用可解释打分，而不是黑盒 LLM 判断：

| Field | Meaning |
| --- | --- |
| `evidence_count` | 支撑该洞察的 memory/event 数量 |
| `time_span_days` | 最早和最晚证据的时间跨度 |
| `relation_count` | 相关实体关系数量 |
| `relation_strength_avg` | 平均关系置信度或权重 |
| `contradiction_count` | 冲突或反例数量 |
| `confidence_level` | strong/moderate/weak/unsupported |

## Output Contract

Phase 06 的输出不应只是自然语言总结。每条洞察至少包含：

- `insight_id`
- `title`
- `claim`
- `confidence_level`
- `evidence_items`
- `related_entities`
- `time_window`
- `contradictions`
- `why_it_matters`
- `profile_action`: include / review / exclude

## Pitfalls

- 把高频词当成深层兴趣。
- 把工具使用次数当成能力强度。
- 忽略时间衰减，导致过时偏好继续影响 profile。
- 忽略反例，把矛盾行为强行合并成单一标签。
- 用 LLM 直接概括，没有保留证据链。

## Source References

- HPI: https://github.com/karlicoss/HPI
- mem0: https://github.com/mem0ai/mem0
- LangMem: https://github.com/langchain-ai/langmem
- mcp-memory-service: https://github.com/doobidoo/mcp-memory-service
- Microsoft GraphRAG: https://github.com/microsoft/graphrag

