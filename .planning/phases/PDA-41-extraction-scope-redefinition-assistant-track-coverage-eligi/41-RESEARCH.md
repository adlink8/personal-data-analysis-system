# Phase 41 Research: Extraction Scope Redefinition (Assistant Track, Coverage, Eligibility)

**Researched:** 2026-07-26
**Inputs:** 41-CONTEXT.md（D-01~D-06 已锁）、ROADMAP Phase 41（EXT-01/02/03）、ku-incremental runbook、抽取器/pipeline/doctor/eval/检索层源码
**Requirements:** EXT-01（assistant 轨成型）、EXT-02（覆盖矩阵进 doctor）、EXT-03（eligible 口径唯一化）

---

## 0. 一句话结论

把 prod 增量抽取引擎**参数化为双轨**（track config 注入 prompt/scope/unit_id 前缀/unit_type 集合，run 级单轨），eligible 判定从 `build_inventory` 抽出一个**带 role 字段的唯一函数**让 inspect/prepare/inventory 三方共用，覆盖矩阵作为 `doctor_ku` 的一个 **warn-only check** 注册，assistant 轨 eval 集复用 frozen jsonl 格式新建 20 条。**不新建并行 ledger 模块**——那会绕过 Gate F watermark 保护。

---

## 1. Q1 — assistant 轨抽取器形态：改造 prod 引擎为双轨参数化（推荐），不新建独立模块

### 两个候选

- **A. 新模块**（如 `extract_knowledge_units_assistant.py`，复刻 L2 的 jobs ledger 模式）
- **B. prod 引擎加 track 参数**（`build_knowledge_units_prod.py` 注入 track config）

### 推荐 B，理由（全部有代码依据）

1. **knowledge_run_items 是 Gate F 与 skip_succeeded 的唯一事实源。** watermark advance 的 fail-closed 检查（pending/in_flight/retryable 阻断、terminal_failed 需 `--acknowledge-failures` 记入 `knowledge_dead_refs`，runbook §Gate F）只读 `knowledge_run_items`；`prepare_production_delta` 的 `skip_succeeded`（refresh_knowledge_units.py:1644）也查它。L2 式独立 ledger（`knowledge_l2_session_jobs`，extract_knowledge_units_l2_session.py:58-73）完全绕开这套保护——assistant 轨若用独立 ledger，watermark 前进后未抽的 assistant refs 会被**永久跳过**（进入 baseline 后不再是 new），且无从察觉。这正是 D-06 覆盖矩阵要抓的事故类型，不能一边建矩阵一边制造盲区。
2. **L2 ledger 没有生产级并发保护。** assistant 轨体量是 user 轨 10 倍（73,220 vs 7,263 条，CONTEXT specifics）。prod 引擎有 lease/claim（`_claim_item`:345、`recover_expired_leases`:292）、429 不计 attempt 额度（:511-522）、双熔断（all-retryable / zero-success circuit breaker，:840-872）、内容寻址 cache（:97-128）。L2 的 jobs 表只有 status/attempt_count，无 lease，多进程 resume 会重复烧 quota。
3. **StagingPublisher 按 unit_id 前缀做 pass 族隔离**（knowledge_unit_pipeline.py:177-192，`substr(unit_id,1,3)`）。新轨用 `as|` 前缀即自动获得 promote 隔离，不触碰 `v1|`/`l2|`/`ku|`（:170-171 注释明示 ku| 不被任何新 run 触碰——与 D-04 豁免天然契合）。**硬约束：新前缀必须是恰好 3 字符含 `|`。**
4. **cache 命名空间安全。** cache_key 含 prompt_hash（compute_cache_key:97），assistant prompt 与 v1_main 不会串 cache。

### B 的改造面（prod 引擎当前的硬编码点）

| 硬编码 | 位置 | 改造 |
|---|---|---|
| prompt 文件 = v1_main.md | prod `PROMPT_PATH`（模块常量，process_run:626 读取） | 变为 run 级参数（prompt path/version 随 `start_run`/run manifest 走） |
| prompt 包装文案 "用户对话证据（role=user）：" | `call_llm_with_retry` build_knowledge_units_prod.py:211 | 加 `role_label` 参数 |
| `evidence_scope='user'` 写死 | `_commit_item_result`:591 | 从 run 的 track config 取 |
| `unit_id` 前缀 `"v1|"` | :576 | 从 track config 取（`as|`） |
| unit_type 校验集合（6 个 user 类型） | `KnowledgeUnit.valid_unit_type`，build_knowledge_units.py:75-81 | assistant 轨用独立 ExtractionResult/validator（`solution`/`decision_rationale`/`technical_conclusion`） |

