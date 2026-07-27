# Phase 41: Extraction Scope Redefinition (Assistant Track, Coverage, Eligibility) - Context

**Gathered:** 2026-07-26
**Status:** Ready for planning

<domain>
## Phase Boundary

把知识抽取从"user-only 单轨 + 补漏式 L2"重定义为显式双轨：**user 轨守用户画像**（preference/habit/personal_fact 等，speaker gate 不拆）、**assistant 轨收知识资产**（解决方案、决策论证、技术结论——实测 87% 的现有库存实际来自 assistant 回答）；同时落地 **source × role × pass 覆盖矩阵**（让 zcode 1032 条消息 0 KU 这类盲区系统报警）与 **eligible 口径唯一化**（inspect 与 prepare 共用同一定义，Gate B 判定恢复可信）。

不做的：不拆 user 轨 speaker gate；不重抽 ku| 世代；L2 prompt 疆域与窗口大小属后续 phase；会话去重键属 Phase 42。

</domain>

<decisions>
## Implementation Decisions

### 双轨抽取
- **D-01:** assistant 轨使用**独立 unit_type 集合**（建议 `solution` / `decision_rationale` / `technical_conclusion`，与现有 6 个 user 轨类型不混），独立 prompt、独立 eval 集。[auto] Q: "复用现有 6 类型还是独立集合？" → Selected: "独立集合"（recommended：两轨知识性质不同，检索/视图需按轨过滤）
- **D-02:** 信任分级靠 `evidence_scope` 列承载（CHECK 已含 'assistant'，无需 schema 变更）：user 轨 = 画像级信任；assistant 轨 = 内容级信任，检索层可按 scope 过滤，用户画像视图只看 user 轨。
- **D-03:** assistant 轨证据 gate：quote 回查**必做**（复用 `_evidence_supported`，锚 assistant 原文）；**用户确认信号做 confidence/lifecycle 修饰而非硬 gate**（后续 user 轮采纳 → 加权，纠正 → 标 superseded 候选，接入既有 lifecycle 路由）。[auto] Q: "确认信号作为硬 gate 还是修饰？" → Selected: "修饰"（recommended：gemini 类问答源大量回答无显式确认，硬 gate 会误杀主体）

### ku| 世代与存量
- **D-04:** ku| 世代（14,928 条）与已重标的 assistant-scope v1| **显式豁免**（grandfather）：scope 重标（2026-07-26 已执行，29,554 行）即视为归属迁移完成，不做内容重抽。新 assistant 轨只覆盖增量。[auto] Q: "ku| 世代重抽还是豁免？" → Selected: "豁免"（recommended：内容实测 ~90% 为真，重抽成本高收益低）

### eligible 口径
- **D-05:** eligible 定义与 role 解耦：eligible = session 级资格（evidence_eligible）+ 内容清洗（剥离系统注入）+ 长度阈值；**role 只决定进入哪条轨**。inspect / prepare / inventory 三方共用同一 eligible 函数（消除"inspect 数裸 user、prepare 数清洗后 user+assistant"的口径差，Gate B 噪声清零）。

### 覆盖矩阵
- **D-06:** 覆盖矩阵进 `pk-ku doctor`：每个 source × role × pass 报告"eligible 消息数 / 已单元化数 / 未覆盖原因（abstain/terminal_failed/未入队）"。告警分级：新 source 首现 → INFO；已知 source 连续零覆盖 → WARN；**不 FAIL**（不阻断日常抽取）。[auto] Q: "覆盖缺口报警级别？" → Selected: "WARN 不 FAIL"（recommended：覆盖是观测问题不是正确性问题）

### the agent's Discretion
- 表结构与 doctor 接线方式、assistant 轨 prompt 文本、覆盖矩阵的具体 SQL 与呈现格式、eval 集规模（建议沿用 20 条级起步）。

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 流程与门禁
- `docs/runbooks/ku-incremental.md` — 增量流水线与 Gate B/E/F；本次 F-07/C2 修复后 watermark 已 fail-closed
- `AGENTS.md` + `docs/AGENTS.md` — KU 硬规则（promote 要 eval、标 lifecycle 不硬删、application.* 为 canonical）

### 抽取契约与 schema
- `assets/prompts/knowledge_unit_extractor/v1_main.md` — 现行 speaker gate 契约（"只有 role=user 能证明用户事实"）——assistant 轨 prompt 与其平级新建，不修改本文件
- `assets/prompts/knowledge_unit_extractor/v1_session_window.md` — L2 窗口 prompt（参考结构）
- `src/personal_knowledge/application/knowledge/migrate_add_knowledge_unit_tables.py` — knowledge_units schema；evidence_scope CHECK 已含 user/assistant/system/sidechain/subagent

