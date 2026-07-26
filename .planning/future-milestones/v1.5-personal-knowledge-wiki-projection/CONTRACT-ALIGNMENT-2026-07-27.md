---
document_type: contract-alignment-pre-report
status: pre_report_not_a_go_decision
recorded: 2026-07-27
recorded_by: gsd-planning-auditor (read-only pre-check)
target_gate: Phase 41 preflight (41-00-PLAN.md), executed only after v1.5 activation
depends_on_remaining:
  - "v1.4 Phase 38 (decision workspace guarded write UI) — not executed"
  - "v1.4 Phase 39 (feedback/proactive/runtime pages) — not executed"
  - "v1.4 Phase 40 (hardening + real-browser UAT, responsive/a11y/privacy re-audit) — not executed"
  - "v1.4 milestone completion/audit pass — root STATE.md still shows milestone v1.4 status: executing, completed_phases: 1 (i.e. only Phase 36's closure has been folded in; Phase 37's 2026-07-27 verified pass has not yet been reflected there)"
  - "explicit fresh v1.5 user authorization per ACTIVATION.md"
sources_examined:
  - src/personal_knowledge/services/ui_projection.py
  - src/personal_knowledge/services/api_server.py
  - src/personal_knowledge/intelligence/decision/service.py
  - src/personal_knowledge/intelligence/schema.py
  - src/personal_knowledge/intelligence/proactive/schema.py
  - .planning/phases/PDA-36-secure-projection-and-cockpit-baseline/36-VERIFICATION.md
  - .planning/phases/PDA-37-authority-aware-state-external-and-evidence/37-VERIFICATION.md
  - tests/contract/test_ui_projection_evidence.py
  - tests/contract/test_ui_projection_state_external.py
  - apps/personal_decision_cockpit/src/api/schemas.ts
  - .planning/future-milestones/v1.5-personal-knowledge-wiki-projection/{SPEC.md,REQUIREMENTS.md,ROADMAP.md,ACTIVATION.md,README.md}
  - .planning/future-milestones/v1.5-personal-knowledge-wiki-projection/phases/PDA-41-topic-authority-and-deterministic-read-projection/{41-00-PLAN.md,41-CONTEXT.md,41-RESEARCH.md}
  - .planning/STATE.md
---

# v1.5 契约对齐预审报告 —— 对照 Phase 36/37 已执行真实契约

## 0. 这份文件不是什么

这不是 WIKI-01 preflight 本身,也不是 v1.5 的 GO/NO-GO 决定。v1.4 尚未完成(Phase 38-40 未执行,里程碑整体也未审计关闭),`41-00-PLAN.md` 规定的"真实 preflight"必须在那之后重新执行一次并产出
`41-PREFLIGHT-RECORD.md`。本报告只是提前核对当前**已验收**的 Phase 36(`36-VERIFICATION.md`,`status: verified`)与 Phase 37(`37-VERIFICATION.md`,`status: passed`)真实契约,与 v1.5 preplan(尤其是
`41-00-PLAN.md`/`41-CONTEXT.md`/`41-RESEARCH.md`)当前假设之间的落差,减少未来 41-00 执行时的返工面。任何"pass"结论仅限本报告核对到的范围,不构成对 Phase 38-40 或 v1.4 整体的验收断言。

## 1. 逐项判定表

