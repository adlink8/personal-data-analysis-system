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
- **L2 窗口上限** 12000 → 48000 + 长尾分块（实测 8.7% 会话被截，最大 237 万字符）——**前半已落地**（cfab291：MAX_WINDOW_CHARS=48000，policy 键自动换命名空间）；~~长尾分块仍 deferred~~ **长尾分块已实施（2026-07-27）**：`_partition_chunks` 按时间序确定性切 ≤48k 消息块，`list_l2_sessions` 对超长会话发出伪 session `sid#c<n>`（零 schema 变更复用 jobs/window 机制，unit 落库 `source_session_id` 仍写真实会话 id）；≤48k 会话行为与 v1 完全一致。实测影响：362 个 L2 会话中 47 个超长会话 → 203 个窗口（块数分布 2/3/7/8/21/43，最大单会话 43 块），此前被截的早期内容全部进入抽取面。**仍 deferred：对 47 个超长会话执行分块重抽的 run 决策（LLM 成本）**
- ~~**confidence 校准**（99.3% ≥0.9 无区分度）——改为证据派生置信或弃用~~ **已实施（2026-07-27）**——查实 confidence **无排序消费者**（semantic_search score=纯向量距离，confidence 仅展示元数据；canonical 聚合取成员 min），LLM 自报 95.2% ≥0.9（众数 0.95）纯误导，弃用自报、改**证据派生**（`application/knowledge/confidence.py::derive_confidence`）：0.4 基线 +0.2 有证据 +0.15 多证据互证 +0.15 user 亲述（L2 按 'window' 不给此项）+0.1 quote≥20 字符，D-03 采纳/纠正 ±修饰并入，封顶 0.95 永不满置信。L1 prod / L2 ingest 均已切换（prompt 不动 → 缓存命名空间不分裂）。存量 44880 条 staging + 37721 条 canonical 已回填（脚本 var/tmp/backfill_derived_confidence.py，回填前快照在 var/backups/personal_system_pre_confidence_backfill_*）：≥0.9 占比 95.2%→7.8%。注意：向量集合 metadata 里的 confidence 是旧值，下次索引重建才刷新（仅展示用）；confirmation_signal 未持久化，回填按 none 处理（旧 ±修饰不保留）
- ~~**1476 条 unresolved 孤儿 unit**（引用消息已不存在）的处置决策~~ **已处置（2026-07-27）**——实测 dead-ref unit 1373 条（条目数随 canonical 重建略漂移）。抽样 120 条分类后全量执行：**A 类（quote 可在现存消息 re-match）1237 条重链接**——更新 `source_message_ref` + 死 `knowledge_unit_evidence` 行（282 条因 quote 命中同 unit 已有活 ref 按去重删除；另有 41 个备份后新抽 unit 按 `evidence_ref = source_message_ref` 约定重建证据行；脚本 var/tmp/relink_orphan_evidence.py）。**B 类（证据彻底丢失）211 条**：全部是单成员/纯 B canonical（210 纯 + 1 混合），混合的 1 条有活成员证据保留 current；**210 个纯 B canonical 已经治理链 deprecate**（5 批 ×≤50，klm_4f6f3fb9e4522b45a6db5931 等 manifest，驱动脚本 var/tmp/deprecate_batch.py，逐条检视无异常）。配套改动：治理链新增 `deprecate` action（ALLOWED_ACTIONS + actions 表 CHECK 整表重建迁移 + apply 分支置 `deprecated`/清 supersedes），`_default_evidence_validator` 放宽为自动识别 ref 类型（deprecate 自引 canonical unit 定位被审对象）。残留：22 条无匹配死 evidence 行（所属 unit 均有活证据，不阻塞，暂留）；deprecated unit 在下一次索引重建时退出向量索引。**事故记录**：重链接过程中一次清理脚本列选错（unit_id 当 evidence_ref 过滤）误删 59477 条证据行，已从 `var/backups/personal_system_20260727T075010Z.sqlite` 按行 id 差集恢复 + 确定性重放重链接，终态校验 total=59705 / dead=233 / 无零证据 unit
- **canonical 同 subject 多 answer 组**（~5.5k 行）的 lifecycle/supersede 审查——**2026-07-27 已启动，首批落地**：reconcile 全量 dry-run（var/reports/analysis/ai_context/reconcile_full_20260727.json）：supersede 候选 211 / conflict 候选 10795。**supersede 211 条已全部处置完（2026-07-27）**：批次 1-4 共 182 条 applied（klm_9bd10978c027546f27ee0e34 等 4 个 manifest，驱动脚本 var/tmp/supersede_batch.py），批次 5 的 8 条经检视判定为**不同事实**（Posters/Bookmarks、search/repository、AUDIT.md/json、专辑索引/临时归档、根目录/integration 子目录）全部 reject 保持 current，另有 ~21 条因 evidence ref ineligible 无法走 manifest（待查 eligibility 重标副作用）。经验：union-find 簇的 newest-wins 在跨文件/跨目录场景会误并，**每批必须逐对检视**，不能全自动 approve。**conflict 候选禁止盲标**——抽样证实误判严重：同 subject 不同方面是正常多facet知识（"用户用什么 shell"5 条一致表述会被全灭），甚至有分词伪 conflict（"学号是2300160629" vs "学号是 2300160629" 同一事实 Jaccard=0）；加 question 门（q-Jaccard≥0.6）后 10795→1626 仍以冗余重述为主而非真矛盾。真 conflict 需要语义级 LLM 审查（对比 OLD/NEW 判矛盾/冗余/时序漂移），建议作为独立 phase 配 LLM review prompt 批量做；base_url 五矛盾案例（canary stale 源）属此类。**conflict 语义审查已完成（2026-07-27）**：q-gated 294 对（q-Jaccard≥0.6，对级去重）全量 LLM 审查（gemini-3.5-flash-lite）→ supersede 144 / keep 126 / conflict 24 / error 0；处置 3 批共 142 条 applied（klm_f9b1c0b0e2791f03f0aa9618 50 + klm_a73360cfc80d5387c71662bd 50 + klm_847cfe9aed6a5b91de5e8076 42，驱动 var/tmp/conflict_apply_batch.py）。处置规则：方向默认"answer 信息量大者存活、持平日期新者、同日期较长者"；**逐对检视后 9 对强制方向覆写、19 对判 keep 跳过**（并存项目/双环境/并行课程/计划vs完成态——LLM 的 conflict/supersede 判决对"同 subject 不同项目并存"和"时序状态"两类误判率仍高，keep/override 清单在脚本内可审计）；同 unit 去重（supersede 优先）+ 链式 retarget（穿透被 supersede 的中间 winner）。终态：conflict=16、superseded=309。遗留：部分重叠但互不包含的对（如 NovelMind 栈 LiteLLM/TS 各缺一角）只能 supersede 牺牲次要信息，真正的 answer 合并属 L2 疆域重定义范畴
- **QA 联立深化（v2 prompt 候选）**——用户 2026-07-26 提出"问题和回答要联立看"：①QA 上下文从"前置 1 条 user"扩到"穿透短确认找最近实质提问"；②question-side ref 显式写入 `knowledge_unit_evidence`（role=context），供检索排序与 eval 并集匹配复用；③QA 配对跳过 <30 字确认类消息（eligible 阈值不应遮住配对逻辑）。约束：**不在 run 中途换 prompt**（compute_cache_key 含 prompt_hash，换版会分裂缓存命名空间）——等全量 run 完成后出 v2，用 eval 集对比 v1/v2 再决定存量是否重抽。**v2 代码已实施（2026-07-27）**：①`_load_preceding_user_context` 穿透短确认（<30 字且匹配确认套话才跳过，短实质提问不误伤，最多回溯 5 条）；②question-side ref 以 `evidence_type='context'` 落盘（`build_knowledge_units_prod.py` 提交路径）；③确认套话由 `_CONFIRM_RE` 判定。QA 双证据计入 confidence 派生（assistant 轨 QA 对 0.6→0.75）。prompt 文本未动（prompt_hash 不变，input_hash 变 → 只新增缓存条目不分裂命名空间）。**v1/v2 A/B eval 已完成（2026-07-27，结论：不按现 v2 行为重抽存量）**：50 条穿透影响样本（seed 41，均有 v1 存量 unit）双盲评审（脚本 var/tmp/qa_v2_ab.py，产物 var/tmp/qa_v2_ab{,_judge}.jsonl）→ **v1 25 / v2 18 / tie 7**。关键发现：v2 把真实问题上下文给 LLM 后，LLM 过度 abstain（19/50，v1 为 0）；其中 14 例 assistant 续答（"继续"后的新回答）其实含实质新内容（WSL 非交互安装、Java 目录整理方案等），v1 抽到了、v2 弃权丢失——盲评在"有内容 vs 无内容"时必然选有内容。双方都抽取的 30 条子集 v1 11 / v2 12 / tie 7，v2 锚定质量略优但优势微弱。**决策：v2 代码保留对未来 run 生效（无害且锚定略优），不做存量重抽**（重抽 ~5500 条 affected item 约 9h@10RPM 且按现行为会净损召回）。后续改进方向（新 deferred）：prompt 层约束 abstain——仅当回答相对前置提问无新信息时才允许弃权，续答中的新步骤/结论必须抽取；改后重跑 A/B 再决策存量
- **L1 单条消息截断上限（2026-07-26 用户问"多少字符合适/要不要分梯度"，实测后结论：不分梯度，单档 48k）**——实测 canonical DB（注意 15135 条 assistant content 为 NULL，统计时先排除）：assistant 文本消息 58085 条中 >12k 仅 106 条，去掉工具前缀后**真正被截的仅 34 条**（p50≈15k，p90≈52k，max≈147k）；user 文本消息 7227 条中 >12k 有 91 条（>48k 有 38 条，max 329k）。两个待办：①**user 轨目前无截断上限**（截断只在 assistant 分支，build_knowledge_units_prod.py:896），329k 字符的消息会整条进 LLM，需补对称 cap；②assistant 轨 `ASSISTANT_MAX_CHARS` 12000 → 48000，可覆盖 ~94% 真实案例，触及消息总共 ~125 条、成本可忽略。分梯度（按对话长度变档）对 ~100 条消息是过度工程，否决。与"L2 窗口 12000→48000"项同源，建议并入同一个 v2 prompt eval A/B 一起验证。**已于 2026-07-27 实施（cfab291）**：`MESSAGE_MAX_CHARS=48000` 双轨对称（user 轨补 cap），L2 同步 48k——对**未来** run 生效；存量已抽 unit 不受影响（截断只影响 LLM 输入，不回填）。截断变更不改 prompt 文本（prompt_hash 不变、只放宽输入长度），无需单独 A/B；QA v2 的 A/B 结论见上条（2026-07-27 完成，不重抽存量）
- ~~**extract-gate / merge-gate 的 track 适配**~~ **已实施（cfab291，2026-07-27）**——①extract-gate 加 `--track`，min-yield 缺省按轨校准（user 0.7 / assistant 0.3），缺省从 prompt_version 推断、无法推断维持 fail-closed，显式 `--min-yield` 优先。②merge gate 正/负例的 `cm|` 消息级 ref 改为经 `knowledge_unit_evidence` 解析（一对多任一命中/误并），无法解析 pair 单独计数、正例全无法解析时 `not_applicable` 而非结构性 FAIL。实测结果：20/20 正例 unit 已不在 canonical（旧 run 未 canonicalize），负例 13/20 可解析且 0 误并——**正例对本身需按当前 canonical 重建（eval 数据集工作，仍 deferred）**。**正/负例集已于 2026-07-27 重建**：正例取自多成员 canonical 的 member unit 对（unit id 引用，answer Jaccard 降序前 20），负例取同 (subject,type) 不同 canonical 的中等相似对；旧文件备份 `*.bak_20260727`；重建脚本 var/tmp/rebuild_merge_pairs.py。重建后 gate：recall 1.0 / 0 误并 / 0 不可解析，恢复为活的一致性检查（未来 canonical 重建若拆散已合并对的回归可检出）
- **QA v2 abstain 约束（A/B 后续改进，2026-07-27 记入）**——A/B 发现 LLM 拿到穿透上下文后过度弃权（19/50），丢失续答新内容。改进：prompt 层约束 abstain 仅当回答相对前置实质提问**无新信息**时可用，续答中的新步骤/结论/决策必须抽取；可考虑 abstain 降级为"回退无上下文抽取"。改后重跑 v1/v2 A/B（同 seed 41 样本）再决策存量是否重抽（~5500 条 affected，~9h@10RPM）。注意 prompt 文本变更会改 prompt_hash → 分裂缓存命名空间，需在 run 间隙切换

</deferred>

---

*Phase: 41-extraction-scope-redefinition-assistant-track-coverage-eligi*
*Context gathered: 2026-07-26*