### 关键设计约束：run 级单轨

`prepare_production_delta` 已有 `--roles` allow-list 与 per-ref role 元数据（refresh_knowledge_units.py:1702, 1751-1776），但 `process_run` 加载内容时**不读 role**（:720-726 只取 content/session/agent）。若一个 run 混入两种 role，单 prompt 无法服务两轨，per-item 选 prompt 会把复杂度塞进热循环。**约束：一个 extraction run 只属于一条轨**——`pk-ku prepare --roles assistant --track assistant` 产 assistant-only run，manifest 的 prompt_version/config 记录轨身份；user 轨 prepare 默认 `--roles user`（现状 prepare 不过滤时会把 assistant refs 也排进 v1 队列，这是口径差的一部分，随 EXT-03 一并修）。

### 为什么不是"A 新模块"的折中

L2 模式唯一值得复刻的是**文件级独立 prompt + 独立 CLI 入口**；这两点 B 方案都有（prompt 独立文件、pk-ku 子命令/flag 区分轨）。`call_llm_with_retry`/`TokenProvider`/`RequestRateLimiter`/cache 两方案都复用，不构成差异。

---

## 2. Q2 — assistant 轨输入选择与窗口策略

### eligible 过滤（进入轨道的门票，统一由 Q4 函数判定）

现有 assistant 过滤先例全在 `build_inventory`（build_knowledge_inventory.py:91-154），assistant 轨直接继承：

- session 级 `evidence_eligible=1`（:96）
- `length(content) > 20` 粗筛 → 注入清洗后 `len(cleaned) > 30`（:97, 141）
- 系统注入剥离（`SYSTEM_INJECTION_PATTERNS`，:38-44；与 build_knowledge_units.py:93-107 重复定义，统一时应合并）
- content_hash 去重（:145-149）
- assistant 专属：13 种工具命令前缀排除（`^\[Bash\]`、`^\[Tool:`、`^\[Thinking\]` 等，:113-127）
- **不剥代码块**：solution 类知识的 evidence_quote 可能就是代码片段，剥离会破坏 quote 回查；prompt 指示 answer 提炼结论即可。

### 窗口策略：单条 assistant 消息 + 前置 user 上下文（QA 对），不做会话窗口

- 实测 gemini 会话 assistant 平均 5,100 字符（CONTEXT specifics），单条信息密度足够，整会话窗口必然超 token（L2 已观测 8.7% 会话截断、最大 237 万字符）。
- 前置 user 消息**只作理解上下文，不作证据**——evidence_quote 必须锚 assistant 原文（D-03，`v1_main.md` 的 speaker gate 在 assistant 轨平移为"只有 role=assistant 的内容能证明该解决方案/结论"）。
- 实现先例现成：`build_knowledge_unit_vector_store._load_user_contexts`（:102-187）已做"锚 assistant 消息 → 同 session 最近前置 eligible user 消息"的解析逻辑（含 sidechain/system 排除、privacy guard），assistant 轨构造 LLM 输入时可复用同一思路取 1 条前置 user 问题拼入 prompt。
- 超长单条：prod 目前无截断；assistant 轨需要 `MAX_CHARS` 截断（建议对齐 L2 `MAX_WINDOW_CHARS=12000`，extract_knowledge_units_l2_session.py:54 的尾部硬截模式 :190-197），**quote 回查对截断后文本执行**，避免抽出来自被截部分的证据。长尾分块属 deferred（CONTEXT deferred 第 2 条），本 phase 不做。

### 确认信号修饰（D-03 落地形态）

后续 user 轮采纳/纠正信号**不进抽取 gate**；落地为 post-extraction 标注：assistant unit 的 `source_session_id` 已知，下一条 user 消息是否含采纳/纠正信号可做 confidence ±/lifecycle 候选（接 `pk-ku reconcile` 的既有 lifecycle 路由，runbook §3F）。本 phase 建议只做**信号检测函数 + 字段修饰**，不做自动 supersede——自动路由属 deferred。

