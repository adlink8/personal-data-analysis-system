---
session: 2026-07-27
model: deepseek-v4-pro[1M]
milestone: v1.4 Decision Cockpit UI
target: 完成 v1.4 以解除 v1.5 Personal Knowledge Wiki Projection 激活门槛
---

# 会话工作状态 — 2026-07-27

## 整体进度

| 阶段 | 计划数 | 完成 | 状态 |
|---|---|---|---|
| Phase 36 安全 Projection 基线 | 4 | 4/4 | ✅ Closed,独立验证 4/4 PASS |
| Phase 37 状态/External/证据真值 | 3 | 3/3 | ✅ Closed,独立验证 4/4 PASS |
| Phase 38 受控决策工作区 | 3 | 1/3 | 🔄 38-01 完成,38-02 执行中 |
| Phase 39 反馈/主动/运行时 | 4 | 0/4 | ⏳ |
| Phase 40 产品硬化 + UAT | 3 | 0/3 | ⏳ |

## 并行完成的工作

- **docs/wiki 准确性审计**(`70804ca`):11 篇运维文档逐篇核验,7 篇完全准确,4 处修正,4 项待决策。
- **v1.5 契约对齐预审**(`3ce8d7d`):对照 Phase 36/37 真实契约预审 WIKI-01 preflight 清单。关键发现:evidence_resolve 超前于 preplan 认知(可直接复用);D4 风险——Goal 主题键需要 predicate 但 Decision 权威无此字段。

## 关键发现与待决策

### DEC-01 后端字段缺口
Phase 38 代码审查确认 `decision_workspace.get` 目前只有 5 个真实字段(target/expected_benefit/costs_constraints/assumptions/contraindications)。DEC-01 蓝图中的目标/硬约束/风险预算/不行动基线/机会成本/停止条件/多候选比较在后端不存在。前端已诚实渲染"未提供",不伪造数据。Phase 38 验证时 DEC-01 可能判 PARTIAL——需要决定是接受"诚实未提供"作为本阶段边界,还是插 decimal phase 补后端。

### 共享工作树约定
此会话执行期间,另一个会话在同步进行 `.planning` 文档重组和 Phase 41/42 知识管线工作。提交严格遵守显式文件路径暂存,零跨会话污染。

## 提交记录

### Phase 36 (12 提交)
```
4ac1400 feat(36-01): 集中定义 Cockpit Origin 与 CORS 响应策略
da954a1 feat(36-01): 在所有受控 session 写入前执行 Origin gate
4e32053 fix(36-01): 收紧静态 Cockpit 与 transport 错误的公开信息
e3994d8 docs(36-01): complete secure transport and cockpit baseline plan
ae80a01 feat(36-02): 定义 Projection 安全公开 limitation/error 目录并修复 run_missing 误判
302360d feat(36-02): 补物理只读边界回归——权威库指纹与写拒绝证明
be8c931 feat(36-02): 锁定 decision/proactive authority vocabulary,闭合未知态提升缺口
c54ec7c docs(36-02): complete safe projection envelope plan
e33eb43 feat(36-03): 把每个 Projection schema 绑定到 v1 和预期 operation
95c9470 feat(36-03): 保持相对同源客户端与安全错误映射的回归覆盖
e22c911 fix(36-03): 修正 Overview 的 confirmation 与 proactive score 展示
ff3ae8d docs(36-03): plan 36-03 execution summary
abe4fe9 chore(36-04): 收紧 Cockpit 忽略清单 + 审计基线边界
9cdf7d7 docs(36-04): 新增 Cockpit 可复现运行 runbook（PowerShell）
70b2098 docs(36-04): 填充 Phase 36 验证记录（真实命令/证据/环境说明）
140579e docs(36-04): plan 36-04 execution summary
1b1cdc4 docs(37): Phase 37 收口——回填验证记录,进度 3/3 Closed
```