| # | Preflight 检查项(源自 41-00-PLAN.md `<action>`) | 判定 | 一句话理由 |
|---|---|---|---|
| 1 | `/ui/*` 信封整体字段结构(operation/ok/partial/freshness/limitations/authorities/snapshot_bindings) | **pass(结构级)/ changed(freshness 内部字段)** | 顶层 8 个键完全一致;但 `freshness` 内部字段与 preplan 假设的 `{status, reason_codes}` 完全不同,见 D1 |
| 2 | 安全错误 / `_SAFE_ERRORS`、`_SAFE_FAILURE_CODES` 降级语义 | **pass(模式级)/ changed(具体形状)** | allowlist+不泄露异常细节的模式已被反复验证;但真实存在"精简错误信封"与"完整信封+partial"两种不同形状,preplan 未区分,见 D2 |
| 3 | Evidence Resolver 是否满足 Wiki 证据下钻依赖 | **pass,且已超出 preplan 认知(重大新能力)** | `evidence_resolve.get` 六态词表、GET-only、稳定引用三元组已在 Phase 37(EVID-01)落地并契约测试覆盖,但 `41-RESEARCH.md` 全文未提及这个具体端点,见 D3 |
| 4 | P0 canonical 字段:project scope / goal domain-scope-predicate(+checksum)/ decision recommendation_id 链 | **pass(project/goal 侧)/ changed-risk(decision 侧缺 predicate)/ cannot-verify-yet(真实样本歧义)** | personal_state 侧字段齐全且经契约测试锁定;但 Decision 权威没有 `predicate` 字段,goal↔decision backlink 存在潜在歧义,需真实样本核验,见 D4;历史时间线还缺时间戳,见 D5 |
| 5 | Origin/CORS 是否满足"同源读"假设 | **pass,但机制描述需精确化** | 生产同源 + 显式 dev allowlist 成立;但 GET 路由本身服务端不做 Origin 拒绝(只影响是否下发 CORS 头),与 preplan 笼统表述有精度落差,见 D6 |

## 2. 逐条discrepancy(含双侧 file:line)

### D1 — `freshness` 结构不是 Cockpit 现有字段的"复用",而是 Wiki 需要自行发明的新设计

- Preplan 侧:
  - `SPEC.md:105` — `"freshness": {"status": "fresh|stale|partial|unavailable", "reason_codes": []}`
  - `41-RESEARCH.md:121` — `"freshness": {"status": "fresh|partial|unavailable", "reason_codes": []}`(注意这里连 preplan 内部两处对 `stale` 是否在该枚举里都不一致)
  - `41-RESEARCH.md:37` — 声称可"Reuse envelope conventions: operation, generated time, snapshot bindings, freshness, authorities, partial, limitations, data"
- 真实侧:
  - `src/personal_knowledge/services/ui_projection.py:442-463`(`_envelope` 方法签名与实现)—— `freshness` 参数是调用方传入的普通 dict,九个真实操作里没有任何一个填过 `status` 或 `reason_codes` 键
  - 例如 `ui_projection.py:506-510`(`overview.get`)、`ui_projection.py:645-649`(`system.status.get`)、`ui_projection.py:1420-1422`(`evidence_resolve.get`)—— 真实 `freshness` 恒为 `{"personal_as_of": ..., "knowledge_unit_count": ..., "generated_at": ...}` 三键形状
  - 前端 zod 契约 `apps/personal_decision_cockpit/src/api/schemas.ts:17-23` —— `FreshnessSchema` 只锚定 `personal_as_of`/`knowledge_unit_count`,同样没有 `status`/`reason_codes`
- 影响:41-00 不能写"沿用 Cockpit freshness 语义"就算过关;Wiki 的 `fresh|stale|partial|unavailable` 状态机是一个**全新契约**,必须独立设计、独立测试,且要先在 preplan 内部把 `stale` 是否属于该枚举这一自相矛盾之处澄清。

### D2 — 真实存在两种不同形状的失败响应,preplan 只假设了一种

- Preplan 侧:`41-RESEARCH.md:181-201`("Typed recovery, not exception disclosure")通篇假设失败都走同一个完整信封 + `limitations`/`authorities` 表达降级。
- 真实侧:
  - `ui_projection.py:427-434`(`CockpitProjectionService._error`)—— 结构性错误(如 `invalid_input`、`unknown_operation`)返回的是精简信封 `{schema_version, operation, ok: False, error: {code, detail}}`,**没有** `snapshot_bindings`/`freshness`/`authorities`/`partial`/`limitations`/`data` 字段
  - 对比 `ui_projection.py:1371-1391`(`evidence_resolve.get` 对非法 `subject_type`/缺字段的处理直接调用 `_error(...)`)与 `ui_projection.py:1401-1426`(权威内部故障走完整信封 + `partial=True`)—— 两条路径共存于同一个操作里
  - `api_server.py:842-849`(`do_GET` 异常兜底)—— `ValueError` 走 `_err()`(另一种更简的 `{"ok": False, "error": "..."}` 字符串错误,不是上面任何一种)
- 影响:Wiki 的 `topic.get` 对"非法 key"应该选用哪一种失败形状(精简 `error` 信封,还是完整信封 + `authorities.topic="error"`)目前没有对齐;41-00 必须显式做出选择并写进 preflight 记录,而不是隐式继承 41-RESEARCH 的单一假设。

