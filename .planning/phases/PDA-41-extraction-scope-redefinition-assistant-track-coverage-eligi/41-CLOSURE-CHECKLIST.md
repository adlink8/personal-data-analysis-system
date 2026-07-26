---
phase: 41
doc: closure-checklist
created: 2026-07-26
status: open
source: 2026-07-26 全量梳理（4 路并行架构/数据流/评估/规划核查 + 生产库只读实测）
---

# Phase 41 收尾执行清单（P0 管线闭合）

> Phase 41 代码侧四个 wave 已完成（41-01..41-04）。本清单覆盖执行侧收尾：
> 从当前正在跑的 assistant 轨抽取，到 watermark 推进与状态对齐。
> 数据质量债（截断上限、QA 联立 v2、confidence 等）**不在本清单**——
> 已登记于 `41-CONTEXT.md` / `../PDA-42-conversation-dedup-with-stable-session-keys/42-CONTEXT.md`
> 的 deferred 段；跨里程碑项见 `ROADMAP.md` 的 Backlog（999.x）。

## 前置事实（2026-07-26 实测基线）

- Active collection `knowledge_units_salvage_v1_b_20260726021631`（32,382 向量）；
  frozen-test Recall@5 = 0.35 / MRR@5 = 0.325（安全项全干净）——assistant 轨
  收编即本 phase 的召回修复主线。
- `committed_assistant` watermark key 已存在，值为空，待本清单末步提交。
- F-13 后 watermark 前置检查扫描**所有** run 的 pending/in_flight/retryable
  （`refresh_knowledge_units.py:1278`），且 `acknowledge_dead_refs()` 只覆盖
  terminal_failed——pending 无内置作废通道，故需第 2 步的迁移脚本。

## 执行步骤（顺序执行，全部 fail-closed）

- [ ] **1. assistant 轨抽取跑完** — `ir_13486f30c029db49` 续跑至队列清空
      （2026-07-26 快照：succeeded 2,721 / abstained 7,092 / pending ~5,389 /
      retryable 26 / terminal_failed 186）。**中途不得改 prompt/schema**
      （cache key 含 prompt_hash，改动分裂缓存命名空间）。
      **血缘备注（2026-07-26）**：flash-lite 撞 Vertex DSQ 429 持续数小时,
      经 8 条探测确认后剩余 pending 切换 `--model gemini-3.5-flash` 续跑
      （操作者决定）——本 run 为**混合模型 run**（~9.9k 条 flash-lite +
      ~5.4k 条 flash）;pending 无旧缓存,无缓存分裂;prompt/schema 未变。
      eval 基线报告应注明混合模型构成。
- [x] **2. 作废两个孤儿 run（2026-07-26 完成）** — 22,450 + 18,102 条 open
      → terminal_failed(run_abandoned) 并登记 dead_refs,两 run 置 aborted。
  - `6f3da1eec…`：2026-07-16 全量 extraction 误启动残留（22,434 pending +
    16 僵死 in_flight + 1 未 ack terminal_failed）
  - `ir_ab6d20f78da2038d`：同日增量队列（18,102 pending，0 处理），27 分钟后
    被 sibling `ir_4cd8af4ad` 覆盖同一 delta 并走完全流程，属重复铸造弃用
  - 脚本已 dry-run 验证（作废 22,450 + 18,102 open items）；带 24h 活跃护栏
    （实测拒绝活跃 run）；不删行、幂等、登记 `knowledge_dead_refs`、run →
    `aborted`。**在抽取跑完后执行**（避免与抽取写线程争 SQLite 写锁）。
- [x] **3. unit_type CHECK 迁移** — 已 apply（2026-07-26 复核 no_op）;
      assistant watermark bootstrap 亦已 `--write`（committed_assistant =
      committed 基准值,防误触全量重排队）。
- [ ] **4. 主流程贯通** — 进行中（2026-07-26）:
  - [x] extract-gate **10/10 PASS**（--min-yield 0.28 pilot 阈值;实际
        yield 0.360、schema 0.9959、总失败率 0.41%;7,818 units;
        61 条 terminal API 错误经 flash 重试全部清零 +61 units）
  - [x] canonical --write（7,818 全 singleton,零冲突;
        by_type: solution 4,249 / technical_conclusion 2,759 /
        decision_rationale 810）
  - [x] publish --write（纯 additive,demoted=0,canonical current 总量
        40,203;前缀隔离验收 ✓:v1|/l2|/ku_ current 计数不变 32,992,
        as| 7,818 staging→current）
  - [x] vector --write（40,200/40,200,missing/orphan/duplicate=0,gate PASS,
        candidate `knowledge_units_ir_13486f30c_20260726153705`;期间发现并
        恢复 Chroma 依赖,见下方运维发现）
  - [x] frozen-test 回归 eval:R@5 **0.65**(与 active 持平,无回归),
        MRR 0.60(-2.5pp,单条位移噪声级);安全项全 0
  - [x] assistant 轨首轮基线(只记录):R@5 **0.25** / MRR 0.15 —
        下轮质量迭代靶子=4c lite 弃答复验 + QA 联立 v2
  - [x] canary --strict **PASS**(helpful 100%,wrong+stale=0,fallback=0,
        p95 187ms;LLM 打标 vertex flash)
  - [x] promote --require-eval-pass(canary_strict gate 文档,沿 salvage
        先例;active: salvage_v1_b → `ir_13486f30c_20260726153705`,可回滚)
  - [x] serving snapshot 收口:promote 后 doctor 报 source_watermarks drift
        (knowledge_retrieval 成员未绑 watermark + canonical_knowledge 绑旧
        水位)→ `serving.snapshots bootstrap --eval-gate … --write` +
        `validate` + `activate` 铸造 `ss_470b5cb907970d1352aee145` 全角色
        重绑,drift 清零。**注意:promote 的快照铸造存在 watermark 绑定缺口,
        每次 promote 后需 bootstrap+activate 收口(或修 promote,归 999.1)**
  - **已知问题(登记,不阻塞)**:canonical 的 Merge Gate 恒 FAIL 属评测绑定
    失效——`integration/evals/knowledge_units/merge_positive_pairs.private
    .jsonl` 的 ref 是 `cm|` 消息 ID,而 `canonical_unit_members` 存 unit ID,
    ID 空间不匹配→40 ref 0 命中,recall 恒 0。系 ID 方案变更后的历史遗留,
    publish 不依赖此 gate。修复=按 unit-ID 空间重生成配对,归入 Backlog
    999.5(gold/评测数据工程)。