---

## 3. Q3 — 覆盖矩阵实现

### SQL 口径（source × role × pass）

- **source 维度**：`canonical_messages.source`（zcode/grok/qoder/gemini 等；inventory 的 `by_source` 统计同口径，build_knowledge_inventory.py:199）。join `canonical_sessions.agent` 可作辅助列。
- **eligible 消息数**：统一 eligible 函数（Q4）按 `(source, role)` group by 计数。
- **已单元化**：`knowledge_unit_evidence`（多对多并集，eval 已按此口径 `_load_cu_ref_index`，evaluate_knowledge_unit_rag.py:216-227）∪ `knowledge_units.source_message_ref`，按 evidence_ref 去重。**用并集而非单看 source_message_ref**——salvage 后 unit 合法持多 ref。
- **pass 维度**：unit_id 前缀（`v1|`/`l2|`/`ku|`/`as|`）即 pass 族，与 StagingPublisher 的 `substr(unit_id,1,3)` 同口径；或 join `knowledge_build_runs.prompt_version`。ku| 世代命中标 `grandfathered`（D-04 豁免），不计入"未覆盖"。
- **未覆盖原因分类**（三值）：
  - `abstained` / `terminal_failed`：ref 出现在某 run 的 `knowledge_run_items`，取最新 status（terminal_failed 同时应已入 `knowledge_dead_refs`）；
  - `未入队`（not_queued）：eligible 但从未出现在任何 run items——zcode 1032 条 0 KU 就是这一类；
  - 注意区分"eligible 但不在当前轨"（role 决定轨，不算未覆盖）。

### doctor 接入模式

- 新增 `_check_coverage_matrix(db_path, canonical_db) -> CheckResult`，在 `run_doctor` 的 checks.append 序列中注册（doctor_ku.py:604-633）。
- `severity="warn"`、`ok=True` 恒成立（矩阵行级分级放 detail）——**不加入 `hard_fail_ids`**（:646-657），exit code 不受影响，满足 D-06 "WARN 不 FAIL"。
- 行级分级：新 source 首现 → 该行 level=info；已知 source 连续零覆盖 → level=warn。"连续"需要历史参照——最简实现：doctor 把当次矩阵摘要写 `var/reports/analysis/ai_context/ku_coverage_latest.json`（只含 count/hash，隐私安全），下次运行比对；无历史时全部按首现 info。
- 行数控制：source × role × pass 理论 ~80 行，detail 放全量数组（count-only），human 输出（`format_human`:702-730）只打 WARN 行 top N。
- 性能：eligible 全量计算要扫 canonical DB（~80k 消息 + 清洗去重），doctor 是日常命令——建议矩阵计算带 `--skip-coverage` 逃逸口 + 结果缓存（source checksum 不变则复用上次数）。

---

## 4. Q4 — eligible 统一函数

### 三处口径差异清单（精确）

| 维度 | inspect（refresh_knowledge_units.py:121-128） | prepare（:799-813 → build_inventory） | inventory（build_knowledge_inventory.py:80-223） |
|---|---|---|---|
| role 范围 | 仅 `role='user'` | `IN ('user','assistant')`（:98） | 同 prepare |
| 长度阈值 | 原文 `length>20` | 粗筛 >20，清洗后 `>30`（:97,141） | 同 prepare |
| 注入清洗 | 无 | 有（5 组正则 :38-44） | 同 prepare |
| 内容去重 | 无 | content_hash 去重（:145-149） | 同 prepare |
| assistant 工具前缀排除 | 无 | 有（:113-127） | 同 prepare |
| 返回形态 | `set[ref]` | `dict[ref→content_hash]` | items list |
| **items 是否带 role** | — | **否**（:166-176 无 role 字段） | **否** |

（第四处隐性口径：`build_knowledge_units.load_evidence` :200-243 是 L1 旧路径的 role=user 版，统一后应收编或显式标记 legacy。）

**这就是 Gate B 噪声根源**：inspect 数的是"裸 user >20 字"，prepare 数的是"清洗去重后 user+assistant >30 字"，两边对同一 canonical DB 必然给出不同 delta，`inspect 有 delta 而 prepare no_op` 无法区分是缺陷还是口径差。

