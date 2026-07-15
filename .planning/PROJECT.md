# 个人数据分析项目

## What This Is

这是一个 Windows 本地优先的个人数据系统，把 Google、GPT、Agent 与 AgentView 的数字足迹转换为可持续追加、可查询、可追溯的统一数据、记忆和知识层。系统同时提供 CLI、REST、MCP、可视化与 RAG 消费接口。

## Core Value

把个人历史转换为隐私安全、证据可回查、能够持续增量学习的外部知识系统。

## Current Milestone: v1.1 Knowledge Unit Evaluation & Quality

**Goal:** 建立统一、可复跑、可视化、可阻断发布的知识单元全面评测闭环，量化 Raw、L1、L2、L1+L2、Hybrid 与最终 RAG 回答之间的真实提升。

**Target features:**
- 同一冻结协议下的五路检索 A/B 与分场景指标
- L2 跨轮增益、重复、冲突、隐私与时效质量评测
- 最终回答正确性、忠实度、引用与 abstain 评测
- candidate → eval gate → canary → promote/rollback 发布闭环
- JSON/SQLite 历史记录与本地 HTML/PNG 可视化报告

**Previous:** v1.0 completed 2026-07-12（Phases 01–16；Phase 08 cancelled）。见 [MILESTONE-v1.0.md](MILESTONE-v1.0.md)。

## Requirements

### Validated (v1.0)

- ✓ 三源增量导入、统一事件、增强与去重管道 — Phase 01-03
- ✓ 结构化记忆、记忆图谱和语义候选层 — Phase 04-10（实验层保留，非知识 SSOT）
- ✓ MCP、Apps SDK、REST 与统一数据访问接口 — Phase 11-12
- ✓ 公共基础层重构和 canonical AgentView 会话证据层 — Phase 13-13.5
- ✓ 知识单元 RAG：30,012 active + KU-01..08 增量 journal/watermark — Phase 14
- ✓ 检索三层 SSOT + layered hybrid + telemetry + holdout — Phase 15
- ✓ Google 轻量结构化 lifecycle + RO consumer — Phase 16
- ✓ 工程结构重整：闲置模块 `_recycle/`；scripts 领域分包 + 兼容 shim
- ✓ Phase 08 取消（MEMX-01 wontfix）

### Optional backlog (not Active)

- 真实源增量付费 promote；非主路径测试覆盖补齐  
  — 见 ROADMAP § Optional Next

### Out of Scope

- 直接修改 AgentView live database — 它只作为只读上游
- 删除 raw events、legacy 数据库或旧 Chroma collection — 必须保留回滚与追溯
- 让 LLM 输出绕过 schema、evidence、privacy 和 evaluation gate — 所有 AI 产物先进入 staging
- 在核心管道引入大型 Agent/RAG 编排框架 — 优先使用现有 Python、SQLite 和轻量接口
- 硬删除 `_recycle/` 归档（仅软归档；恢复靠 MANIFEST）

## Context

- 项目根目录默认运行环境是 Windows + PowerShell（工作区可为 `D:\ADLINK\数据分析` 等）。
- **源码布局（Phase 19–21）：** `src/personal_knowledge/`  
  - `core/` 基础（含 `llm.py`）  
  - `domains/*/` 规则/模型/常量 + facade（清理窗口 2026-08-13）  
  - `application/*/` **canonical build/lifecycle**  
  - `evaluation/*/` **canonical eval**（含 `evaluation/vector/`）  
  - `retrieval/` 向量/检索 I/O；`services/` REST/MCP  
- **数据/运行时（Phase 20）：** `data/`、`var/`、`archive/`；AgentsView live 仍为 protected-external。
- 核心统合库：`var/db/personal_system.sqlite`；对话 SSOT：`data/canonical/agent/structured/db/agent_conversations.sqlite`。
- 当前 active 知识索引：`knowledge_units_205bff9560b9_20260712142938`（**30,774**，含 L2 session 窗并入）。
- 向量模型：`bge-small-zh-v1.5`（512d）— 当前数据量无需更换。
- KU 抽取：L1 **1 message / 1 call** + L2 **session 窗二次抽取**（已并入 canonical/active）。

## Constraints

- **Privacy**: thinking、PII、原始 tool input/result 和 secret-bearing 正文不得进入规范化、知识或向量层。
- **Evidence**: 知识、记忆与回答必须能回查 source session/message/event。
- **Publication**: 新数据库、知识版本和向量 collection 必须 staging → gate → atomic promote，并可 rollback。
- **Compatibility**: 不破坏现有 CLI、REST、MCP 和 12 步数据管道契约（shim 保证旧入口可用）。

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| SQLite 作为结构化事实和 lineage 主存储 | 本地、可审计、容易备份与回滚 | ✓ Good |
| Chroma 只作为检索特征空间 | 避免把向量库误当作事实源 | ✓ Good |
| AgentView 只读快照后再规范化 | 避免污染正在写入的 live DB | ✓ Good |
| canonical conversation 是 Phase 14 的会话证据入口 | 消除 legacy/AgentView 双计数 | ✓ Good |
| evaluation-first knowledge unit RAG | 用冻结测试和 A/B 决定是否发布 | ✓ Good |
| 闲置模块软归档到 `_recycle/` 而非删除 | 可回滚、主树更清晰 | ✓ Good |
| scripts 按领域分包 + 根 shim | 可读性与旧命令兼容 | ✓ Good |
| 三层 SSOT + layered hybrid | 避免 personal_events 冒充全量对话 | ✓ Phase 15 |
| Google 不进对话 KU；light assert 隐私 = service+category | 日志≠断言；地点/支付不进兴趣断言 | ✓ Phase 16 |
| domains 瘦身：build→application / eval→evaluation + core.llm | 消除跨域 hub；facade 30 天窗口 | ✓ Phase 21 |
| Phase 08 memory 融合取消 | KU 已是知识 SSOT | ✓ Cancelled |
| KU 抽取 = message-level | 证据可回查、可增量、可并行 | ✓ Locked (v1.0) |
| L2 是 L1 的跨轮补强，不是独立事实源 | 保留 message 证据边界，并单独测量跨轮净增益 | Planned (v1.1) |
| 所有 KU candidate 必须先通过统一评测门 | 防止“数量增加但质量下降”仍被 promote | Planned (v1.1) |
| 评测使用现有 Python + SQLite/JSON/HTML | 数据私密、本地优先，避免引入重型外部平台 | Planned (v1.1) |

## Evolution

本文件在阶段转换和里程碑边界持续更新。每次阶段完成时核对需求、关键决策、范围和真实运行状态；每次里程碑结束时重新检查 Core Value、Out of Scope 与已验证能力。

---
*Last updated: 2026-07-13 — Milestone v1.1 planning started*
