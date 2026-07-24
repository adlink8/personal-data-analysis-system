---
phase: 38
slug: guarded-decision-workspace
date: 2026-07-22
requirements: [DEC-01, DEC-02, DEC-03]
depends_on: [36-secure-projection-and-cockpit-baseline, 37-authority-aware-state-external-and-evidence]
research_status: complete
---

# Phase 38 Research: Guarded Decision Workspace

## Research Question

如何把既有的低风险 `project` 决策会话安全地呈现为浏览器工作区，使用户能理解决策、逐步确认写入、看到精确重放与恢复路径，同时不让浏览器成为新的 authority、确认器或自动执行器？

## Phase Boundary

Phase 38 是已有 Guarded Orchestration 的 UI 接线与可审计交互层，不是新的决策引擎。

```text
Decision Workspace（只读比较）
  → prepare（纯预览，不写入）
  → exact preview（用户检查）
  → explicit confirm（服务端校验）
  → append-only event / exact replay
  → receipt 或 typed recovery
```

它只开放现有 `domain=project`、`risk_budget=low` 路径；不会扩展到健康、财务、关系等高风险域，不调用浏览器端 Provider，不执行外部动作，也不改变 Personal、External、KU、Pilot 或 Calibration 的 authority 边界。

## Existing Capability Map

| 能力 | 已有实现 | 必须保持的契约 |
|---|---|---|
| 决策工作区只读投影 | `CockpitProjectionService.decision_workspace.get`、`/ui/decision/workspace` | recommendation、history、outcomes、effectiveness 分别标注 authority；单一分段失败返回 `partial`，不由页面自行聚合。 |
| 决策链状态机 | `intelligence/orchestration/service.py` 的 `TRANSITIONS` | 严格线性 `confirmed → generated → published → decided → preregistered → action_started → action_completed → observed → calibrated`；非法跳转 fail closed。 |
| 纯 prepare | `OrchestrationService.prepare` | 生成的 Preview 绑定 goal、constraints、weights、Personal/External binding、actor、sequence；不写 ledger、不调 Provider。 |
| 精确确认 | `issue_confirmation`、`_confirmation_claims` | HMAC claims 精确绑定 session、operation、preview checksum、actor、expected sequence 与短期 expiry。 |
| 并发与重放 | `confirm`、`commit_transition` 的 `BEGIN IMMEDIATE` 与 idempotency 查询 | 同请求键返回原 event 且 `replayed=true`；同键不同内容 `idempotency_conflict`；绝不生成第二条事件。 |
| Provider 至多一次 | `generation.py` reservation 与 `test_orchestration_replay.py` | 已保留 reservation 时返回 `provider_outcome_unknown`；浏览器不得自动重试。 |
| 浏览器写 client | `src/api/orchestration.ts` | 相对 `/agent/session/*` URL、原样回传 Preview、每次写入带新的 idempotency key 与 Z 时间戳。 |
| 新建/推进 UI | `NewSessionFlow.tsx`、`SessionPage.tsx`、`ConfirmDrawer.tsx` | 每一跳独立 preview/confirm；不存在“一键完成全部阶段”入口。现有代码是 WIP，须在本阶段验证后才可宣称交付。 |
| typed recovery | `agent_contract.py`、`TypedRecoveryPanel.tsx` | UI 只显示 compact envelope 的安全字段，按稳定 code/category/recovery actions 引导恢复。 |

## Authority and Transport Boundary

```text
React Workspace
  ├── GET /ui/decision/workspace      （只读 Projection）
  ├── GET /agent/session/resume       （只读、校验事件链）
  └── POST /agent/session/*           （仅既有 guarded contract）
            ↓
REST privacy + same-origin boundary
            ↓
GuardedOrchestrationInterface
            ↓
Orchestration ledger ──references──> Analysis / Pilot / Calibration
```

### Browser responsibilities