### Phase 37 (12 提交)
```
af7cc05 feat(37-01): 扩展 Projection 权威元数据与 canonical External DTO
ccf18c2 feat(37-01): 实现快照绑定的只读证据解析 Projection 与 REST 路由
ccd47ff feat(37-01): 同步客户端 schema、hooks 与受控真实响应 fixtures
4126875 docs(37-01): plan 37-01 execution summary
dd9716e feat(37-02): 建立共享的 claim、lifecycle、authority 与服务端 freshness 视觉语义
8105b6c feat(37-02): 更新 Overview 与 Personal State 的八领域真值展示
7f02d57 feat(37-02): 按独立 External authority 渲染来源、时效、冲突与显式限制
61e7538 docs(37-02): plan 37-02 execution summary
8040c66 feat(37-03): 实现通用只读 Evidence Drawer 与 stable-reference 调用链
fee86ad feat(37-03): 从状态、External 与决策工作区接入同一证据下钻
79828b9 feat(37-03): 收口 Evidence 页面与跨源 MCP Widget 的诊断降级
14a22c4 docs(37-03): plan 37-03 execution summary
```

### Phase 38 (进行中)
```
1db53e5 feat(38-01): 实现 DEC-01 完整决策比较与持续可见的 Personal snapshot 上下文
27167bb feat(38-01): 把只读工作区到会话的 handoff 约束为 fail-closed 资格门
5dfa4c3 docs(38-01): plan 38-01 execution summary
ba1dada feat(38-02): 收口浏览器编排 client 的安全重试/恢复边界
```

### 并行审计
```
70804ca docs(wiki): 2026-07-27 准确性审计——修正过时命令/路径/引用
3ce8d7d docs(v1.5-preplan): 契约对齐预审——对照已执行的 Phase 36/37 真实契约
```

## 测试基线

| 套件 | 基线 |
|---|---|
| Python 契约(ui_projection ×4 + evidence + transport + orchestration) | 102 passed |
| 前端 Vitest | 214 passed(19 文件) |
| 前端 build(tsc --noEmit + vite) | 通过 |

## 下一步

1. 完成 38-02(ConfirmDrawer exact preview) → 38-03(typed recovery + negative tests)
2. Phase 38 独立验证
3. Phase 39(4 计划,严格串行——ui_projection.py 贯穿全部)
4. Phase 40(3 计划,真实浏览器 UAT)
5. v1.4 里程碑审计 → 解除 v1.5 Wiki 激活门槛

---

# 并行会话独立工作记录 — 2026-07-26/27

> 本段记录与上方 Cockpit 会话**并行执行**的另一会话工作(项目根 D:\ADLINK\数据分析,
> 分支 main)。两个会话严格遵守显式文件路径暂存,零跨会话提交污染,共享 Claude Code
> 会话通知机制核对进度。

## 并行会话目标

**v1.4.1 Data Layer Remediation**:
- Phase 41 抽取疆域重定义(assistant 轨收编) — 全链闭合,active 40,200 向量
- Phase 42 会话去重稳定键 — 研究+计划完成,待执行
- 项目全局梳理 + 架构/数据/评估体系优化 + 规划文档重组 + 评测简化协议

## 并行会话进度

| 阶段 | 状态 |
|---|---|
| Phase 41 抽取疆域重定义 | ✅ **Complete 2026-07-27** — 全链闭合,doctor OK |
| Phase 42 会话去重稳定键 | ✅ **Planned 2026-07-27** — 3 plans,checker 复检 PASSED |
| 999.5 评测简化协议 | ✅ 种子笔记+policy v3 草案+评审台 UI,待人工核对 |
| 全局梳理与规划重组 | ✅ 日期文档收编 audits/,Backlog 999.1-999.5 登记 |

## Phase 41 闭合详情

### 核心成果
- **assistant 轨首次全量抽取闭合**:succeeded 5,554 / abstained 9,805 /
  units 7,818(by_type: solution 4,249 / technical_conclusion 2,759 /
  decision_rationale 810)
