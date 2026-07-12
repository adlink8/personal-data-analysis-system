# 个人数据分析项目

## What This Is

这是一个 Windows 本地优先的个人数据系统，把 Google、GPT、Agent 与 AgentView 的数字足迹转换为可持续追加、可查询、可追溯的统一数据、记忆和知识层。系统同时提供 CLI、REST、MCP、可视化与 RAG 消费接口。

## Core Value

把个人历史转换为隐私安全、证据可回查、能够持续增量学习的外部知识系统。

## Requirements

### Validated

- ✓ 三源增量导入、统一事件、增强与去重管道 — Phase 01-03
- ✓ 结构化记忆、记忆图谱和语义候选层 — Phase 04-10
- ✓ MCP、Apps SDK、REST 与统一数据访问接口 — Phase 11-12
- ✓ 公共基础层重构和 canonical AgentView 会话证据层 — Phase 13-13.5
- ✓ 知识单元 RAG 小样本评测优于 raw baseline — Phase 14 Wave 0-4
- ✓ 扩大生产抽取 gate PASS + 合并索引上线（30,012）— Phase 14 KU-01..07
- ✓ 工程结构重整：闲置模块 `_recycle/`；scripts 领域分包 + 兼容 shim

### Active

- [ ] Phase 14 KU-08：生产非空 source delta → journal promote → watermark（契约测试已绿）
- [ ] 高优先级自动化测试补齐（见 `integration/analysis/ai_context/test_coverage_gaps.md`）
- [ ] 收口 Phase 08 遗留的记忆实验去复杂化工作

### Out of Scope

- 直接修改 AgentView live database — 它只作为只读上游
- 删除 raw events、legacy 数据库或旧 Chroma collection — 必须保留回滚与追溯
- 让 LLM 输出绕过 schema、evidence、privacy 和 evaluation gate — 所有 AI 产物先进入 staging
- 在核心管道引入大型 Agent/RAG 编排框架 — 优先使用现有 Python、SQLite 和轻量接口
- 硬删除 `_recycle/` 归档（仅软归档；恢复靠 MANIFEST）

## Context

- 项目根目录为 `C:\Users\li\Desktop\数据分析`，默认运行环境是 Windows + PowerShell。
- 主工程在 `integration/`；`Agent/structured/db/` 为会话证据库；GPT 等闲置数据在 `_recycle/`。
- 核心统合库为 `integration/db/personal_system.sqlite`。
- 脚本实现在 `integration/scripts/{core,knowledge,memory,...}/`，根目录 `*.py` 为兼容 shim。
- canonical 会话库由 Phase 13.5 从 AgentView 与 legacy Agent 数据构建。
- Phase 14 的核心理论是“RAG = 对个人历史进行非参数化二次训练”。
- 当前 active 知识索引：`knowledge_units_run_76c6259e_20260712062418`（30,012）。
- 本文件由旧 `.gsd/phases/` 与 `.planning/STATE.md` 迁移生成；旧文档保留为审计来源。

## Constraints

- **Privacy**: thinking、PII、原始 tool input/result 和 secret-bearing 正文不得进入规范化、知识或向量层。
- **Evidence**: 知识、记忆与回答必须能回查 source session/message/event。
- **Publication**: 新数据库、知识版本和向量 collection 必须 staging → gate → atomic promote，并可 rollback。
- **Compatibility**: 不破坏现有 CLI、REST、MCP 和 12 步数据管道契约（shim 保证旧入口可用）。
- **Model routing**: 子代理不得使用 GPT-5.6 Sol；未配置 5.5/5.4 专用代理前关闭自动并行代理。

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
| 保留 `.gsd/` 作为迁移源 | 文档迁移可逆且不丢历史 | — Pending |

---
*Last updated: 2026-07-12 after structure cleanup + scripts package layout + test gap audit*
