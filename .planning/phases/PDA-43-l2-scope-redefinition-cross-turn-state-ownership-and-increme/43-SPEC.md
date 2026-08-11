# Phase 43: L2 Scope Redefinition (Cross-turn State Ownership and Incremental Dedup) — Specification

**Created:** 2026-07-27
**Ambiguity score:** 0.19 (gate: ≤ 0.20)
**Requirements:** 4 locked (L2G-01..04)

## Goal

把 L2 从"L1 补漏"重定义为"跨轮状态变更所有者 + 增量去重守门"：同一事实不再被 L1/L2 反复产出平行重述 unit，目录/分支/阶段/计划类状态知识沿 supersede 链获得可查的"当前值/历史值"时效语义。

## Background

- L1（`build_knowledge_units.py`）逐条 message 调 LLM 抽取；L2（`extract_knowledge_units_l2_session.py`）按 session 窗口抽取。两者都只面向"watermark 后新增证据"，**互不感知对方和已有 canonical 存量**——同一事实在后续会话被再次提及时，会再产出一条平行重述的 current unit。Phase 41 ⑧ conflict 治理一轮就清了 294 个 q-gated 重复对（commit `81cabbc`），证明这不是偶发而是结构性缺门。
- 目录路径、git 分支、项目阶段、计划安排这类**状态类知识**天然是跨轮变更的（今天的值 supersede 昨天的值），但现在 L1 逐 message 抽取把它们当静态事实反复产出 current；L2 名义上按 session 看跨轮，实际只有 815 条 unit（staging 44,880 条中占 1.8%），且定位是"补漏"而非"所有者"。
- 时效语义缺失：supersede 链已存在（canonical 终态 current 39,880 / superseded 309 / deprecated 212 / conflict 16），但查询侧无法区分"这是某 subject 的当前值"还是"历史值"，状态类 unit 和普通事实混在一起。
- Phase 42-03 的 inspect delta（new_refs=1,995 / deleted_refs=12,496 / affected_subjects=8,100）已归因：**88% 是 Phase 41 eligibility 收紧的口径账**（56% 工具前缀 + 32% 清洗后 ≤30 字），不是会话合并副本退出。deleted refs 对应 11,008 条 staging unit 与存活 unit 内容重复率仅 2%——其中含从 bash/工具输出抽出的真知识（Maven 损坏、SDK 路径、WHEA 等），一刀切 deprecate 会埋掉它们，已按 42-03 STOP 判据中止处置，待本 phase 分级处理。
- watermark 因 42-03 gate 未过而**故意未推进**；inspect 的 delta 会持续挂着，直到本 phase 给出收敛方案。

## Requirements

1. **L2G-01 增量去重守门**: L1/L2 抽取时注入同 subject 的已有 canonical 清单，新抽 unit 与已有等价时标 supersede 而非新增 current。
   - Current: L1/L2 prompt 只含当次证据窗口，无已有知识上下文；等价事实重复产出 current unit，靠事后 ⑧ conflict 治理批清理（一轮 294 对）。
   - Target: 抽取前按 subject（索引或 embedding top-k，具体机制留给 discuss-phase）拉取该 subject 已有 canonical 清单注入 prompt；LLM 判定"与已有等价"时输出 supersede 指向而非新 current；管线落库时尊重该指向。
   - Acceptance: 构造一组"同一事实在两个会话重复出现"的测试会话重跑抽取，平行重述新增 current 数相对基线（无注入对照 run）显著下降；治理链上能看到对应的 supersede 记录而非堆积的重复 current。

