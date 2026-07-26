# Phase 41 Discussion Log (--auto)

**Date:** 2026-07-26
**Mode:** --auto（全部灰色地带自动选定，推荐项）

## Areas auto-selected
1. assistant 轨 unit_type 与信任分级
2. ku| 世代归属
3. eligible 口径定义
4. 覆盖矩阵形态与告警级别
5. assistant 轨证据 gate

## Auto-selected decisions

- [auto] [双轨抽取] Q: "复用现有 6 类型还是独立集合？" → Selected: "独立 unit_type 集合（solution/decision_rationale/technical_conclusion）" (recommended default)
- [auto] [双轨抽取] Q: "确认信号作为硬 gate 还是修饰？" → Selected: "confidence/lifecycle 修饰，非硬 gate" (recommended default)
- [auto] [ku| 世代] Q: "重抽还是豁免？" → Selected: "显式豁免（grandfather），scope 重标即归属完成" (recommended default)
- [auto] [eligible 口径] Q: "assistant 是否进 eligible？" → Selected: "eligible 与 role 解耦，role 只决定轨；三方共用同一 eligible 函数" (recommended default)
- [auto] [覆盖矩阵] Q: "告警级别 FAIL 还是 WARN？" → Selected: "WARN 不 FAIL" (recommended default)

## Notes
- 依据来自 2026-07-25/26 数据层审计实测数据（见 CONTEXT.md specifics）。
- 无用户追加参考文档（auto 模式）。

## Deferred
- L2 疆域重定义 + L1 已知注入 prompt
- L2 窗口 12000→48000 + 长尾分块
- confidence 校准
- 1476 条 unresolved 孤儿 unit 处置
- canonical 同 subject 多 answer 组 lifecycle 审查