### 统一函数设计

**位置：新模块 `application/knowledge/eligibility.py`**（不放 build_knowledge_inventory.py 内部——inventory 是"冻结"语义，eligibility 是"判定"语义；inspect 侧 import inventory 模块已经造成过循环倾向的耦合，refresh:801-804 是函数内延迟 import 绕开的）。

```python
@dataclass(frozen=True)
class EligibleMessage:
    evidence_ref: str
    content_hash: str
    role: str                    # user / assistant —— D-05：eligible 与 role 解耦，role 只决定轨
    session_id: str
    source: str
    agent: str
    started_at: str
    has_injection: bool

def compute_eligible_messages(
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    *,
    roles: tuple[str, ...] = ("user", "assistant"),
    exclude_assistant_tool_prefix: bool = True,
) -> tuple[list[EligibleMessage], dict]:
    """唯一 eligible 判定。返回 (items, stats)。stats 含 excluded 分类计数。"""
```

### 收编路径

1. `build_inventory` 改为调用它（roles 全量），items 补 role 字段（**这是 schema 级变化**：`knowledge_inventory_items` 无 role 列——要么加列（迁移幂等 ALTER），要么 items dict 带 role 但落库时仍写旧列；建议加列，覆盖矩阵和 prepare 的 `ref_roles` 二次查询（refresh:1761-1773）都能省掉）。
2. `find_affected_evidence` 改为调用它（inspect 口径 = prepare 口径；role 过滤不下推到 inspect，由 delta 消费方按轨过滤）。
3. `strip_system_injections`/`is_meaningful`/`SYSTEM_INJECTION_PATTERNS` 三处重复定义（build_knowledge_units.py:93-112、build_knowledge_inventory.py:38-54、间接 L2）收敛到 eligibility.py，旧 import 路径保留别名兼容（tests 直接 import 这些名字，tests/unit/test_knowledge_unit_extraction.py 等）。

---

## 5. Q5 — assistant 轨 eval 集

### 格式（照抄 frozen_test_queries.private.jsonl，实测结构）

```json
{"id": "asst-001", "split": "frozen_test_assistant", "query": "<用户会提的检索问题>",
 "gold_evidence_refs": ["cm|<assistant 消息 id>"],
 "allowed_unit_types": ["solution", "decision_rationale", "technical_conclusion"],
 "expected_abstain": false, "expected_conflict": false,
 "group": "assistant_track", "agent": "gemini", "started_at": "..."}
```

- **gold_evidence_refs 语义**：支撑该结论的 **assistant 消息 canonical_message_id**（现行 frozen 集锚 user 消息，:1-3 实测均为 user 提问）。评估命中链已兼容：`evaluate_candidate` 的 ref 并集匹配（evaluate_knowledge_unit_rag.py:496-505，cu → member source_message_ref + knowledge_unit_evidence 全并集）不关心 ref 的 role。
- 规模：20 条起步（CONTEXT discretion；现有 frozen/dev/merge pairs 均 20 条）。
- 标注策略：从 assistant 消息存量（ku| 世代来源会话优先，内容已实测 ~90% 为真）选 15 正例 + 3 应 abstain（纯工具输出/临时回答）+ 2 跨源对照；`expected_abstain` 行驱动 no_answer_false_positive 指标（:174-175）。
- **注意内容匹配兜底失效风险**：`evaluate_raw_baseline`/`evaluate_hybrid` 的 gold snippet 用 `content[:200]`（:111, :163）——assistant 消息平均 5100 字，结论常在中后段，snippet 兜底命中率会低于 user 轨。标注时在 gold 消息的选择或 query 设计上保证 ref 匹配为主路径即可；不必改评估代码。
- 入口接线：`_load_eval_dataset` 的 else 分支（:56）已支持任意 `{name}.private.jsonl`，但 CLI `--dataset` choices 只有三个（:580）——加 `frozen-test-assistant` choice 或加 `--dataset-path` 参数，二选一，改动 1-2 行。
- 抽取层 eval（可选第二块）：`evaluate_knowledge_unit_extraction.py` 的 Gate 8 speaker_attribution（:216-229）只查 user 类型错配 scope；assistant 轨应对称新增"assistant 类型必须 scope='assistant'"检查，1 个 GateCheck。