- **active 集合**:`knowledge_units_ir_13486f30c_20260726153705`(40,200 向量,
  含 7,818 个 as| KU;前任 salvage 集合保留可回滚)
- **serving snapshot**:`ss_470b5cb907970d1352aee145`(10/10 roles 全绑最新水位)
- **watermark**:双 key 分立(committed_assistant 首次提交,committed 原值不变)
- **质量门**:extract-gate 10/10 PASS · vector gate PASS · canary strict PASS
  (helpful 100%,wrong+stale=0) · promote(require-eval-pass) · doctor OK exit=0

### 过程中额外修掉的问题
1. **schema_invalid 根因修复**:164 条失败主因是 ① 多 unit 响应全有全无校验连坐
   (94 条)② Windows 路径非法 JSON 转义(70 条)。`_tolerant_parse` 抢救层
   + `requeue_schema_invalid.py` 重排队,零 LLM 成本回收 109 条(+123 units)。
   单测 9 项全绿。
2. **61 条 terminal API 错误全数复活**:gemini-3.5-flash 重试后全部成功(+61 units)
3. **孤儿 run 作废**:2026-07-16 遗留的全量误启动(22,450 open)与被 sibling 顶替的
   增量队列(18,102)共 40,552 条通过 `abandon_orphan_runs.py` 落 dead_refs+
   置 aborted,解除 F-13 后的 watermark 阻塞
4. **promote 快照绑定缺口**:promote 后 doctor 报 source_watermarks drift →
   `snapshots bootstrap→validate→activate` 收口(归入 Backlog 999.1)
5. **Chroma 隐藏依赖曝光**:Chroma :8001 实为 novel-mind 项目 compose 共享服务,
   Docker 重启致向量层静默离线,此前零文档记载(归入 Backlog 999.1)
6. **lite 弃答复验**:flash-lite 弃答率 70.8% vs flash 48.2%(差 23pp),
   登记为 41-CLOSURE-CHECKLIST 4c 项(~$0.5 验证实验,待做)

### 混合模型 run 血缘
run `ir_13486f30c029db49` 因 flash-lite 撞 Vertex DSQ 429 持续数小时,
经 8 条探测确认后剩余 pending 切换 `gemini-3.5-flash` 续跑(操作者决定)。
prompt/schema 未变,缓存未分裂。eval 基线报告应注明混合模型构成。

### eval 基线
- frozen 回归 R@5 **0.65**(与 active 持平,无回归),MRR 0.60
- assistant 轨首轮基线 R@5 **0.25**(只记录,下轮靶子=4c lite 弃答复验+QA 联立 v2)

## Phase 42 计划详情

### 研究结论(42-RESEARCH.md, `cd99844`)
- **推荐稳定键 `(source, AV sessions.id)`**:AV 原生 ID 已是稳定复合键
- **改键对证据链零破坏**:cm| evidence ref 铸造不含 session 键
- **迁移拆两半**:canonical builder 每次全量重建→supersede 由 builder 确定性生成;
  unified DB ref 重映射是一次性迁移(content_hash 对齐为主)
- **执行顺序警示**:normalized 快照滞后 live 12 天(920 vs 1,159 会话),
  必须先常规 sync 消化积压再上改键

### 计划(3 plans, checker 复检 PASSED, `76d314b`)
- **42-01**(wave 1,DED-01+02):消化积压+改键 builder(source_mapping 稳定键/
  取消漂移键/supersede 列/D-04 确定性排序/16→18 占位耦合同步/5 用例 fixture)
- **42-02**(wave 2,DED-01):一次性 ref 迁移(40+89 ref 重映射,old-DB 字段判源+
  dry-run/备份/单事务/幂等,硬断言阻断零执行伪验收)
- **42-03**(wave 3,DED-01+02):doctor warn-only+双轨受控消化 delta+
  byte-stable 双构建+幂等复核+runbook 注记

