---
sketch: 002
name: sqlite-evidence
question: "只读 SQLite 查询的 SQL、结果与证据应在何处呈现，才能既可信又不打断对话？"
winner: "A"
tags: [sqlite, evidence, conversation, audit, desktop]
---

# Sketch 002: SQLite Evidence

## Design Question

在固定的 Codex 式双栏对话壳中，用户应如何看见一次受限 SQLite 查询的范围、SQL、结果、证据和限制？

## How to View

在浏览器打开 .planning/sketches/002-sqlite-evidence/index.html。

## Variants

- **A: 行内查询卡** — 查询元数据留在助手消息旁，适合逐段核对。
- **B: 右侧证据检查器** — 对话保持简洁，引用与 SQL 在按需展开的侧栏中查看。
- **C: 底部活动抽屉** — 把查询看作一次可追踪的开发工具活动，可浏览队列与失败状态。

## What to Look For

比较查证信息是否容易找到、对话是否仍保持可读，以及取消、空结果和错误状态是否足够清楚而不暗示模型拥有写权限。
