# Phase 43: L2 Scope Redefinition (Cross-turn State Ownership and Incremental Dedup) - Context

**Gathered:** 2026-07-27
**Status:** Ready for planning

<domain>
## Phase Boundary

把 L2 从"L1 补漏"重定义为"跨轮状态变更所有者 + 增量去重守门"：抽取时注入已有 canonical 清单做等价标注（supersede 候选而非新 current）；目录/分支/阶段/计划类状态 subject 归 L2 管辖、L1 降 candidate；沿用 supersede 链提供"当前值/历史值"查询语义；11,008 条 41 口径账存量分级处置并收敛 watermark。

不做的：Google 数据单元化（独立 phase）；QA v2 abstain prompt 调优（41 deferred）；全量重抽存量；L1 prompt 大改版；`valid_from/to` 新字段；Cockpit 新端点。

</domain>

<spec_lock>
## Requirements (locked via SPEC.md)

**4 requirements are locked (L2G-01..04).** See `43-SPEC.md` for full requirements, boundaries, and acceptance criteria.

Downstream agents MUST read `43-SPEC.md` before planning or implementing. Requirements are not duplicated here.

**In scope (from SPEC.md):**
- 抽取侧已知清单注入机制
- 状态类 subject 清单与 L1/L2 管辖路由
- 复用现有 supersede 链的"当前值/历史值"查询视图
- 11,008 条存量 staging unit 的分级报告与治理链处置
- watermark 推进/delta 收敛的执行笔记（含 42-03 gate 遗留收尾判定）

**Out of scope (from SPEC.md):**
- Google 数据源知识单元化 — 独立数据源 phase
- QA v2 abstain prompt 约束调优 — Phase 41 deferred
- 全量重抽存量 — 41 ⑨ 已决策
- L1 抽取 prompt 大改版 — 本 phase 只加注入段
- `valid_from/valid_to` 时效新字段 — 沿用 supersede 链

</spec_lock>

<decisions>
## Implementation Decisions

### 注入机制（L2G-01）
- **D-01:** 两阶段召回：subject 归一化（小写/去空白标点）精确匹配已有 canonical 为主路径；未命中且 subject 非空时才走 Chroma embedding top-k 兜底。理由：精确匹配零成本、确定性、可测试；embedding 只补表述漂移，不让非确定性进入主路径（eval/复现需要确定性）。
- **D-02:** 注入上限 **20 条**，answer 截 200 字符（约 +4k 字符 prompt 预算）；命中率随 run 报告验证后再调。
- **D-03:** 等价判定 LLM 只标注不裁定：输出 `duplicate_of: <unit_id>`（只能引用注入清单内 id，否则视为无效输出）；落 staging 记 **supersede 候选**，治理批逐对裁定后才生效。不做双 LLM 二次确认（治理批人工检视已是防线，双确认成本翻倍收益边际）。

### 状态类清单与 L1 拦截（L2G-02）
- **D-04:** 清单来源 = 种子手工清单（目录路径、git 分支、项目阶段、当前计划、在用设备/环境五族）+ 从 39,880 条 canonical subject 一次性 LLM 聚类**建议**扩充项，人工确认后入清单。纯人工漏长尾、纯自动进噪音。
- **D-05:** 清单落 `assets/` 下 yaml（版本可控、review 友好）；匹配用归一化精确 + 前缀规则，不上 embedding（清单几十条规模，embedding 是过度工程）。
- **D-06:** L1 命中清单 → **降 candidate 不跳过**。跳过是不可逆信息损失；candidate 保留人工转正通道，误杀成本趋零。L2 对清单内 subject 负全责。

### 当前值视图（L2G-03）
- **D-07:** CLI 两落点：`pk-ku history --subject` 扩展输出（链上标注"← 当前值"）+ `rag-search` 对 superseded/deprecated 降权并加 `--current-only` flag。不做 Cockpit 端点——本 phase 把 canonical lifecycle 语义做对，projection 层后续自然消费。

### 存量分级与 watermark（L2G-04）
- **D-08:** 三层分级：规则初分（与存活 unit 高相似 → 重复档；纯 traceback/路径列表/命令回显特征 → 噪音候选档；其余 → 疑似真知识）→ 只对"疑似真知识"子集（估 2–4k 条）走 LLM 复核 → 两个规则档各抽 50 条人工检视验证规则准确率。否决全量 11k LLM 分级（@6s/条 ≈ 18h，不值）。
- **D-09:** 转正前必须 **re-match quote 到现存 eligible 消息**（复用 41 孤儿重链接的 re-match 逻辑，已验证）；match 不上的不硬转正，走 candidate 或 deprecate。
- **D-10:** watermark：**分级处置完 + 归因报告落盘后即推进**。delta 已归因，继续挂起无信息量且让 Gate B 持续带噪；推进与处置记录都进 manifest 链，可回滚。

### the agent's Discretion
- 归一化规则细节、embedding top-k 的 k 值与距离阈值、prompt 注入段具体文案与位置、yaml schema、规则档的特征阈值、LLM 复核 prompt、各档处置的批次编排（遵守 ≤50/批铁律）、执行笔记格式。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 本 phase 锁定物
- `.planning/phases/PDA-43-l2-scope-redefinition-cross-turn-state-ownership-and-increme/43-SPEC.md` — Locked requirements (L2G-01..04) — MUST read before planning

