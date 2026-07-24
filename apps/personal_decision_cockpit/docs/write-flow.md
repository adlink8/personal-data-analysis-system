# 写入流程契约（Guarded Orchestration）

> 本文档整理 Personal Decision Cockpit 前端的写操作契约（Phase 38）。
> 后端实现：`src/personal_knowledge/services/orchestration_service.py`
> （接口版本 `guarded_orchestration_interface_v1`，经 `agent_contract.compact_envelope`
> 投影为 16KB 预算的 compact 信封 `agent_compact_envelope_v1`）。
> 前端实现：`src/api/orchestration.ts` + `components/decision/ConfirmDrawer.tsx`
> + `components/feedback/TypedRecoveryPanel.tsx` + `pages/sessions/SessionPage.tsx`。

## 1. 总原则（spec §5.3 硬性）

```text
Prepare → 展示 exact preview → 用户逐项检查 → Confirm → Execute
→ 返回 sequence / event_id / checksum → 网络重试返回 exact replay
```

- 每一次写入都必须先 preview、再显式确认；**前端不提供"一键完成全部阶段"入口**。
- 幂等键 `ui-<op>-<crypto.randomUUID()>` 由前端生成；同一次写入尝试的重试**复用同一键**。
- 所有时间戳必须 `Z` 结尾（`new Date().toISOString()`）；execute 类请求 `now` 必填
  （缺失返回 `timestamp_required`）。
- 响应均为 compact 信封：`ok/status/summary/data/error{code,category,message,retryable,recovery_actions}`；
  HTTP 200 表示 `ok:true`，HTTP 400 表示 `ok:false`。

## 2. transition 链（严格线性）

每跳都要重新 preview + 独立确认；路由别名必须等于 `preview.operation`（否则 `route_operation_mismatch`）。

| # | transition | state 前 → 后 | 执行路由（POST） |
|---|------------|---------------|------------------|
| 1 | confirm | none → confirmed | `/agent/session/confirm` |
| 2 | generate | confirmed → generated | `/agent/session/generate` |
| 3 | publish | generated → published | `/agent/session/publish` |
| 4 | decide | published → decided | `/agent/session/decide` |
| 5 | preregister | decided → preregistered | `/agent/session/preregister` |
| 6 | action_start | preregistered → action_started | `/agent/session/action-start` |
| 7 | action_complete | action_started → action_completed | `/agent/session/action-complete` |
| 8 | observe | action_completed → observed | `/agent/session/observe` |
| 9 | calibrate | observed → calibrated | `/agent/session/calibrate` |

## 3. 各步请求体

### 3.1 prepare

`POST /agent/session/prepare`

```json
{
  "goal": "未来 8 周如何分配英语、项目和求职时间",
  "constraints": ["每周总投入不超过 30 小时"],
  "weights": {"career": 0.6, "learning": 0.4},
  "actor_identity_hash": "<64 位小写 hex>",
  "domain": "project",
  "risk_budget": "low",
  "now": "2026-07-19T10:00:00.000Z"
}
```

- `actor_identity_hash` 必须恰好 64 位小写 hex；前端用 SubtleCrypto SHA-256
  对本地随机串派生（不含真实用户标识、不持久化，页面刷新后更换——此后旧会话只能只读 resume）。
- `constraints` ≥ 1 条非空；`weights` ≥ 1 个且值在 0..1；`domain`/`risk_budget` 固定
  `project`/`low`（其他值返回 `domain_not_allowed`/`risk_budget_not_allowed`）。
- 响应 `data` = Preview P0：`{session_id, operation:"confirm", expected_sequence:0,
  payload（manifest，含 binding）, issued_at, preview_checksum}`。

### 3.2 confirm（第一跳）

`POST /agent/session/confirm`

```json
{"preview": "<P0 原样回传>", "confirmed": true, "idempotency_key": "ui-confirm-<uuid>", "now": "...Z"}
```

- preview 必须**原样回传**（checksum 绑定，改动即 `preview_checksum_mismatch`）。
- 响应 `data` = OperationResult：`{session_id, operation:"confirm", state:"confirmed",
  sequence:1, event_id, event_checksum, replayed, references}`。

### 3.3 之后每一跳：preview → execute

`POST /agent/session/preview`

```json
{
  "session_id": "ors_…",
  "transition": "decide",
  "payload": {"case_id": "…", "...": "…"},
  "actor_identity_hash": "<64 位小写 hex>",
  "expected_sequence": 3,
  "now": "...Z"
}
```

- `expected_sequence` = 上一步 OperationResult.sequence（或 resume 的 sequence）；
  不一致返回 `stale_expected_sequence`（stale 类，可重试：先 resume 再重新 preview）。
- 响应 Preview：`payload` 为 `{input: <你提交的 payload>, binding_hash}`。

`POST /agent/session/<别名>`（别名见第 2 节表）