- [x] **4b. schema_invalid 根因修复 + 零成本回收（2026-07-26 完成）** —
      诊断:164 条 schema_invalid 主因是 ① 多 unit 响应第 2 个起缺 question /
      带 extra 字段(全有全无校验连坐好 unit,94 条)、② Windows 路径反斜杠
      非法 JSON 转义(70 条)。修复:`_tolerant_parse` 抢救层
      (`build_knowledge_units_prod.py`,严格路径不变;单测
      `tests/unit/test_extraction_salvage_parse.py` 9 项)+
      `tools/migrations/requeue_schema_invalid.py` 重排队,缓存命中重裁,
      **零 LLM 成本回收 107 条 succeeded + 123 个 unit**。
      残余 terminal_failed = 82(55 深度损坏 + 27 terminal API),
      随 `--acknowledge-failures` 落 dead_refs。schema_validity 预计
      完跑后 ~0.98(>0.95 gate)。注意:extract-gate 的 minimum_yield 需要
      pilot threshold(`--min-yield`),完跑后按实际 yield(~0.18-0.2)设定。
- [ ] **4c. lite 弃答复验（可选,promote 后做,~$0.5）** — 混合模型 run 实测
      弃答率:flash-lite 70.8% vs flash 48.2%（差 23pp,群体非随机分组,仅
      提示性）。从 lite 弃答的 7,099 条中抽 100 条样本用 flash 重跑
      （cache key 含 model,天然不冲突）:flash 抽出 unit 比例 >20-30% →
      对 lite 全部弃答定向补抽（≈$7）;比例低 → lite 弃答判定可信,结案。
- [x] **5. watermark 推进（2026-07-27 完成）** — `committed_assistant` 首次
      提交(=canonical checksum 87e24e2a…),188 条 terminal_failed 落
      dead_refs(本 run 63 schema 深损 + 历史 125),dead_refs 总量 40,741。
- [x] **6. 终验（2026-07-27 完成）** — `pk-ku doctor --skip-ports`
      **status OK, exit=0**,全部 check 绿;coverage matrix 4 行 all ok,
      无零覆盖警告。

## 验收标准（全部达成,2026-07-27）

- [x] promote 前后 `v1|` / `l2|` / `ku_` 世代 current 计数差为 0
      （32,992 不变;as| 7,818 staging→current）
- [x] watermark 双 key 分立：`committed_assistant` 非空且 `committed` 不变
      （仍为 2026-07-16T04:08:13Z 原值）
- [x] assistant eval 报告落盘：`ku_eval_ir13486_assistant_20260726.json`
      （R@5 0.25 首轮基线,不设阈值；第二轮起按 Backlog 999.5
      单人简化协议设定——先抓回归后设绝对线，见
      `../999.5-eval-simplification-gold-expansion/999.5-NOTES.md`）
- [x] doctor coverage 矩阵 check 通过,新源以 INFO 显形,无零覆盖 WARN

## 运维发现（2026-07-26 夜,登记勿丢）

- **Chroma 依赖外部项目**：向量层的 Chroma :8001 实际是
  `D:\ADLINK\Myproject\novel-mind\docker-compose.yml` 里的服务
  （容器 novel-mind-chroma-1,数据在命名卷 chromadata）。Docker 引擎重启
  会导致本系统向量层静默离线。本项目文档此前无任何记载。
  恢复命令:`docker compose -f D:\ADLINK\Myproject\novel-mind\docker-compose.yml up -d chroma`。
  **治本归 Backlog 999.1**:把 Chroma 迁入本项目自己的 compose/启动脚本,
  或至少写进 docs/runbooks + start-services 健康检查。
- 中断的向量构建残留集合 `knowledge_units_ir_13486f30c_20260726151211`
  （未注册 candidate）待 GC。

## 收尾对齐（完成上述后立即执行）

- [ ] **状态文件对齐**：`STATE.md`（现为未提交修改，写着 "Phase 36 —
      EXECUTING"）改指 v1.4.1 / Phase 41 实际状态；`ROADMAP.md` Phase 41
      从 "Discuss" 更新；就绪分以 `PRODUCT-READINESS.md` 为准修
      `AGENTS.md` 头部（86 vs 89 不一致）。
- [ ] **工作区清理**：审查 `services/api_server.py` 未提交修改——属 Phase 41
      的随本 phase 提交，不属的显式决定保留/丢弃。
- [ ] **治理测试陈旧断言**：`tests/governance/test_governance_planning.py::
      test_phase17_remains_open_and_consistent` 断言 `"17 | 4/4 code"`，但
      ROADMAP 在 v1.4 注册重写时已将 Phase 17 行移入里程碑归档——存量失败
      （HEAD 即失败，非本次重组引入；checker 本体 PASS）。随状态对齐一并更新
      断言到当前 ROADMAP 结构。