### checker 发现的缺陷与修复
1. 迁移脚本 ref 分类判据误用字面匹配(实际 cm ID 是不透明哈希)→改为 old-DB
   字段(source='legacy')+source_mapping 链路三条件,对账升级硬断言
2. 测试断言在纯 AV fixture 下不可实现→删除,divergent 断言收归其他用例
3. 迁移依赖的 backup 单代滚动,两个 plan 之间 sync 会冲掉→pre42 备份固化+
   启动前置断言,缺失即 exit 2

## 999.5 评测简化协议

### 种子笔记(999.5-NOTES.md)
- 三层协议:L1 机械门全自动保持不动 · L2 canary LLM 打标+人工只复核 critical
  (每次 promote ~15 分钟) · L3 gold 集"LLM 起草→人三键核对(对/错/删)"
- 降档决策:评测职责→抓回归,放弃统计显著性;Phase 17 遗留以简化协议替代性关闭;
  eval_policy_v3-draft 草案(安全门不降,质量门按 n=20 分辨率降档)
- 发现:judge_calibration_v1 从未有过人工锚点(两轮"独立评审"均同一 LLM,
  自己评分 kappa=1.0);gold 起草早已完成(45 条 human_review_candidate 等核对)

### 评审台(`/ui/review`, 提交 `5026150`)
- rag-api :8000 上新路由 GET /ui/review(HTML 页) + POST /ui/review/labels
  (labels 保存,直接落 private_evals 新文件)
- Origin 门禁(跨源 403 零写入)+ Cache-Control: no-store(私有数据)+ 安全错误
  (_safe_error 目录登记 review_console_error)
- 契约测试 6 例全绿(跨源拒绝/合法保存/非法判定 400,全合成数据)
- 人工剩余:gold 45 条 ~10 分钟 + judge 30 题 ~35 分钟(键盘操作,进度 localStorage)

## 规划文档重组

- 五份日期散落文档 → `.planning/audits/`(附 README 索引,明确"点时快照只读"规则)
- Cockpit UI 契约 → `research/v1.4-decision-cockpit-ui/UI-SPEC.md`
- Wiki 规格 → `future-milestones/v1.5-.../SPEC.md`
- Backlog 999.1-999.5 登记进 ROADMAP(管线健壮性/检索性能/治理例外/domains 删除/
  评测简化),各建 phase 目录
- 17 个文件跨引用批量修复,全路径零残留

## 本会话提交记录

```
5026150 feat(services): 999.5 单人评审台 /ui/review — gold 三键核对 + judge 校准,Origin 门禁 + no-store + 安全错误
1ffc007 feat(knowledge): schema 抢救解析层 — 逐 unit 校验 + 非法反斜杠转义修复
c82dad5 feat(migrations): 孤儿 run 作废 + schema_invalid 重排队工具
e22bb99 docs(planning): Phase 41 收尾闭合 + 日期文档收编 audits/ + Backlog 999.x
cd99844 docs(42): phase 42 规划前研究 — 稳定键推荐 (source, AV sessions.id) 与迁移影响面实测
13cd859 docs(42): pattern map — 5 待改文件类比与惯例红线
76d314b docs(42): phase 42 计划 — 3 个 plan,checker 复检 PASSED
221f04f docs: Phase 42 计划完成 — STATE 指向 42,ROADMAP 更新
```

## 下一步(并行会话视角)

1. 人工评审:重启 rag-api 后 `http://127.0.0.1:8000/ui/review`(gold 45 条 + judge 30 题)
2. Phase 42 执行:先 sync 消化 12 天积压 → 42-01 改键 → 42-02 迁移 → 42-03 验收
3. 4c lite 弃答复验(~$0.5,决定是否定向补抽 7,099 条)
4. Phase 42 闭合后:v1.4.1 里程碑审计,ROADMAP 更新