### D3 — Evidence Resolver 已经是具体落地能力,preplan 的研究文档尚未见过它(重大新能力提示)

- Preplan 侧:`41-RESEARCH.md:151-163`("Evidence references stay references")与 `41-RESEARCH.md:235` 只提到复用 `intelligence/analysis/evidence.py` 与 `retrieval/evidence.py` 两个模块,设想 Phase 41 自己"定义 reference schema 和 allowlist";`SPEC.md` 创建于 2026-07-22。
- 真实侧(Phase 37 EVID-01,验收于 2026-07-27,即今天):
  - `ui_projection.py:143-151` —— `_EVIDENCE_SUBJECT_TYPES = {personal_state, external_fact, decision}`、`_STATE_KEY_FIELDS`、`_EVIDENCE_RESULT_STATUSES = {ok, mismatch, expired, abstain, not_found, authority_unavailable}` 六态词表已定型
  - `ui_projection.py:1366-1543`(`_evidence_resolve_get` 及三个 `_resolve_*_evidence`)—— 完整实现:stable_id/snapshot_id/checksum 三元组 + personal_state 额外的 5 要素 state key,mismatch-never-fallback-to-latest 语义
  - `api_server.py:613, 619-632` —— REST 路由 `/ui/evidence/resolve`,GET-only(POST 落 404,见 `tests/contract/test_ui_projection_evidence.py:428-460` 的 `test_ui_route_serves_evidence_resolve_and_rejects_post`)
  - `tests/contract/test_ui_projection_evidence.py`(全文 547 行)—— 三种 subject_type 的成功/mismatch/expired/abstain/not_found/authority_unavailable 全路径契约测试,以及物理只读边界测试
- 影响(这是本报告最重要的一条正向发现):Phase 41 **不需要、也不应该**重新定义证据引用 schema——应直接复用 `evidence_resolve.get` 的四元组 `(subject_type, stable_id, snapshot_id, checksum)` 与六态词表作为 Topic Page 证据下钻的绑定层。但 41-RESEARCH 自拟的引用结构 `{authority_id, record_type, record_id, snapshot_id, checksum?, evidence_type?}`(`41-RESEARCH.md:156`)与真实结构字段名完全不同,41-00 必须明确"弃用自拟 schema、改绑真实 `evidence_resolve.get`"这一结论,否则 Phase 42 的 Evidence Drawer 会对着一个不存在的字段集设计 UI。

### D4 — Decision 权威没有 `predicate` 字段,Goal↔Decision backlink 存在潜在身份歧义

- Preplan 侧:`SPEC.md:124` 与 `41-CONTEXT.md`(W-41-01)把 Goal 稳定键定义为 `goal:{domain}:{scope}:{predicate}`,`41-RESEARCH.md:141,146-149` 要求 backlink 只能用"exact decision links"/`recommendation_targets_topic` 这类精确字段匹配,不能用模糊/语义匹配。
- 真实侧:
  - `src/personal_knowledge/intelligence/decision/service.py:190-226`(`_metadata`)—— `decision_recommendations` 暴露的身份字段只有 `subject`/`domain`/`scope`(`service.py:205-207`),**没有 `predicate`**
  - `ui_projection.py:100-103`(`_QUEUE_CARD_KEYS`)、`apps/personal_decision_cockpit/src/api/schemas.ts:455-477`(`RecommendationDetailSchema`)—— 均不含 `predicate`
- 影响:一个以 `domain+scope+predicate` 三元组标识的 Goal 主题,若要反向链接到 Decision,现有 Decision 权威只能提供 `domain+scope` 两个维度做匹配。若同一 `domain+scope` 下存在多个不同 `predicate` 的目标(例如同一 project scope 下"完成学习"与"控制预算"两个不同 predicate 的 goal),现有字段**无法**无歧义区分某条 recommendation 到底对应哪一个 goal。41-00 必须用真实数据样本核验这种同 `domain+scope` 多 `predicate` 共存的情况是否存在;若存在且无法解决,应该按 `41-CONTEXT.md` 自身写的原则("若 WIKI-01 发现当前 Authority 缺少稳定的 scope、snapshot 或 evidence 路径,应先以失败为结果收口该契约")把 Goal↔Decision backlink 降级为不产出,而不是放宽成 domain+scope 模糊匹配。

