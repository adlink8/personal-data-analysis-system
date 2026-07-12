# Phase 16 候选：Google 轻量结构化（非本阶段交付）

## 现状（2026-07-12）

- `google_data.sqlite`：`activities` 1696、`gemini_attachments` 320、FTS 可用  
- `normalized_events`：**0 行**  
- 知识 inventory / KU：**未纳入**（证据全是 `cm|` 对话）  
- 仅进入 `unified_events` + `personal_events` raw  

## 为何不在 Phase 15 做全量 KU

1. 搜索/YouTube/Maps 行为日志 ≠ 用户第一人称断言  
2. 对话 extractor（preference/habit/…）prompt 不适用  
3. 隐私面更广（位置、支付相关 Takeout 模块）  
4. career-os 主价值当前在对话蒸馏的 KU  

## 若做 Phase 16，建议范围（草案）

| 做 | 不做 |
|---|---|
| 填 `normalized_events` 或等价事件合同 | 原样套用 knowledge_unit_extractor |
| 主题/服务级「轻断言」可选 | 把 Maps 轨迹当 personal_fact 无门禁入库 |
| 检索分路 `source=Google` 保持 | 与对话 evidence 混用同一 ref 命名空间不经设计 |

## 进入 Phase 16 的触发条件

- Phase 15 layered fallback 与 evidence 门禁已绿  
- I05 抽样 50 条确认有可结构化「偏好/兴趣」信号  
- 明确 privacy 规则（哪些 service 永不进知识层）
