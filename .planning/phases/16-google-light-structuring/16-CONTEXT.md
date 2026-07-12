---
phase: 16
name: google_light_structuring
status: executing
created: 2026-07-12
depends_on:
  - phases/15-retrieval-ssot-governance
---

# Phase 16 上下文：Google 轻量结构化

## Boundary

把 Google Takeout 活动从「仅 activities + raw 向量」提升为：

1. **normalized_events** 事件合同（可哈希、可批次回溯）
2. **google_light_assertions** 聚合级兴趣/服务信号（**非**对话式 knowledge_unit）

## Must / Must-not

| 做 | 不做 |
|---|---|
| 从 `activities` 幂等填充 `normalized_events` | 套用 `knowledge_unit_extractor` 对话 prompt |
| 主题/服务/频道/域名聚合断言 | Maps 地点轨迹当 personal_fact |
| 隐私分级：支付/地图等限制进入断言 | 写入 AgentsView |
| 保持 layered 检索 Google 分路 | 与 `cm|` 证据命名空间混用 |

## SSOT

- Google 活动原文/明细：`Google/structured/db/google_data.sqlite` → `activities`
- 规范化事件：`normalized_events`（`event_id` 前缀 `g|`）
- 轻断言：`google_light_assertions`（同库）
- 对话知识仍为 `canonical_knowledge_units`（`cm|`）

## Privacy tiers

| tier | 规则 |
|---|---|
| `aggregate_ok` | Search / YouTube / Gemini Apps / AI Mode 的主题与频次 |
| `restricted` | 支付/金融/卡类别；Maps 服务 — **可规范化事件，不进兴趣断言** |

## Success

- `normalized_events` 行数 ≈ eligible activities（幂等重跑）
- 断言表非空；报告 JSON 可审计
- 契约测试绿；文档更新 retrieval-ssot
