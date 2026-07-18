# 个人数据分析项目

## What This Is

这是一个 Windows 本地优先的**个人决策智能系统**。它把 Google、GPT、Agent 与 AgentView 等长期个人数据转换为可持续追加、可查询、可追溯的个人知识与状态，并以独立 External Context Authority 接入受控公共事实，通过受控 LLM 与确定性规则形成个性化决策建议、行动结果和反馈校准。系统同时提供 CLI、REST、MCP、可视化与 RAG 消费接口。

项目状态分析只是 project 域的一个输入能力，不是产品最终目标。系统默认不替用户执行外部动作，用户保留价值选择、风险接受与最终决策权。

## Core Value

以长期个人数据为内部状态、以外部社会环境为外部状态，在隐私安全、证据可回查和不确定性可解释的前提下，为用户提供可验证、可反馈、可持续校准的个人决策支持。

## Long-term Product Target

权威目标说明：[`PERSONAL-DECISION-INTELLIGENCE-VISION-STATUS-2026-07-18.md`](./PERSONAL-DECISION-INTELLIGENCE-VISION-STATUS-2026-07-18.md)。

当前预期目标差距：[`TARGET-GAP-ANALYSIS-2026-07-18.md`](./TARGET-GAP-ANALYSIS-2026-07-18.md)。

```text
长期个人数据 + 当前个人状态 + 外部环境 + 历史决策结果
→ 状态与变化建模
→ 决策案例与多方案比较
→ LLM 决策分析候选
→ 用户确认、行动与结果
→ 后验评估与建议校准
```

LLM 输出是 Recommendation Candidate，不是个人事实、最终决策或执行权限。

## Current State: v1.2 External Context & Low-risk Decision Intelligence Pilot

**Shipped:** 2026-07-18。已建立与个人事实隔离的 External Context Authority，并在低风险 `project` 域用受控 LLM 完成真实、证据绑定、可反馈的决策试点。

**Delivered features:**
- 两个受控公共来源、一个 project/technology 主题的独立 External Authority
- Personal + External 双快照 Decision Context 绑定与 fail-closed 漂移检查
- 逐主张 evidence ID 的结构化 LLM Decision Analysis Candidate
- 真实低风险 Recommendation→Decision→Action→Outcome 纵向链
- 预注册 personalized/generic 对照、观察窗与严格 `INCONCLUSIVE` 边界

**Previous:** v1.0 completed 2026-07-12（Phases 01–16；Phase 08 cancelled）。见 [MILESTONE-v1.0.md](MILESTONE-v1.0.md)。

## Current Reality — 2026-07-18

- Phase 28–31 已完成：External Authority、双快照结构化 LLM 分析、project 真实决策链和成对校准均可校验重建。
- Phase 29 通过现有 ChatGPT 登录完成一次真实 `gpt-5.4` 分析；Phase 31 严格执行两臂各一次调用、零重试、零费用。
- Phase 30 有一条 11-event 真实 Recommendation→Decision→Action→Outcome 主链及一条 defer 控制链；系统外部动作数为零。
- Phase 31 个性化相对 generic 的效果结论为 **INCONCLUSIVE**：样本 1 小于最小 2、generic 缺少真实 outcome、实际 token 超出预注册预算；`causal_claim=false`。
- v1.2 需求 PDI-01..08 全部完成，里程碑审计通过；后续扩样或扩域必须重新预注册并保持无自动 promotion。

- Phase 23 已完成复合 SSOT、D/S/R/A registry、Serving Snapshot、证据下钻和 fail-closed Doctor。
- Phase 24 已闭环：最终 Recall@5 提升 **10.4478pp**，置信下界 **+4.4776pp**；真实 lifecycle ledger 有 6 个事件、2 个 applied manifests。
- Phase 25–27 Live schemas 已应用，Personal State、Decision Feedback、Proactive Intelligence 各有 1 个真实 committed run，并通过 exact snapshot/checksum 验证。
- 真实链路已覆盖状态、建议、用户确认、行动、结果、非因果效果评估、主动候选以及 suppress/restore。
- `src/personal_knowledge/intelligence` 已有受控 LLM candidate 路径；所有事实、隐私、冲突与风险门仍由确定性规则执行。
- External Context Authority 当前限定两个 allowlisted 公共来源；Google Activities 仍属于个人行为数据，不属于外部社会情报。
- Technical Target D、真实低风险数据链、External Context、LLM 决策分析与 Product UAT 均已通过；比较效果仍需更大真实 cohort。

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

### Validated (v1.2)

- ✓ 独立 External Context Authority、bounded import、生命周期和可逆快照 — PDI-01..04
- ✓ 双快照证据绑定的结构化 LLM Decision Analysis Candidate — PDI-05..06
- ✓ 低风险 project 真实主链、defer 控制链和非因果 outcome — PDI-07
- ✓ 预注册 personalized/generic 对照与诚实 INCONCLUSIVE 边界 — PDI-08

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
- **产品同步入口（2026-07-16）：** `pk-sync conversations [--write]`（AgentsView→canonical）。  
  旧 `rag-pipeline` 统合 1–12 步已退役（仅取证：`PK_ALLOW_LEGACY_PIPELINE` + `--legacy-integrated`）。  
  **KU：** 日常仅增量（`docs/runbooks/ku-incremental.md`）；禁止把全量 `build_knowledge_inventory`+`prod --start` 当对话同步后的默认步骤。  
  Agent 全流程见 `docs/AGENTS.md`。  
- **数据/运行时（Phase 20）：** `data/`、`var/`、`archive/`；AgentsView live 仍为 protected-external。
- 核心统合库：`var/db/personal_system.sqlite`（非对话 PE 过渡层）；对话 SSOT：`data/canonical/agent/structured/db/agent_conversations.sqlite`。
- 当前 active 知识索引：`knowledge_units_ir_4cd8af4ad_20260718054940`；当前复合 serving snapshot：`ss_5d816a6bf3ebd0bce9463236`。
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
| External 与 Personal 权威物理、语义和权限隔离 | 防止公共事实污染个人事实 | ✓ Good (v1.2) |
| LLM 输出永远是 candidate，事实与安全门确定性执行 | 保留证据边界和用户最终决策权 | ✓ Good (v1.2) |
| 样本不足、缺测或协议偏离必须 INCONCLUSIVE | 防止把单次演示包装为个性化因果增益 | ✓ Good (v1.2) |
| 校准 proposal 不自动 promotion | 策略变更必须独立评审并可回滚 | ✓ Good (v1.2) |

## Evolution

本文件在阶段转换和里程碑边界持续更新。每次阶段完成时核对需求、关键决策、范围和真实运行状态；每次里程碑结束时重新检查 Core Value、Out of Scope 与已验证能力。

---
*Last updated: 2026-07-18 after v1.2 milestone completion*