### 现状基线（2026-07-25/26 审计与修复）
- `tools/migrations/backfill_ku_data_debts.py` — 已执行：provenance 回填 30,865 行、scope 重标 29,554 行、Chroma GC 16 集合
- `tools/migrations/salvage_v1_backlog.py` — 已执行：v1 积压并账（15,313 愈合 + 415 新建 canonical + 221 rejected）
- `var/reports/analysis/ai_context/ku_canary_gate_salvage_20260726.json` — 现役 active 索引的 canary gate 基线（Recall@5 0.65）

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_evidence_supported`（extract_knowledge_units_l2_session.py:80）：10 字连续片段证据回查，assistant 轨直接复用
- `call_llm_with_retry` / `TokenProvider` / `RequestRateLimiter` / 内容寻址 cache（build_knowledge_units_prod.py）：assistant 轨抽取器的基础设施原样可用
- `knowledge_l2_session_jobs` 的 jobs ledger 模式：assistant 轨 run 的可恢复状态机可复刻
- `RunManifest` / `StagingPublisher`（knowledge_unit_pipeline.py，F-06 修复后 promote 按 pass 族隔离）：assistant 轨的 staging→promote 通道

### Established Patterns
- 证据多对多：`knowledge_unit_evidence`（salvage 后 unit 合法持有多个 ref；eval 已对齐并集匹配）
- `compute_similarity` 已换 char 4-gram Jaccard（F-03），阈值未经 eval 集正式校准——assistant 轨 merge 阈值需随 eval 集一并校准
- doctor 检查项注册模式（doctor_ku.py 的 checks 列表）：覆盖矩阵作为一个新 check 接入

### Integration Points
- `pk-ku doctor`（doctor_ku.py）：覆盖矩阵 check 的落点
- `refresh_knowledge_units.py::_current_eligible_ref_hashes` / `inspect`：eligible 唯一函数的抽出处
- `build_knowledge_inventory.py`：inventory 目前纳入 assistant（与 inspect 口径差的来源之一）
- `personal_knowledge.evaluation.knowledge.evaluate_knowledge_unit_rag`：assistant 轨 eval 集的评测入口（已支持证据并集）

</code_context>

<specifics>
## Specific Ideas

- 实测驱动的事实（2026-07-25/26 审计）：gemini 会话 user 平均 41 字符 / assistant 平均 5100 字符；全库 assistant 消息 73,220 条 vs user 7,263 条；zcode 1,032 条 eligible user 消息 0 KU；current KU 的 87%（ku| 世代）实际抽自 assistant。
- 用户意图（对话原文）："Google 没有进行知识单元化，而且还当做了补漏"、"不会导致有价值的回答丢失吗"——assistant 轨是对这两个观察的直接回应。

</specifics>

<deferred>
## Deferred Ideas

- **L2 疆域重定义**（从"L1 补漏"改为"跨轮状态变更所有者"）+ L2 prompt 注入 L1 已知清单 —— 与双轨正交，建议作为独立 phase 或并入 Phase 41 实施时的子项，由 planner 判断
- **L2 窗口上限** 12000 → 48000 + 长尾分块（实测 8.7% 会话被截，最大 237 万字符）
- **confidence 校准**（99.3% ≥0.9 无区分度）——改为证据派生置信或弃用
- **1476 条 unresolved 孤儿 unit**（引用消息已不存在）的处置决策
- **canonical 同 subject 多 answer 组**（~5.5k 行）的 lifecycle/supersede 审查
- **QA 联立深化（v2 prompt 候选）**——用户 2026-07-26 提出"问题和回答要联立看"：①QA 上下文从"前置 1 条 user"扩到"穿透短确认找最近实质提问"；②question-side ref 显式写入 `knowledge_unit_evidence`（role=context），供检索排序与 eval 并集匹配复用；③QA 配对跳过 <30 字确认类消息（eligible 阈值不应遮住配对逻辑）。约束：**不在 run 中途换 prompt**（compute_cache_key 含 prompt_hash，换版会分裂缓存命名空间）——等全量 run 完成后出 v2，用 eval 集对比 v1/v2 再决定存量是否重抽
- **L1 单条消息截断上限（2026-07-26 用户问"多少字符合适/要不要分梯度"，实测后结论：不分梯度，单档 48k）**——实测 canonical DB（注意 15135 条 assistant content 为 NULL，统计时先排除）：assistant 文本消息 58085 条中 >12k 仅 106 条，去掉工具前缀后**真正被截的仅 34 条**（p50≈15k，p90≈52k，max≈147k）；user 文本消息 7227 条中 >12k 有 91 条（>48k 有 38 条，max 329k）。两个待办：①**user 轨目前无截断上限**（截断只在 assistant 分支，build_knowledge_units_prod.py:896），329k 字符的消息会整条进 LLM，需补对称 cap；②assistant 轨 `ASSISTANT_MAX_CHARS` 12000 → 48000，可覆盖 ~94% 真实案例，触及消息总共 ~125 条、成本可忽略。分梯度（按对话长度变档）对 ~100 条消息是过度工程，否决。与"L2 窗口 12000→48000"项同源，建议并入同一个 v2 prompt eval A/B 一起验证
- **extract-gate / merge-gate 的 track 适配（2026-07-27 全量 assistant 轨实测踩坑）**——①extract-gate 的 `--min-yield` 默认 0.7 是 user 轨校准值，assistant 轨内容驱动 abstain 率 ~64%（抽样 10 条核实均为过程叙述，abstain 判定正确），实测 yield 0.36，本次以 `--min-yield 0.3` 通过；建议 gate 增加 `--track` 参数按轨校准默认阈值。②canonical 的 merge gate 正例对（merge_positive_pairs 20 对，`cm|` 消息级 ref）在 `canonical_unit_members.member_unit_id` 中 0/40 存在——正例集用的是旧 id 体系，对任何新 run 都结构性 FAIL（本次 7818 条全 singleton、0 合并、负例 0 误并，写入正常）；需要把正例对迁移到 unit id 体系，或在新 run 类型下跳过该 gate

</deferred>

---

*Phase: 41-extraction-scope-redefinition-assistant-track-coverage-eligi*
*Context gathered: 2026-07-26*