### D5 — Decision 历史/时间线不暴露时间戳,与 Topic Page"历史演变"区块的期望有落差

- Preplan 侧:`SPEC.md` §4.2 把"历史演变与生命周期"列为 Topic Page 固定结构的必备区块。
- 真实侧:
  - `ui_projection.py:105-108`(`_HISTORY_EVENT_KEYS`)—— `recommendations.history` 只返回 `{event_id, sequence, event_type, typed_record_id, previous_event_checksum, payload_checksum}`,不含时间戳/status;`ui_projection.py:1028-1030`、`ui_projection.py:1111-1113` 两处都专门写了这条限制说明
  - `service.py:190-226`(`_metadata`)—— `recommendations.get` 同样不返回 `created_at`(只有 `expires_at`),即便底层 `decision_recommendations` 表按 `created_at` 排序(`service.py:253` `ORDER BY created_at,recommendation_id`),这个字段没有被读契约向外暴露
- 影响:Decision Topic 的历史区块只能按 `sequence` 排序展示"发生了什么类型的事件",不能展示"什么时候发生的"。41-00 需要明确这是可接受的降级展示(与既有 Cockpit 限制说明保持一致),还是需要为 Wiki 单独申请扩展 Decision 权威读接口暴露时间戳——如果是后者,这超出了"只读投影、不新增权威"的 Wiki 边界(`SPEC.md` §2.2),需要谨慎处理。

### D6 — Origin/CORS:GET 路由不做服务端 Origin 拒绝,安全性依赖浏览器同源策略而非服务端 403

- Preplan 侧:`41-RESEARCH.md:266-270` 断言 "Read routes remain within the accepted v1.4 CORS/origin policy and do not reopen cross-origin mutation exposure"。
- 真实侧:
  - `api_server.py:184-199`(`_origin_policy`)—— 判定逻辑本身只是"要不要下发 CORS 头"的依据
  - `api_server.py:376-393`(`_send`)—— **所有**响应(含全部 `do_GET` 路由)都经过这里决定是否附加 `Access-Control-Allow-Origin`,但 `do_GET`(`api_server.py:417-849`)本身**没有任何一处**对 Origin 做 allow/reject 判断并拒绝请求
  - 显式的 Origin 拒绝只发生在 `do_OPTIONS`(`api_server.py:407-414`)和 `SESSION_WRITE_ROUTES`/`/ui/review/labels` 的 `do_POST` 前置校验(`api_server.py:857-874`)
- 影响:preplan 的结论"不重新打开 cross-origin mutation 暴露"本身成立(因为 Wiki 路由只读、没有 mutation),但如果 41-00 把这条理解成"跨源 GET 也会被服务端拒绝"就是误读真实实现——真实情况是跨源 GET 请求服务端仍会 200 应答且不带 CORS 头,靠浏览器同源策略阻止 JS 读取响应体,而不是服务端主动 403。41-00 的 preflight 记录需要把这个精确机制写清楚,避免"同源读"被误当成"服务端强制校验"。

## 3. 已确认成立、可以直接复用的部分(不算 discrepancy,供 41-00 引用)

- 信封顶层 8 键(`schema_version/operation/ok/generated_at/snapshot_bindings/freshness/authorities/partial/limitations/data`)结构与命名与 preplan 假设一致(`ui_projection.py:452-463` vs `41-RESEARCH.md:113-128`),Wiki 可以在顶层照搬这套骨架,只是内部字段(见 D1/D2)要重新设计。
- `authorities` 字段的真实取值域被契约测试锁定为 `{"ok","empty","error"}` 三态(如 `tests/contract/test_ui_projection_state_external.py:73` `assert set(result["authorities"].values()) <= {"ok","empty","error"}`),Wiki 若复用这个词表能省掉一次自行设计的往返。
- 安全错误 allowlist 模式(固定 code/message、绝不拼接 `str(exc)`/路径/Bearer/HMAC/provider body)已经被 Phase 36/37 的 poisoned-fragment 契约测试反复验证为可靠模式(`36-VERIFICATION.md` §2 CCK-03,`37-VERIFICATION.md` 第 28 行),Wiki 应该复用这个**模式**,但要新建自己的 code 表(见 D2,不能直接照抄 `_SAFE_FAILURE_CODES`/`_SAFE_ERRORS` 里那几个不相关的 4/5 个 code)。
- Project/Goal 侧的 personal_state canonical 字段(`assertion_kind/subject/domain/scope/predicate` 五要素键 + `current_value_checksum` 与 `current_assertion_id` 成对出现)已被契约测试锁定(`tests/contract/test_ui_projection_state_external.py:92-100`),8 个 canonical domain(含 `project`)已定型(`intelligence/proactive/schema.py:9`),`goal` 是合法 `assertion_kind`(`intelligence/schema.py:15`)。这部分 P0 身份基础是稳的。
- Evidence 六态词表 + 稳定引用三元组(见 D3)是可以直接拿来用的既成能力,是本报告发现的最大利好。