2. **L2G-02 状态类知识归属 L2**: 目录/分支/阶段/计划类 subject 归 L2 跨轮管辖，L1 不再为这些 subject 产出新的 current unit。
   - Current: 状态类事实由 L1 逐 message 当静态事实抽取，每个新值都是独立 current，靠人工/治理批事后串链；L2 无 subject 管辖清单。
   - Target: 维护一份状态类 subject 清单（显式配置 + 可扩展）；双轨 run 中这些 subject 的抽取只走 L2，L1 产出被拦下或落为 candidate 而非 current。
   - Acceptance: 给出 subject 清单与一次双轨 run 的记录：清单内 subject 的 L1 current 新增 = 0（或全部 candidate 标记），L2 侧有对应 unit 或显式 no-change 记录。

3. **L2G-03 时效语义可查**: 状态类 unit 沿 supersede 链可区分"当前值/历史值"，查询侧可读，不新增 schema 字段。
   - Current: supersede 链存在（`superseded_by` 等既有 lifecycle 字段），但检索/查询层不暴露"当前值 vs 历史值"语义；状态类与普通事实 unit 无类型区分。
   - Target: 复用现有 lifecycle 链 + unit_type/subject 清单，在检索与治理接口提供"某 subject 当前值"视图；历史值沿链可回查。明确不做 `valid_from/valid_to` 新列（避免 schema 大改，discuss 若有更强证据可复议）。
   - Acceptance: 对一个有 ≥2 次变更的状态类 subject，查询接口返回唯一"当前值"unit 且能列出其历史链；不新增任何 SQLite/Chroma schema 字段。

4. **L2G-04 工具输出源知识分级处置**: 11,008 条源消息被 41 新口径排除的 staging unit 先分级再处置，并给出 inspect delta 收敛（watermark 推进）方案。
   - Current: 这些 unit 源消息是 `[Bash]`/`[Read]` 等工具前缀输出；与存活 unit 内容重复率仅 2%，含真知识；42-03 一刀切 deprecate 已 STOP，挂账未决。
   - Target: 抽样 + LLM 分级（真知识 / 噪音 / 与存量重复三档）后按治理链分批处置（保留转正 / supersede / deprecate）；同时明确"面向未来工具输出不进抽取"与存量的边界；给出 watermark 推进时机与 delta 收敛的执行笔记。
   - Acceptance: 产出分级报告（三档数量 + 抽样依据）；治理链上有逐批（≤50/批、逐对检视）处置记录；执行笔记写明 watermark 推进或继续挂起的判据，inspect delta 不再是无归因的黑盒。

## Boundaries

**In scope:**
- 抽取侧已知清单注入机制（subject 索引或 embedding top-k，机制选择属 discuss-phase）
- 状态类 subject 清单与 L1/L2 管辖路由
- 复用现有 supersede 链的"当前值/历史值"查询视图
- 11,008 条存量 staging unit 的分级报告与治理链处置
- watermark 推进/delta 收敛的执行笔记（含 42-03 gate 遗留的收尾判定）

**Out of scope:**
- Google 数据源知识单元化 — 独立数据源（google_activities→normalized→assertion 链）从未进 staging，需要自己的数据源 phase，不在本 phase 顺带做
- QA v2 abstain prompt 约束调优 — Phase 41 已记 deferred（A/B：v1 25/v2 18/tie 7，v2 过度 abstain 19/50），属评测 prompt 迭代
- 全量重抽存量 — 41 ⑨ 已决策不重抽存量，本 phase 的去重守门只面向增量
- L1 抽取 prompt 大改版（unit_type 集合、输出 schema 重设计）— 本 phase 只加注入段
- `valid_from/valid_to` 时效新字段 — 决策沿用 supersede 链，避免 schema 变更（L2G-03 已锁定）

## Constraints