- 呈现问题、目标、硬约束、风险预算、候选方案、不行动基线、成本、机会成本、假设、反面证据、停止条件、缺失信息和限制。
- 显示当前 Personal/External snapshot、freshness、authority 与 evidence 绑定；任何 `partial`、stale、conflict、binding mismatch 或证据不足都阻止进入 prepare/confirm。
- 收集用户的显式意图，展示服务端原样 Preview，并在成功后显示 event ID、sequence、checksum 与 `replayed` 状态。

### Browser must not do

- 直连 SQLite、Chroma 或下游 authority；不得在 JavaScript 中计算 current/lifecycle/risk 或拼装事实。
- 铸造/保存 confirmation token、HMAC 或稳定身份；不得把 actor hash 当作身份认证。
- 用 localStorage、URL、console、DOM dataset 或 Query persistence 保存 preview、个人正文、token、secret 或 Provider body。
- 在网络异常、stale preview、provider outcome unknown、sequence/binding/integrity error 时自动更换 payload、自动重新 prepare 或自动重试。
- 直接写 Pilot、Analysis、Calibration，或以 UI 完整性为由添加外部动作、自动 promotion 或高风险域。

## Preconditions From Earlier Phases

Phase 38 不得绕过前置阶段的失败门禁：

1. **Phase 36 transport:** `/app` 与 API 必须为 loopback same-origin；production wildcard CORS 已移除；mutation routes 对跨 origin 请求拒绝且无写入。当前 `api_server.py` 仍统一输出 `Access-Control-Allow-Origin: *`，因此不能把当前 WIP 界面当作可发布的写入入口。
2. **Phase 36 DTO/security:** 前端只消费受校验的版本化 response，错误信封不泄露路径、PII、confirmation/HMAC、Provider request/response。
3. **Phase 37 truth gate:** Decision Workspace 的入口必须从已有 authority/snapshot/evidence 语义获得可操作状态；`partial`、stale、conflict、缺证据或 binding mismatch 只允许查看/下钻和恢复，不允许 prepare/confirm。

若任一前置验收未通过，本阶段只能保持只读界面，不能以临时按钮、浏览器检查或直连端点绕过。

## Session State and Volatile Actor Semantics

| 状态 | 唯一合法下一步 | UI 行为 |
|---|---|---|
| 无 session | `prepare → confirm` | 表单仅接受 project/low；显示 prepare 是零写入。 |
| `confirmed` | `generate` | 显示 Provider 仍可能不可用；不隐瞒 `generation_provider_unavailable`。 |
| `generated` | `publish` | 仅使用服务端返回的 Analysis references。 |
| `published` | `decide` | 明确这是写入 Pilot authority 的用户决定。 |
| `decided` | `preregister` | 不把接受建议包装成行动或结果。 |
| `preregistered` | `action_start` | 手工行动记录，不外部执行。 |
| `action_started` | `action_complete` | 保留 append-only 语义。 |
| `action_completed` | `observe` | 结果不等于因果结论。 |
| `observed` | `calibrate` | 显示非因果、无自动 promotion。 |
| `calibrated` | 无 | 仅展示完整事件链和收据。 |

`actor_identity_hash` 从浏览器运行期本地随机值经 SubtleCrypto SHA-256 派生，仅在当前 JS 运行期缓存。刷新后，旧会话可以 `resume`/`explain` 只读，但必须因 `actor_identity_mismatch` 不能继续写入。Phase 38 应明确呈现该状态，而不能伪造续写能力、持久化 actor 或降低服务端 actor binding。

## Exact Preview and Confirmation Rules

1. `prepare` 或 `session.preview` 的返回值是不可编辑、原样回传的 Preview；UI 不得补字段、重排序后重算、替换 `payload` 或重用过期 Preview。
2. Confirm Drawer 最少展示：操作名称、服务端 exact preview、将新增事件、明确不会执行的动作、checksum、expected sequence、idempotency key、风险提示和操作专属确认文案。
3. 单次写入尝试的 retry 必须复用同一 Preview 和同一 idempotency key；任何新的 payload、sequence、binding 或 preview 都必须先 resume/重新 preview，再生成新 key。
4. 成功回执必须显示 `event_id`、`event_checksum`、`sequence` 和 `replayed`；`replayed=true` 的文案必须是“已返回原事件，未重复写入”，不可显示为一次新写入。
5. Close/Esc 只关闭抽屉，不写入；抽屉需保持焦点管理，确认 busy 时避免重复点击。