---

## 6. Q6 — 风险清单

### R1. ku| 世代 × 新 assistant 轨在 canonical 层的重复（中风险，有天然防火墙）

- **时间维不重叠**：assistant 轨只抽 watermark 后增量（D-04），ku| 世代是存量，同一 assistant 消息不会被两条轨各抽一遍。
- **类型维不合并**：`build_canonical` 分桶 key 含 evidence_scope（build_canonical_knowledge_units.py:91）→ 跨 scope 不自动合并；`merge_l2_into_canonical.find_match` 按 unit_type 分候选（:103-105）→ D-01 的独立类型集合使 ku|（旧 6 类型）与 as|（3 新类型）在 find_match 里永不相遇。**D-01 同时充当了跨轨合并防火墙。**
- **残余**：ku| 世代 canonical 与新 as| canonical 可能语义重复但类型不同 → `pk-ku reconcile` 按 `(subject, unit_type)` 分组（runbook §3F）也不跨类型，重复会长期共存。**缓解**：本 phase 只观测不治理——覆盖矩阵/doctor 增加一行"跨类型同 subject 高相似计数"（可选）；治理属 CONTEXT deferred 第 5 条（~5.5k 同 subject 多 answer 组审查）。

### R2. promote 前缀截断约束（低风险，硬约束）

`StagingPublisher.promote` 取 `substr(unit_id,1,3)` 作 pass 族（knowledge_unit_pipeline.py:180）。assistant 轨 unit_id 前缀**必须恰好 3 字符**（如 `as|`）；取 `asst|` 会被截成 `ass` 导致族隔离错位。写进 plan 的验收用例。

### R3. evidence_scope 对下游的影响面（**有一处必须改**）

| 下游 | 位置 | 影响 | 处置 |
|---|---|---|---|
| **EvidenceResolver（证据下钻）** | retrieval/evidence.py:80-81 | message 级证据要求 `evidence_scope=='user'`，assistant 消息的 resolve 返回 `ineligible` → **assistant 轨 KU 的证据链下钻全部被 veto** | **必改**：放宽为 `in ('user','assistant')`（doctor 的 `evidence_resolver` check 视 `ineligible` 为合法状态 :356，不会误报） |
| candidate vector store | build_knowledge_unit_vector_store.py:214-232 | `load_eligible_units` 不按 scope 过滤 → as| units 一旦 current 自动进候选索引（**这是期望行为**，无需改）；`_load_user_contexts` 的前置 user 上下文富化对 assistant 锚点天然适用（:102-187，QA 对策略的红利） | 不改；metadata 补 `evidence_scope` 字段（:330-341 当前没有），供检索层按轨过滤——或利用 unit_type 已在 metadata（D-01 红利）零 schema 成本过滤 |
| semantic_search | retrieval/semantic_search.py | KU 层按 collection 检索，**不按 scope 过滤**；混合层 ku:raw=1:4 slot（evaluate_knowledge_unit_rag.py:357-359）对 assistant 轨内容无 veto | 不改；用户画像视图如需"只看 user 轨"用 unit_type/scope metadata 过滤（D-02 的检索层过滤点） |
| relevance 判定 | retrieval/relevance.py:15,92,108 | evidence_scope 被当 privacy 信号查 `_BLOCKED_PRIVACY={'secret','blocked','excluded','system','private_secret'}`——**'assistant' 不在黑名单，不会误伤** | 不改 |
| extract gate Gate 8 | evaluate_knowledge_unit_extraction.py:216-229 | 只查 user 类型错配；assistant 类型与 user 类型不相交 → 现有 gate 天然通过 | 对称补 assistant 方向检查（见 Q5） |
| eval review packets | evaluation/review_packets.py:482-483 | 只取 scope='user' 的会话/消息 → assistant 轨会话不进评审包 | 本 phase 不改；记入 follow-up |
| run_knowledge_eval | evaluation/run_knowledge_eval.py:167-168 | 只 veto secret/excluded | 不改 |

### R4. 成本与体量（中风险）