## 4. 41-00 preflight 在 Phase 38-40 之后仍必须重新核对的事项

以下事项**不是**本报告能确认的,因为它们依赖尚未执行的 Phase 或尚未关闭的里程碑,必须留给未来真正执行的 `41-00-PLAN.md` 重新核对,不能用本报告替代:

1. **v1.4 里程碑整体状态**:`.planning/STATE.md` 当前仍显示 `milestone: v1.4`、`status: executing`、`completed_phases: 1`(仅 Phase 36 已折叠进度),而 Phase 37 已于 2026-07-27 独立验证通过(`37-VERIFICATION.md`)但尚未反映到 STATE.md;这本身说明 v1.4 完成度的"官方记录"滞后于实际验收,41-00 执行时需要先把 STATE.md/ROADMAP.md 的进度补齐,再判断"v1.4 完成"这一激活前提是否真正成立。
2. **Phase 38(Decision Workspace 受控写 UI)**:目前 Decision Topic 页面若要提供"跳转到确认/行动/结果记录入口"的链接,其目标路由/组件形状要等 Phase 38 定稿才能确认稳定性,当前不能假设。
3. **Phase 39(反馈/主动情报/运行时页面)**:若未来 backlink 想引用 proactive candidate 或运行时状态,其数据形状/组件尚未验收,现在做的任何绑定假设都是临时的。
4. **Phase 40(硬化 + 真实浏览器 UAT)**:Wiki P0 验收标准里的"隐私封存/320px 响应式/键盘导航/长中文长 ID"目前只有 Phase 36 的传输层安全测试和 Phase 37 的字段级契约测试作为间接佐证,还没有真实浏览器 UAT 证据可以直接复用或对照;41-00 需要等 Phase 40 产出真实 UAT 方法论后再决定 Wiki 自己的 UAT 怎么做,不能假设"Phase 36/37 的自动化测试通过"等价于"真实可用性已验证"。
5. **D4 的真实数据样本核验**(同 domain+scope 多 predicate 是否共存)需要在有真实/可控 fixture 的执行环境下跑一次针对性查询才能定论,本次只读预审没有执行数据库采样,只是从字段定义层面确认了结构性缺口的存在。
6. **D1/D2 的最终设计选择**(freshness 状态机具体字段、错误信封选哪一种形状)本报告只指出了落差,没有替 41-00 做设计决定——这些决定应该在真正执行 preflight、并已知 Phase 38-40 最终契约后再定稿,避免提前锁定后又被 Phase 38-40 的变化打破。

## 5. 结论

本报告确认:v1.5 preplan 关于"信封顶层结构""安全错误模式""P0 project/goal 字段基础""同源读大方向"的核心假设**基本站得住**,且发现了一项 preplan 完全不知道的重大新能力(Phase 37 EVID-01 的 `evidence_resolve.get`,应直接复用而非重新设计)。同时发现六项需要在真正执行 41-00 preflight 时逐一收口的具体落差(D1-D6),其中 D4(Goal↔Decision 潜在身份歧义)风险最高,可能触发 `41-CONTEXT.md` 自身规定的"缩窄或收口该 P0 类型"条款。

**这不是 GO 决定。** v1.4 Phase 38-40 尚未执行,里程碑尚未审计关闭,`41-00-PLAN.md` 规定的真实 preflight(产出 `41-PREFLIGHT-RECORD.md`)必须在那之后重新执行一次,并把本报告列出的 D1-D6 作为其检查清单的输入之一,而不是跳过重新核对的理由。