## Typed Recovery Matrix

| 类别/代表 code | 可否自动重试 | 用户可见恢复 | 禁止行为 |
|---|---|---|---|
| `stale` / `stale_expected_sequence` | 否自动；用户可重新发起 | resume 获取最新 sequence → 新 preview → 新确认 | 用旧 Preview 静默再发。 |
| `confirmation` / expired、consumed、binding mismatch | 否自动 | resume/检查 → fresh preview → 再确认 | 重用已失效/被消费 token。 |
| `sequence` / `illegal_transition` | 否自动 | resume 解释当前 state → 只允许下一跳 | 跳过 transition 或修改 state。 |
| `conflict` / `idempotency_conflict` | 否 | 核对原 event 与原 idempotency key；需要时人工复核 | 使用同 key 发送不同 payload。 |
| `integrity` / checksum、binding、chain drift | 否 | 停止写入，检查 authority/人工复核 | 以客户端缓存继续会话。 |
| `risk` / domain、budget、external action forbidden | 否 | 缩小到 project + low，或离开受控流程 | 改前端字段、跳过服务端 allowlist。 |
| `runtime` / secret、schema、generation runner unavailable | 否自动 | 检查本地运行服务后由用户重新尝试；会话可读 | 将错误解释为已写入或改用浏览器 Provider。 |
| `unknown_outcome` / `provider_outcome_unknown` | 绝对否 | resume + inspect provider reservation + manual review | 再调 Provider 或替换 idempotency key。 |

`TypedRecoveryPanel` 应以 `error.code`、`category`、`retryable`、`recovery_actions` 为唯一输入。前端不能显示原始 exception、HTTP body、调用参数或确认材料。

## Recommended Implementation Order

1. **Verify dependencies:** 执行 Phase 36/37 的 secure transport、authority/snapshot/evidence 相关验证；把“可写”入口绑定到这些已验证状态。
2. **Settle read-to-write handoff:** 让 Decision Workspace 只从 `/ui/decision/workspace` 的稳定 recommendation/snapshot/evidence 元数据启动会话；缺少可验证 `case_id` 时明确要求用户输入，绝不臆造。
3. **Audit the initial session flow:** 使用 `NewSessionFlow` 的 fixed project/low form、volatile actor、pure prepare 和 ConfirmDrawer；校验预览/确认/receipt 与服务端 compact envelope 一致。
4. **Audit linear resume/advance:** 用 `SessionPage` 的 `resume → legal next transition → preview → confirm/execute` 方式渲染；所有表单只产生 service-defined `payload.input`。
5. **Wire typed recovery:** 为 stale、confirmation、sequence、conflict、integrity、risk、runtime、unknown-outcome 加入可访问、非泄露、非自动的恢复路线；每条路线回到服务端 read/preview。
6. **Prove browser safety:** 完成同源 mutation、跨 origin 无写入、preview 篡改/过期、重复确认 exact replay、刷新 actor 只读、provider unknown 不重试的测试；记录真实浏览器写流的边界证据，完整 UAT 留给 Phase 40。

## Validation Architecture

### Reuse and retain

- `tests/contract/test_orchestration_interfaces.py`：REST/stdio MCP 共用服务契约、严格 mutation input。
- `tests/integration/test_orchestration_replay.py`：Provider 一次调用、完成重放、reserved unknown outcome 和 abstain 不转换状态。
- `tests/e2e/test_orchestration_acceptance.py`：真实 transport shim 下的 exact replay；拒绝/过期路径前后 authority fingerprint 不变。
- `apps/personal_decision_cockpit/src/test/orchestration.test.ts`：Preview 原样回传、route alias、Z timestamp、error normalization、idempotency/actor 形态。
- `apps/personal_decision_cockpit/src/test/TypedRecoveryPanel.test.tsx`：stale、conflict、runtime、replay 的可读恢复语义。

