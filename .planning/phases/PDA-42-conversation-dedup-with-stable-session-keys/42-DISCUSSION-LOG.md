# Phase 42 Discussion Log (--auto)

**Date:** 2026-07-26
**Mode:** --auto（全部灰色地带自动选定，推荐项）

## Areas auto-selected
1. 稳定身份键设计
2. 存量双份清理策略
3. 内容增长的合并方式
4. legacy 代表行确定性

## Auto-selected decisions

- [auto] [身份键] Q: "稳定键用什么？" → Selected: "(source, source_session_id) 复合键，file_hash 仅作变更检测" (recommended default)
- [auto] [合并方式] Q: "更新时全量替换还是增量合并？" → Selected: "消息级增量合并，保 evidence ref 稳定" (recommended default)
- [auto] [存量双份] Q: "直接删还是标 superseded？" → Selected: "标 superseded + ref 映射，不硬删" (recommended default)
- [auto] [确定性] Q: "legacy 代表行漂移怎么修？" → Selected: "确定性 ORDER BY（started_at, 路径）" (recommended default)

## Deferred
- canonical 发布崩溃窗口（M4）
- parent_canonical_id 回填 / legacy session_relations（L3）
- timestamp 格式混存（L2）