### 前序 phase 决策与现状
- `.planning/phases/PDA-41-extraction-scope-redefinition-assistant-track-coverage-eligi/41-CONTEXT.md` — 双轨抽取、eligible 口径、evidence_scope、deferred 清单（含 re-match/治理批/QA v2 全部实操经验）
- `.planning/phases/PDA-42-conversation-dedup-with-stable-session-keys/42-CONTEXT.md` — 稳定键、ref 映射、"失败不静默"原则
- `docs/runbooks/ku-incremental.md` — 增量流水线与 Gate B/E/F、watermark 语义
- `AGENTS.md` + `docs/AGENTS.md` — KU 硬规则（不硬删、promote 要 eval、application.* canonical）

### 抽取与治理代码现状
- `src/personal_knowledge/application/knowledge/eligibility.py` — 41 eligible 唯一口径（11,008 条存量的排除来源）
- `assets/prompts/knowledge_unit_extractor/v1_main.md` — L1 现行 prompt（注入段的挂载点，prompt_hash 约束）
- `assets/prompts/knowledge_unit_extractor/v1_session_window.md` — L2 窗口 prompt（同上加注入段）
- `src/personal_knowledge/application/knowledge/confidence.py` — 证据派生置信（candidate/supersede 候选的置信修饰参照）
- `tools/migrations/backfill_ku_data_debts.py`、`tools/migrations/salvage_v1_backlog.py` — dry-run/--write/备份/单事务的迁移标准形态

### 基线数据
- `var/reports/analysis/ai_context/reconcile_full_20260727.json` — reconcile 全量 dry-run（supersede/conflict 候选基线）
- 42-03 delta 归因（本会话实测）：new_refs=1,995 / deleted_refs=12,496；88% 为 41 eligibility 口径账；11,008 条 staging unit 与存活重复率仅 2%

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 孤儿重链接的 quote re-match 逻辑（`var/tmp/relink_orphan_evidence.py`，41 实操验证 1237 条成功）— D-09 转正证据修复直接复用
- 治理批驱动脚本族（`var/tmp/supersede_batch.py` / `conflict_apply_batch.py` / `deprecate_batch.py`）— 处置批次的形态参照（≤50/批、逐对检视、manifest 链）
- `knowledge_l2_session_jobs` jobs ledger — L2 管辖 run 的可恢复状态机
- `RunManifest` / `StagingPublisher`（knowledge_unit_pipeline.py）— staging→promote 通道
- Chroma active 索引（`knowledge_units_ir_13486f30c_20260727101229`）— embedding top-k 兜底的现成向量库

### Established Patterns
- prompt_hash 进 compute_cache_key：注入段= prompt 变更 → 缓存命名空间分裂，必须在 run 间隙切换（41 硬约束）
- 等价/supersede 判定永不自动落库：LLM 标注 → 治理批裁定（41 ⑧：union-find/newest-wins 全自动误并率高，每批必须逐对检视）
- "失败不静默"：所有拦截/降级/跳过路径计数进 run 报告（42 D-05）
- evidence ref 稳定性：任何重铸都要映射表（42 D-02）；candidate/supersede 候选不触碰原 ref

### Integration Points
- `build_knowledge_units_prod.py` — L1 注入段挂载点（subject 归一化查 canonical → prompt 注入；清单命中 → candidate 路由）
- `extract_knowledge_units_l2_session.py` — L2 注入段 + 状态类 subject 全责抽取
- `pk-ku history --subject`（lifecycle/history 命令族）— 当前值标注的 CLI 落点
- `rag-search` — superseded 降权 + `--current-only` 落点
- `pk-ku doctor` — 清单命中率、candidate 积压、分级处置进度可作新 check（可选）

</code_context>

<specifics>
## Specific Ideas

- 用户原始诉求链：L1/L2 无交叉查重 → "L2 要不要改成通过多个 L1 来" → 12000 字符上限（已 48k，cfab291）→ 跨 message 查重有用 → Google 未单元化（out of scope，独立 phase）→ 只抽 user 会丢有价值回答（41 assistant 轨已回应）→ 本 phase = L2 疆域重定义。
- 42-03 gate 遗留：dual-track strict yield gate failed（user 0.0141 / assistant 0.1381），watermark 故意未推进——收尾判定进 D-10 执行笔记。
- 用户拍板风格（41/42/43 一致）：接受"标注+治理批裁定"而非全自动；接受"candidate 不跳过"的保守路由；成本敏感（否决全量 LLM 分级、否决双 LLM 确认）。

</specifics>

<deferred>
## Deferred Ideas

- **Google 数据源知识单元化**（google_activities→normalized→assertion 链从未进 staging）— 独立数据源 phase，用户已点名关注，建议下个 milestone 优先
- **QA v2 abstain prompt 约束**（41 deferred ⑩）— A/B 后 prompt 迭代 + 存量重抽决策
- **47 个超长 L2 会话的分块重抽 run**（41 deferred，分块代码已落地 `_partition_chunks`）— LLM 成本决策
- **Cockpit 消费"当前值"语义的 projection 端点** — 等 v1.4 验收或 v1.5 Wiki 时自然衔接
- **注入命中率/拦截量的 run 报告指标进 doctor** — 视首轮 run 数据决定（agent discretion 内的可选项，不锁定）

</deferred>

---

*Phase: 43-l2-scope-redefinition-cross-turn-state-ownership-and-increme*
*Context gathered: 2026-07-27*