- 治理链铁律：manifest 链完整、不硬删 knowledge 行、每批 ≤50 且逐对检视、改库前 `cp` 快照到 `var/backups/`
- 不动运行中途的 prompt（prompt_hash 分裂会破坏缓存与可比性）；注入段作为新 prompt 版本处理
- Vertex 调用：gemini-3.5-flash-lite + 6s 间隔 + 429 冷却 65s；`PERSONAL_DATA_GCLOUD="$HOME\google-cloud-sdk\gcloud.bat"`
- python 命令加 `PYTHONIOENCODING=utf-8`
- 新代码 import `application.*` / `evaluation.*`，不写 `domains.*`
- 日常只抽 watermark 后 new；全量 `--start` 需 `PK_KU_ALLOW_FULL_INVENTORY_START=1`（本 phase 的对照实验如需全量，走实验库而非动 canonical）

## Acceptance Criteria

- [ ] 重复事实测试会话重跑抽取，平行重述 current 新增数相对无注入对照显著下降，supersede 记录可见
- [ ] 状态类 subject 清单存在且双轨 run 中清单内 subject 的 L1 current 新增 = 0（或全部 candidate）
- [ ] 对 ≥2 次变更的状态类 subject，查询返回唯一当前值 + 完整历史链，且未新增 schema 字段
- [ ] 11,008 条 staging unit 的三档分级报告落盘，治理链有逐批处置记录
- [ ] 执行笔记写明 watermark 推进或继续挂起的判据与依据，inspect delta 有归因
- [ ] `pk-ku doctor` 保持 exit=0，相关 pytest 全绿

## Ambiguity Report

| Dimension          | Score | Min  | Status | Notes                                              |
|--------------------|-------|------|--------|----------------------------------------------------|
| Goal Clarity       | 0.85  | 0.75 | ✓      | "从补漏到守门+所有者"有基线数据支撑                 |
| Boundary Clarity   | 0.85  | 0.70 | ✓      | Google/QA prompt/全量重抽/L1 大改均显式排除         |
| Constraint Clarity | 0.75  | 0.65 | ✓      | 治理链铁律与 Vertex 配额来自前序 phase 实操          |
| Acceptance Criteria| 0.75  | 0.70 | ✓      | 各条有对照 run / 计数 / 报告落盘的可判 PASS/FAIL    |
| **Ambiguity**      | 0.19  | ≤0.20| ✓      |                                                    |

Status: ✓ = met minimum, ⚠ = below minimum (planner treats as assumption)

## Interview Log

Auto permission 模式：`--auto` 风格，无交互问答。以下为 auto-selected 决策及依据。

| Round | Perspective     | Question summary                          | Decision locked                                                  |
|-------|-----------------|-------------------------------------------|------------------------------------------------------------------|
| 1     | Researcher      | 重复 unit 是偶发还是结构性？               | 结构性缺门：41 ⑧ 一轮 294 q-gated 对；L1/L2 均无存量感知（auto）  |
| 2     | Researcher      | L2 现状能否直接承接"所有者"角色？          | 不能，仅 815 条且定位补漏；需重定义而非停用（auto）                |
| 2     | Simplifier      | 注入机制选 subject 索引还是 embedding？    | 不在 SPEC 锁定，留给 discuss-phase；两案都在验收标准内（auto）     |
| 3     | Boundary Keeper | Google 数据单元化要不要并入？              | 排除：独立数据源链，值得自己的 phase（auto，用户曾点名但属另一疆域） |
| 3     | Boundary Keeper | 时效语义是否加 valid_from/to 字段？        | 否：沿用 supersede 链，schema 零变更；discuss 可凭证据复议（auto） |
| 4     | Failure Analyst | 11,008 条 staging unit 最大风险是什么？    | 一刀切 deprecate 埋掉工具输出源真知识（重复率仅 2%）→ 先分级（auto）|
| 4     | Failure Analyst | watermark 一直不推进会怎样？               | inspect delta 永久挂账、Gate B 失真 → L2G-04 必须含收敛判据（auto）|

---

*Phase: 43-l2-scope-redefinition-cross-turn-state-ownership-and-increme*
*Spec created: 2026-07-27*
*Next step: $gsd-discuss-phase 43 — implementation decisions (注入机制、subject 清单维护方式、分级流水线选型)*
