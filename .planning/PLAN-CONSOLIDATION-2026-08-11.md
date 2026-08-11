# 综合修复计划：数据污染 + 隐私 + 旧管线 + Wiki 转正

**创建**: 2026-08-11 | **状态**: executing | **执行方式**: 子 agent 分阶段

## 已确认的架构决策（用户）

1. **wiki 转正**：wiki 是最上层统合层，KU 是底层数据，SQLite 是事实数据；后台 agent 定期从 KU 统合更新 wiki；最上层直接检索 wiki，但保留访问底层数据能力（wiki 优先 + 底层可穿透）
2. **web 冻结**：先冻结不删，只停用入口
3. **先出方案再动手**（方案已确认，本计划即方案）

## 阶段清单

| 阶段 | 内容 | 优先级 | 状态 |
|------|------|--------|------|
| 0 | 压缩摘要污染修复（628 条 KU 伪事实） | P0 | pending |
| 1 | 隐私/脱敏（suite_tags、路径、敏感词、gitignore） | P0 | pending |
| 2 | 旧管线关闭（9 个死模块） | P1 | pending |
| 3 | Web 冻结（停用入口不删代码） | P1 | pending |
| 4 | Wiki 转正为统合层（依赖 0 的干净数据） | P1 | pending |
| 5 | 数据质量收口（conflict 16 条、L2 重复率） | P1 | pending |
| 6 | 功能主线（多轮记忆、projection、v2.0 Phase 53-60） | P2 | pending |

## 阶段 0：压缩摘要污染修复

**背景（实证）**：AgentView 源库 22 条压缩摘要（"This session is being continued from a previous conversation that ran out of context" / "was compacted. The summary below is the authoritative context"），20 条标 role=user → canonical 10 session 13 条 user 摘要 → 产出 628 条 KU（含大量真实路径 personal_fact）。

**任务**：
- 0.1 核查 628 条中 quote 直接来自摘要的占比
- 0.2 build_agentsview_normalized.py：识别压缩摘要，不再标 role=user，改标 source_type=compact_summary + evidence_scope=system
- 0.3 eligibility.py compute_eligible_messages：排除 evidence_scope=system
- 0.4 已污染 628 条标记 lifecycle=deprecated（不硬删，保留 lineage）
- 0.5 重跑 extraction_quality 验证

## 阶段 1：隐私/脱敏

- 1.1 suite_tags.json 40 条 query_preview 真实对话 → 合成摘要（文件被 6 工具引用，只改字段不改结构）
- 1.2 .planning/ 9 处 /home/li → ~/
- 1.3 build_preference_memory.py:113、phase15_wave0_investigate.py:56 敏感词中性化
- 1.4 .gitignore 加 latest_logs/
- 1.5 禁区：git 历史改写/force push 不做，停下报告

## 阶段 2：旧管线关闭

9 个模块引用已删路径（Agent/ GPT/ imports/）：run_import_pipeline、build_gpt_conversation_summary、build_conversation_segments、summary、enrich_unified_events、build_integrated_system、build_mem0_candidate_memory + domains/ 对应 + tools/compat/v1_1/。
处理：确认依赖后标 DEPRECATED 或移 archive；grep 旧路径归零（除 archive）。

## 阶段 3：Web 冻结

- 3.1 start-services.ps1 去掉 cockpit 托管段
- 3.2 api_server.py 停用 8 条 cockpit /ui/* 路由，保留 4 条 /ui/topic*
- 3.3 apps/personal_decision_cockpit/ 加 FROZEN.md
- 3.4 相关测试标记 skip

## 阶段 4：Wiki 转正（依赖阶段 0）

- 4.1 wiki 库增加正文表，统合结果落盘
- 4.2 新增后台统合任务：KU 增量 → subject 分桶 → 物化 wiki 页面
- 4.3 topic_projection.py 读时现算 → 读库正文
- 4.4 wiki.page/wiki.directory 成为统合检索入口；44 底层工具保留（可穿透）
- 4.5 knowledge.research skill 调整为先 wiki 后底层

## 执行约束

- 只改任务范围文件，不碰无关代码
- 不做 git 提交（除非用户明确要求）；不做 force push / git 历史改写
- 删除操作前先确认依赖；数据标记不硬删（保留 lineage）
- 每阶段完成后跑相关测试验证
- 遇到无法自行决策的偏离，停下回报主 agent