assistant eligible 消息 ~73k 条存量 + 增量；若 prepare 首次以 `--roles assistant` 运行且无 watermark 基线区分轨，delta 会把全部存量 assistant refs 当 new。**必须**为 assistant 轨建立独立基线（独立 inventory 或独立 watermark key——`knowledge_source_watermark` 是 key-value 表，可加 `committed_assistant` key），否则第一次 prepare 就是 7 万条全量队列，撞上 Gate A（runbook §Step A 大批量需人工批准）和硬规则 2（禁止日常全量）。这是 plan 划分里最需要先想清楚的一点。

### R5. merge 阈值未校准（低风险，已知债务）

`compute_similarity` 已换 char 4-gram Jaccard，但 `MERGE_SIMILARITY_THRESHOLD=0.85`/`ANSWER_SIM`/`SUBJECT_SIM` 是词级 Jaccard 时代经验值（build_canonical_knowledge_units.py:96-115 注释自认未校准）。assistant 轨 answer 更长（solution 类），4-gram 相似度分布不同——assistant eval 集建立后顺带校准，不做独立工作项。

### R6. inspect 口径切换的瞬时噪声（低风险）

eligible 统一后 inspect 的 new_refs 口径突变（纳入 assistant + 清洗去重），首次运行会出现大 delta——属预期，在 plan 验收中写明"首次切换 delta 突增是口径修正不是缺陷"，避免触发 runbook Gate B 的 STOP 反射。

---

## 7. Q7 — Plan 划分建议（4 个 PLAN）

| Plan | 范围 | 任务边界 | 依赖 | 预估 |
|---|---|---|---|---|
| **41-01 eligible 口径唯一化**（EXT-03） | 新建 `eligibility.py`；收编 inspect/inventory；`knowledge_inventory_items` 加 role 列；三方共用；回归测试证明 inspect/prepare delta 一致 | **不含** assistant 抽取、不含 doctor | 无 | 中（纯 Python + 迁移，无 LLM） |
| **41-02 assistant 轨抽取器**（EXT-01 核心） | prod 引擎 track config 化（prompt/scope/prefix/validator 注入）；`v1_assistant.md` prompt；QA 对输入构造 + 12000 截断；`as|` 前缀；`--track`/`--roles` 接线；assistant 独立 watermark key；pilot 20 条 smoke | **不含** eval 集、不含 doctor | 41-01（eligible 函数提供轨道输入） | 大 |
| **41-03 覆盖矩阵 + doctor**（EXT-02） | 覆盖 SQL（eligible/已单元化并集/未覆盖三分类）；doctor `_check_coverage_matrix`（warn-only，不进 hard_fail_ids）；历史快照比对分级；ku| 豁免标注 | 41-01（eligible 唯一口径是矩阵的分母）；与 41-02 可并行 | 中 |
| **41-04 eval 集 + 下游 scope 贯通 + 端到端**（EXT-01 收尾） | 20 条 assistant eval 集；evaluate CLI 接新 dataset；Gate 8 对称检查；evidence.py:81 放宽；vector metadata 补 scope；merge 阈值随 eval 校准；一次完整 canary→strict→promote 走通 | 41-02、41-03 | 中 |

顺序：41-01 →（41-02 ∥ 41-03）→ 41-04。会话去重键（Phase 42）依赖本 phase 的 eligible/证据口径稳定，ROADMAP 已声明（:146）。

---

## 8. 验证策略

### Nyquist Validation Architecture

每类行为在最小样本上验证一次，不做重复全量测试。按"行为类"划分最小充分集：

