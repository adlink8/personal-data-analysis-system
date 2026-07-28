# Phase 43: L2 Scope Redefinition (Cross-turn State Ownership and Incremental Dedup) - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-27
**Phase:** 43-l2-scope-redefinition-cross-turn-state-ownership-and-increme
**Areas discussed:** 注入机制（L2G-01）、状态类清单与 L1 拦截（L2G-02）、当前值视图落点（L2G-03）、存量分级与 watermark（L2G-04）

---

## 注入机制（L2G-01）

| Option | Description | Selected |
|--------|-------------|----------|
| subject 归一化精确匹配为主 + embedding top-k 兜底 | 零成本确定性主路径，embedding 只补表述漂移 | ✓ |
| 纯 embedding top-k | 召回率高但非确定性进主路径，eval/复现添噪 | |
| 纯 subject 精确匹配 | 最简单但漏表述漂移 | |
| 双 LLM 二次确认等价 | 成本翻倍，治理批人工检视已是防线 | |

**User's choice:** 确认推荐方案（用户指令"四个领域最合适的点"→ 我出推荐，用户"确认"锁定）
**Notes:** 注入上限 20 条 / answer 截 200 字符；LLM 只输出 `duplicate_of` 标注（限注入清单内 id），落 staging 为 supersede 候选，治理批裁定生效。

## 状态类清单与 L1 拦截（L2G-02）

| Option | Description | Selected |
|--------|-------------|----------|
| 种子手工清单 + LLM 聚类建议扩充（人工确认） | 纯人工漏长尾、纯自动进噪音，两害相权最轻 | ✓ |
| 纯手工清单 | 漏长尾 | |
| 纯 LLM 自动清单 | 进噪音 | |
| L1 命中即跳过 | 不可逆信息损失，误判直接丢 | |
| L1 命中降 candidate | 保留人工转正通道，误杀成本趋零 | ✓ |

**User's choice:** 确认推荐组合
**Notes:** 清单落 `assets/` yaml；归一化精确 + 前缀规则匹配，不上 embedding；L2 对清单内 subject 负全责。

## 当前值视图落点（L2G-03）

| Option | Description | Selected |
|--------|-------------|----------|
| CLI 两落点：`pk-ku history --subject` 扩展 + `rag-search --current-only`/降权 | canonical lifecycle 语义做对，projection 后续自然消费 | ✓ |
| Cockpit 新 projection 端点 | 跨 v1.4/v1.5 phase 疆域伸手 | |

**User's choice:** 确认 CLI 方案
**Notes:** 不新增 schema 字段（SPEC L2G-03 已锁）。

## 存量分级与 watermark（L2G-04）

| Option | Description | Selected |
|--------|-------------|----------|
| 规则初分 + 疑似真知识子集 LLM 复核 + 规则档抽样验证 | 全量 11k LLM ≈18h 不值；子集估 2–4k 可接受 | ✓ |
| 全量 LLM 分级 | ~18h @6s/条，成本不值 | |
| 一刀切 deprecate | 42-03 已 STOP：重复率仅 2%，会埋真知识 | |
| 处置完即推进 watermark | delta 已归因，挂起无信息量且 Gate B 带噪 | ✓ |
| 保守挂起到 43 全部验收 | 持续污染 inspect Gate B | |

**User's choice:** 确认推荐组合
**Notes:** 转正前必须 re-match quote 到现存 eligible 消息（复用 41 重链接逻辑）；match 不上走 candidate/deprecate；处置与推进全进 manifest 链。

---

## the agent's Discretion

归一化规则细节、embedding k 值与阈值、注入段 prompt 文案与位置、yaml schema、规则档特征阈值、LLM 复核 prompt、批次编排（≤50/批铁律内）、执行笔记格式。

## Deferred Ideas

- Google 数据源知识单元化 — 独立 phase，用户点名关注
- QA v2 abstain prompt 约束 — 41 deferred ⑩
- 47 个超长 L2 会话分块重抽 run — 41 deferred（代码已落地，成本决策）
- Cockpit 消费"当前值"语义的 projection 端点 — v1.4 验收/v1.5 衔接
- 注入命中率/拦截量指标进 doctor — 视首轮 run 数据决定
