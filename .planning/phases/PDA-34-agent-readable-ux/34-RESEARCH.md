---
phase: 34
status: complete
created: 2026-07-19
---

# Phase 34 Research

## Existing Assets

- `DecisionIntelligenceReadService` 已有 schema-versioned success/error envelope，但默认会携带完整 `data`。
- `GuardedOrchestrationInterface` 已有 typed code 和限制，但缺统一 summary、evidence links、retryability 与恢复提示。
- ChatGPT Node adapter 当前为读面和编排面分别构造摘要，存在语义漂移风险。
- `privacy_guard` 已能封存 credentials/PII/敏感字段，可作为 compact contract 的最终出口。

## Selected Design

建立纯函数 `AgentCompactContract`：

1. 从共享 service envelope 投影稳定 ID、evidence links 和安全限制。
2. 使用集中错误目录决定分类、retryability 和 allowlisted recovery actions。
3. 在序列化预算内保留 detail；超预算递归裁剪为稳定引用和核心状态。
4. REST/stdio helper 返回相同 projection；ChatGPT Node 不再推断 authority 语义，只透传 compact fields。

## Risks

- 裁剪导致关键限制丢失：限制、错误、下一步和 evidence links 属于不可裁剪核心。
- checksum 被隐私规则误封：checksum/id 字段在现有 deny-list 中明确保留。
- recovery action 诱导危险重试：集中目录对 unknown provider outcome、risk 和 integrity 错误标记不可重试。
- 旧调用方依赖原 envelope：底层 service `invoke` 保持不变，新增 `invoke_compact`/transport projection。