| 行为类 | Nyquist 用例（每类 1 个代表） | 层 |
|---|---|---|
| eligible 等价性 | 同一 fixture canonical DB：inspect 的 current_refs == prepare 的 after_hashes（集合相等，差集=0）——Gate B 噪声的回归锁 | unit（fixture sqlite，tests/fixtures 模式） |
| role 解耦 | 同一消息集按 roles=('user',) / ('assistant',) / 全量调用，role 只影响分组不影响 eligible 判定 | unit |
| assistant prompt schema | 模拟 LLM 返回 → assistant ExtractionResult 接受 3 新类型、拒绝 6 旧类型 | unit |
| quote 回查 | quote 锚 assistant 原文过 `_evidence_supported`；锚被截断部分 → drop | unit |
| run 级单轨 | `--track assistant` 的 run manifest 记录 prompt_version=v1_assistant；run items 全为 assistant refs | unit/integration |
| promote 前缀隔离 | as| run promote 不触碰 v1|/l2|/ku| current 行（prefix 恰好 3 字符的断言） | unit |
| 覆盖矩阵 SQL | fixture DB 造 3 类未覆盖（abstained/terminal_failed/not_queued）+ 1 个 ku| 豁免行，断言分类计数 | unit |
| doctor 注册 | coverage check 出现在 report、severity=warn、exit_code 不受矩阵内容影响 | unit（参照 tests/unit/test_doctor_ku.py 既有 probe 注入模式） |
| eval 集加载 | 新 jsonl 被 `_load_eval_dataset` 解析、20 条字段齐全、gold refs 在 canonical DB 存在 | unit |
| evidence resolver 放宽 | assistant scope 消息 resolve → ok（不再 ineligible） | unit |

### 集成 / 端到端（手动门，付费步骤需人工批准）

1. `pk-ku inspect`（切换后首次）delta 突增解读为口径修正（R6）。
2. `pk-ku prepare --roles assistant --track assistant` → artifact `extract_item_count` 符合预期、`active_changed=false` 等安全字段全 false。
3. `pk-ku extract --run <ir_*> --max-items 20` pilot smoke（Vertex 付费，需批准）→ `pk-ku status` 验收 succeeded/abstained 分布。
4. `pk-ku extract-gate`（含对称 Gate 8）→ `canonical --write` → `publish --write` → `vector --write`。
5. assistant eval 集跑 `evaluate_candidate`（Recall@5 基线记录，不预设阈值，首轮用于校准）。
6. `pk-ku canary … --strict` PASS → `promote --require-eval-pass` → `watermark --advance`（assistant 轨独立 key）。
7. `pk-ku doctor --skip-ports`：coverage check 出现且 doctor 整体 exit 0。

### 不做

- 不重抽 ku| 世代（D-04）；不拆 user 轨 speaker gate；不动 L2 prompt 疆域/窗口（deferred）；不做确认信号自动 supersede（本 phase 只做信号修饰）；不动会话去重键（Phase 42）。

---

## 9. 关键 file:line 速查

| 主题 | 位置 |
|---|---|
| inspect eligible（裸 user >20） | refresh_knowledge_units.py:121-128 |
| prepare eligible（→ build_inventory） | refresh_knowledge_units.py:799-813 |
| inventory 过滤全集（清洗/去重/tool 前缀） | build_knowledge_inventory.py:91-176 |
| prepare roles 元数据 | refresh_knowledge_units.py:1702, 1751-1776 |
| prod ledger/claim/熔断 | build_knowledge_units_prod.py:272-372, 609-877 |
| prod 硬编码点（prompt 包装/scope/前缀） | build_knowledge_units_prod.py:211, 576, 591 |
| L2 jobs ledger（复刻对象，但勿用于 assistant 轨） | extract_knowledge_units_l2_session.py:58-73 |
| `_evidence_supported` 回查 | extract_knowledge_units_l2_session.py:80-93 / prod:474-488 |
| promote pass 族前缀（3 字符） | knowledge_unit_pipeline.py:163-211 |
| canonical 分桶含 scope | build_canonical_knowledge_units.py:82-93 |
| find_match 按类型分组（跨轨防火墙） | merge_l2_into_canonical.py:103-124 |
| 前置 user 上下文解析（QA 对先例） | build_knowledge_unit_vector_store.py:102-187 |
| vector metadata（无 scope 字段） | build_knowledge_unit_vector_store.py:330-341 |
| evidence resolver user-only veto（**必改**） | retrieval/evidence.py:80-81 |
| relevance 黑名单（assistant 安全） | retrieval/relevance.py:15, 108 |
| Gate 8 speaker_attribution | evaluate_knowledge_unit_extraction.py:216-229 |
| doctor 注册/hard_fail_ids | doctor_ku.py:604-633, 646-657 |
| eval 数据格式 / 加载 / choices | evaluate_knowledge_unit_rag.py:49-59, 580 |
| evidence_scope CHECK 已含 assistant | migrate_add_knowledge_unit_tables.py:109 |