```json
{"preview": "<上一步 Preview 原样>", "confirmed": true, "idempotency_key": "ui-<op>-<uuid>", "now": "...Z"}
```

### 3.4 各 transition 的 payload.input

| transition | input 字段 |
|------------|-----------|
| generate | `{personal_evidence: [], external_evidence: []}`（固定空集；真实证据由服务端 generation runner 组装） |
| publish | `{run_id, candidate_id, selected_option_id, case_confirmation_event_id}` |
| decide | `{case_id, decision:"accept"\|"reject"\|"defer", confirmed_case_checksum, reason_code, pilot_expected_sequence}` — **决策确认写入 Pilot 权威案例** |
| preregister | `{case_id, metric, unit, baseline, target, direction, window_start, window_end, collection_source, estimated_time_minutes, estimated_cost, pilot_expected_sequence}` |
| action_start | `{case_id, action_state:"started", description, operator, pilot_expected_sequence}` |
| action_complete | `{case_id, action_state:"completed", description, operator, pilot_expected_sequence}` |
| observe | `{case_id, observed_value, actual_time_minutes, actual_cost, completion, quality, satisfaction, side_effects[], regret, confounders[], source, observed_at, pilot_expected_sequence}` |
| calibrate | `{protocol_id}`（可选 `proposal`；非因果、不自动 promote） |

`pilot_expected_sequence` 是 Pilot 案例事件链的乐观锁（来自 `/agent/pilot/item` 查询）。
case_id 无法从工作区投影可靠推导时，前端让用户手动输入并注明原因，**不臆造 case_id**。

### 3.5 resume（只读）

`GET /agent/session/resume?session_id=<id>`

响应 `data`：`{session_id, state, sequence, last_event_checksum, manifest, binding}`。
用于恢复会话、决定下一合法 transition（state → transition 映射见 `orchestration.ts`
的 `NEXT_TRANSITION_BY_STATE`）。读操作不写库（spec §13.1）。

## 4. 错误码分类（compact 信封 error 节）

`error.category` 决定 `retryable` 与默认 `recovery_actions`（后端 `ERROR_CATALOG`）：

| category | retryable | recovery_actions | 说明 |
|----------|-----------|------------------|------|
| not_found | 否 | verify_id, list_available | 记录不存在（如 `session_missing`） |
| conflict | 否 | resume_session, use_original_idempotency_key, manual_review | `idempotency_conflict` 等，不可自动重试 |
| stale | 是 | resume_session, prepare_fresh_preview | `stale_expected_sequence` |
| confirmation | 是 | resume_session, prepare_fresh_preview, confirm_again | 确认缺失/过期/已消费/不匹配 |
| sequence | 是 | resume_session, prepare_fresh_preview | `illegal_transition` / state 漂移 |
| risk | 否 | reduce_scope, manual_review | 越出低风险 project 边界 |
| integrity | 否 | inspect_authority, manual_review | checksum / 链校验失败 |
| runtime | 是 | check_runtime, retry_when_ready | 本地运行态缺失 |
| unknown_outcome | 否 | resume_session, inspect_provider_reservation, manual_review | provider 结果未知，自动重试不安全 |

前端 `TypedRecoveryPanel` 按 `error.code` 给出特定恢复说明：

- `confirmation_secret_unavailable`：服务端未设置 `PERSONAL_DATA_ORCHESTRATION_SECRET`
  （≥32 字节随机值），设置后重启 rag-api，再重新 prepare。
- `generation_provider_unavailable`：stock 服务未注入 generation runner；会话停在
  confirmed 不中断，配置 runner 后可继续。
- `idempotency_conflict`：不可重试；恢复会话核对状态，更换幂等键重新 preview。
- `route_operation_mismatch`：preview.operation 与执行路由不一致；重新 preview。
- `actor_identity_mismatch`：页面刷新后 actor 更换；旧会话只读，需新建会话推进。

## 5. Replay 语义（spec §12）

同一幂等键 + 相同请求内容重复到达时，服务端不追加新事件，返回原 OperationResult
且 `replayed:true`。前端必须显示 Replay 态：**"已返回原事件，未重复写入"**，
不重算 sequence、不当作新写入。幂等键相同但内容不同 → `idempotency_conflict`（fail closed）。

## 6. 已知服务端限制

1. `PERSONAL_DATA_ORCHESTRATION_SECRET` 未配置（或 < 32 字节）时，一切会话写操作
   返回 `confirmation_secret_unavailable`（runtime 类，可重试但需先修复配置）。
2. stock rag-api 未注入 `generation_runner`：generate 跳返回
   `generation_provider_unavailable`；publish/decide/行动/观察/校准不受影响。
3. 高风险域（健康/财务/关系）词表在 prepare 直接拒绝
   （`high_risk_or_external_action_forbidden`）；外部动作永远禁止。
4. 编排事件 append-only：写入不可删除，后续阶段只能以新事件修正。
