# Phase 43 Watermark Note

## Delta 归因

Phase 42-03 记录的 `new_refs=1,995 / deleted_refs=12,496 / affected_subjects=8,100` 已归因：主要是 Phase 41 eligibility 收紧造成的口径变化（工具前缀与清洗后短消息），不是会话合并副本退出。42-03 的 user/assistant strict yield gate 分别为 0.0141 / 0.1381，未通过，因此历史 delta 当时没有被伪装成已消费。

## 43-08 分级与治理状态

历史快照 `personal_system_20260725T150456Z.sqlite` 复现 11,163 条目标记录。规则分档为 duplicate=11,150、noise_candidate=4、suspected_true_knowledge=9。疑似真知识 LLM 复核为 7 true_knowledge、2 noise；规则档 50 条抽样已经落盘，但人工逐条误判清单尚未完成。

当前 unified DB 已将历史 ID 转为 current/rejected，不能直接按历史 staging 提案写入。43-09 dry-run 台账为 `var/reports/analysis/triage_disposition_plan_20260728T014200Z.json`；supersede 223 批、deprecate 1 批，全部标记为 stale-snapshot skip，未 register/apply。

## 索引重建时机

本次未执行向量索引重建。只有治理处置完成、canary strict PASS、并由 promote 流程确认后，才重建 active collection。

## Watermark 推进记录

user 轨 dry-run：`87e24e2aa2e9f167989b4e4724ae9cd3 → ae44b63925e52663755c16808432a4d9`；assistant 轨 dry-run 无变化。两轨 preconditions 均显示无 unfinished/failed item。由于历史目标尚未完成真实人工治理确认，本次不执行 `--write`，避免用 watermark 掩盖未完成的处置链；因此 Phase 43 整体保持 partial，后续应先完成当前库状态对账和人工批次裁定。