### Phase 38 additions required

| 层级 | 必须证明 |
|---|---|
| UI component | workspace 中所有 DEC-01 字段可见；Candidate、事实、限制与证据不混淆；抽屉 Esc/焦点/忙碌状态不导致写入。 |
| UI integration | 只能进入服务端定义的下一 transition；Preview 被篡改、过期或 sequence/binding 漂移时不会调用 execute；refresh 后 actor mismatch 只读。 |
| Transport security | same-origin POST 可走 guarded path；跨 origin POST/OPTIONS 被拒绝且 orchestration/Pilot/Analysis/Calibration fingerprint 不变。 |
| Replay | 相同 confirm/execute payload 返回同 event、`replayed=true`，UI 不新增 receipt；同 key 不同 payload 显示 conflict，不自动换 key。 |
| Provider uncertainty | reserved unknown outcome 不产生第二次 Provider 调用，界面只允许 resume/inspection/manual review。 |
| Privacy | DOM、console、API error snapshot 不含 confirmation token、HMAC、secret、raw evidence 或 Provider body。 |

所有 mutating test 应使用 disposable fixture/临时数据库；不得为了 UI 测试写入用户真实 authority 或调用付费 Provider。

## Prohibited Shortcuts

- 从 `DecisionWorkspacePage` 直接 POST Pilot/Analysis/Calibration，或在 UI 里复制 authority lifecycle 规则。
- “确认一次自动跑完整会话”、自动 Provider 重试、自动刷新 Preview 后重新确认、浏览器选择/替换下一跳。
- 在刷新后持久化 actor hash，或将 hash、session URL 参数、页面状态视为身份/授权机制。
- 把 `replayed=true`、`partial`、空数据、MCP/Provider 故障包装成成功、当前结论或新增事件。
- 为补齐 UI 而新增高风险域、自动 action、自动 promotion、Wiki 页面、客户端个人数据缓存或新的事实 SSOT。

## Planning Recommendation

建议用三个顺序计划保持回滚边界清晰：

1. **Workspace truth and entry gate**：DEC-01 比较视图、snapshot/evidence/partial gate、从现有 Projection 到受控新会话的 handoff。
2. **Exact confirmation and linear session advance**：复用 prepare/preview/confirm/replay、收据、volatile actor、严格下一跳与 Confirm Drawer。
3. **Recovery and browser-write regression**：typed recovery、跨 origin 无写入、preview 篡改/过期/重复确认/provider unknown 回归，以及定向 browser flow 验证。

三者均须以 Phase 36/37 通过为前置；若前置门禁失败，Phase 38 应停留在只读比较而不是扩大写入面。

## Sources

- `38-CONTEXT.md`、`.planning/REQUIREMENTS.md`、`.planning/ROADMAP.md`。
- `PDA-33-guarded-decision-orchestration/{33-CONTEXT.md,33-VERIFICATION.md,33-RESEARCH.md}`。
- `PDA-37-authority-aware-state-external-and-evidence/37-CONTEXT.md`。
- `.planning/research/v1.4-decision-cockpit-ui/{SUMMARY.md,STACK.md,FEATURES.md,ARCHITECTURE.md,PITFALLS.md}`。
- `apps/personal_decision_cockpit/{docs/write-flow.md,src/api/orchestration.ts,src/components/decision/{ConfirmDrawer.tsx,NewSessionFlow.tsx},src/components/feedback/TypedRecoveryPanel.tsx,src/pages/sessions/SessionPage.tsx}`。
- `src/personal_knowledge/{services/{api_server.py,orchestration_service.py,agent_contract.py},intelligence/orchestration/{service.py,models.py}}`。
- `tests/{contract/test_orchestration_interfaces.py,contract/test_ui_projection_decision.py,integration/test_orchestration_replay.py,e2e/test_orchestration_acceptance.py}`。

