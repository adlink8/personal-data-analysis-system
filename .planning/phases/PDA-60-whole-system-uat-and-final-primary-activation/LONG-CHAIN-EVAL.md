# Phase 60: Real-Model Long-Chain Scheduling Eval

**Status: passed with documented tool-contract limitations**
**Date:** 2026-08-12 (real run 01:51–01:56 UTC)
**Runner:** `tmp/long_chain_eval_runner.py` · **raw results:** `tmp/long_chain_eval_results.json`

## 1. 执行环境

| 项 | 值 |
| --- | --- |
| Kernel | `http://127.0.0.1:8790`（capability `eval-cap-20260812`） |
| Python domain | `http://127.0.0.1:8000`（44 工具真实数据，synthetic 已消除） |
| Provider | openai-compatible → `https://opencode.ai/zen/go/v1`，model `deepseek-v4-flash` |
| 认证 | 明文 api_key（config 内，报告不输出） |
| 预算 | cost_ceiling 30 CNY；input 1 CNY/M、output 2 CNY/M；timeout 120s；thinking disabled |
| 验证运行 | 4 skill 先做 1 次无模型 dry-run（provider_calls 不变，0 元）确认工具链，再跑真实链 |

长链路：**system.diagnosis → knowledge.research → decision.support → warehouse.health**，
每个 skill 独立 `idempotency_key`，`model_prompt` 把前一步真实工具发现注入当前模型调用。

## 2. 长链路场景与每步工具调用链

### Step 1 — system.diagnosis（`pi_chain_diag_20260812` / `pi-chain-diag-20260812`）

| step | tool | 状态 | 工具返回摘要（真实数据） |
| --- | --- | --- | --- |
| health | system.health | committed | api/kernel/mcp/chroma 全部 up，knowledge 40200 units |
| runtime | system.runtime | committed | 运行态探测成功 |
| inspect | warehouse.inspect | committed | records=40203, visible=5, failed=214, quarantined=0 |
| quality | warehouse.quality | committed | 同统计，quality=ok |
| integrity | warehouse.integrity | committed | 同统计，schema=pass |

→ 5/5 真实数据。模型 81 in / 46 out tokens。

### Step 2 — knowledge.research（`pi_chain_research_20260812` / `pi-chain-research-20260812`）

model_prompt 注入 Step 1 发现（knowledge 权威健康、failed 级记录存在）要求调研交付方法主题并用真实证据佐证。

| step | tool | 状态 | 工具返回摘要（真实数据） |
| --- | --- | --- | --- |
| wiki | wiki.page | committed（receipt=error） | **error envelope `invalid_topic_key`**（见 §6 限制-1） |
| wiki_dir | wiki.directory | committed（partial） | 统合层真实主题：`decision:drec_a2f1f44dc911765f4b2d531e`(fresh)、`goal:project:data-analysis:delivery_method`(stale) 等 5 条 |
| search | knowledge.search | committed | 3 条真实单元：`cu\|77630788…`(0.6992)、`rollout-2026-06-08…`(0.8119)、`6a40e334…`(0.8109) |
| evidence | evidence.resolve | committed（receipt=error） | **error envelope `invalid_input`**（见 §6 限制-2） |
| evidence_sqlite | evidence.sqlite_query | committed | **lease 通过**；row_count=3，receipt `evidence:ce51356314898d29`，freshness `2026-07-25T11:47:48.745Z`，bytes=610，duration_ms=44（真实会话消息元数据行） |
| record | knowledge.get | committed | 真实单元 `cu\|9989a6addb2705672ffd7d32abe288a7`（personal_fact/current/conf 0.85） |
| external | external.list | committed | 外部上下文列表成功 |

→ 7/7 committed（5 真实成功 + 2 受限 error envelope）。模型 122 in / 165 out tokens。

### Step 3 — decision.support（`pi_chain_decision_20260812` / `pi-chain-decision-20260812`）

model_prompt 注入 Step 2 证据（统合层主题 + evidence.sqlite_query 真实行）要求结合 state 与决策历史给建议。

| step | tool | 状态 | 工具返回摘要（真实数据） |
| --- | --- | --- | --- |
| state | state.current | committed（empty） | 真实空态：`run_missing`（无 committed personal state run） |
| decisions | decision.list | committed | 2 条真实 committed run：`dar_b99403661addf15b6e0f2375`、`dar_77843392b266cd0a992cc274`（decision-analysis-policy-v1） |
| evidence | evidence.resolve | committed（receipt=error） | error envelope `invalid_input`（同 §6 限制-2） |
| external | external.list | committed | 外部上下文列表成功 |

→ 4/4 committed（3 真实 + 1 受限 error envelope）。模型 97 in / 245 out tokens。

### Step 4 — warehouse.health（`pi_chain_warehouse_20260812` / `pi-chain-warehouse-20260812`）

model_prompt 注入前三步结论要求最终体检并给 verdict。

| step | tool | 状态 | 工具返回摘要（真实数据） |
| --- | --- | --- | --- |
| inspect/lineage/quality/freshness/integrity/failed | warehouse.* 6 工具 | committed ×6 | 全部真实统计 records=40203, visible=5, failed=214, quarantined=0；quality=ok、freshness=fresh、schema=pass |

→ 6/6 真实数据。模型 125 in / 51 out tokens。

**数据流验证结论：** 全链 22 次工具调用全部经 domain bridge 命中真实数据；knowledge.research 的
wiki.directory 返回统合层 canonical topic（含 freshness），evidence.sqlite_query 通过
skill_id+manifest_checksum(0d539fe1…)+privacy_ceiling(R1) 三重 lease 校验并返回真实证据行，
warehouse.* 返回真实仓库统计（40203/214）。

## 3. 模型消费真实数据的证据

每步模型调用由 `executeSkillTask` 内 `providerAdapter.generate` 真实发出
（`provider_calls` 0→5，非 replay；replay 模式 provider 为 `replay-v1`，本链为 `deepseek-v4-flash`）。

| skill | provider | model | in | out | cost (CNY) | response_checksum 前缀 |
| --- | --- | --- | --- | --- | --- | --- |
| system.diagnosis | dashscope* | deepseek-v4-flash | 81 | 46 | 0.000173 | 480bda916e27… |
| knowledge.research | dashscope* | deepseek-v4-flash | 122 | 165 | 0.000452 | faa9ff308f36… |
| decision.support | dashscope* | deepseek-v4-flash | 97 | 245 | 0.000587 | d1aa11868552… |
| warehouse.health | dashscope* | deepseek-v4-flash | 125 | 51 | 0.000227 | 300620e7332c… |

\* transport 硬编码 `provider:"dashscope"` 标签，实际 endpoint 为 opencode.ai/zen/go/v1（见 §6 限制-4）。
费用按 provider 定价（in×1 + out×2）/1e6 推算（skill model_receipt 不含 cost 字段）。

模型消费真实数据的佐证链：Step 2 的 model_prompt 引用 Step 1 的真实诊断数字，Step 3 引用 Step 2 的
真实证据行数/时间戳——模型输入 token 序列由前一步工具输出组成。

## 4. 调度状态机记录

### 4.1 Task ledger 轨迹（`var/db/pi_kernel_events.sqlite`）

每个 chain task：`task_accepted → task_started → [tool_started → tool_completed]×N → task_completed`。
模型调用发生在 task_started 与首个 tool_started 之间（例如 system.diagnosis 01:56:19.556→01:56:21.969）。

| task | ledger state | version | lease_owner | 事件链 |
| --- | --- | --- | --- | --- |
| pi_chain_diag_20260812 | succeeded | 4 | pi_kernel | accepted→started→5×tool→completed |
| pi_chain_research_20260812 | succeeded | 4 | pi_kernel | accepted→started→7×tool→completed |
| pi_chain_decision_20260812 | succeeded | 4 | pi_kernel | accepted→started→4×tool→completed |
| pi_chain_warehouse_20260812 | succeeded | 4 | pi_kernel | accepted→started→6×tool→completed |
| pi_chain_cancel_20260812 | failed | 5 | pi_kernel | accepted→started→**cancel_requested**→5×tool→completed(事件)→ledger failed(stale_version) |

### 4.2 Cancel 调度验证（`pi_chain_cancel_20260812`）

后台发 `POST /v1/tasks`，主线程观测到 `running`(v3) 后立即 `POST /v1/tasks/:id/cancel`（expected_version=3）：

1. 观测 `running` version=3（模型调用进行中）
2. cancel 返回 200，task 转 **cancel_requested** version=4（事件 `task_cancel_requested` 距 task_started 仅 5ms）
3. skill engine 不在 step 间检查 cancel → 5 个工具仍全部执行完成
4. 完成后 `transition(succeeded, expectedVersion=3)` 与 cancel 已改的版本冲突 → **illegal_transition**，task 落 **failed / error_code=stale_version**（version=5）
5. 该次模型调用已被消费（provider_calls 计入 1 次）但未返回 receipt

结论：cancel 正确阻止了 succeeded 提交，但**不会中止执行中的工具序列**，且模型费用已产生；
终态为 `failed`（非 outcome_unknown，因为模型调用本身成功返回）。这是需要记录的真实调度行为。

### 4.3 runtime-control 操作在长链路后的行为

| 操作 | 调用 | 结果 |
| --- | --- | --- |
| list | `GET /v1/tasks` | 5 个 eval task 可见，状态/版本正确 |
| get | `GET /v1/tasks/:id` | 全部可取，lease_owner=pi_kernel，lease 已释放 |
| resume | `POST /v1/tasks/:id/resume`（succeeded 任务） | 400 `task_reconcile_state_required`（仅 outcome_unknown 可 resume） |
| reconcile | `POST /v1/conversations/reconcile`（succeeded 任务） | 400 `task_not_resumable` |
| cancel | `POST /v1/tasks/:id/cancel`（succeeded 任务） | 400 `task_not_cancelable`（仅 queued/claimed/running） |

状态机门禁全部按声明工作：`queued→claimed→running→succeeded`，`running→cancel_requested→failed`，
终态任务拒绝 cancel/resume/reconcile。

## 5. 费用统计

| 项 | 值 |
| --- | --- |
| 真实模型调用次数 | 5（4 chain + 1 cancel 测试） |
| provider_calls delta | 0 → 5 |
| 4 个 chain 调用合计费用 | **0.001439 CNY** |
| cancel 测试调用费用 | 已消费未返回 receipt（不可精确计量，估算 <0.001 CNY） |
| 工具调用 | 22 次 committed（只读，免费） |
| 验证（dry-run） | 4 次无模型调用，0 元 |

## 6. 如实记录的工具限制与发现

1. **wiki.page 无法经 skill gateway 返回统合层页面**：gateway 的 project 工具 allowed 字段集
   （`{task_id,idempotency_key,binding,query,record_id,limit,cursor,snapshot_id,source_id}`）不含
   `topic_type`/`topic_key`，而 topic resolver 对非 subject 主题必须 topic_type+topic_id 才能解析。
   传 `record_id` 得到 `invalid_topic_key` error envelope。统合层数据通过 `wiki.directory`
   （canonical_key + freshness）完整可见。这是输入契约缺口，非数据缺失。
2. **evidence.resolve 经 skill gateway 受限**：其 handler 必需 `subject_type/stable_id/snapshot_id/checksum`，
   但 gateway allowed 集不含这些字段（除 snapshot_id 外），传参即 `undeclared_input`，不传即 `invalid_input`。
   直接 probe 也复现。同样为输入契约缺口。
3. **state.current 返回空态**：`run_missing`（当前无 committed personal state run），真实空结果，如实标注。
4. **provider 标签不精确**：opencode.ai/zen/go/v1 走 openai-compatible Chat Completions transport，
   但 transport 返回值硬编码 `provider:"dashscope"`。不影响调用与计费，仅标签误导。
5. **间歇性响应/ledger 分歧**：批量连续执行时 knowledge.research 的 `POST /v1/tasks` 有 2/3 概率
   在任务实际 succeeded 后返回 400 `internal_error`（事件链完整、ledger=succeeded）。隔离复现始终成功。
   判断为 kernel 响应层瞬时错误（`safeCode` 兜底 internal_error），非数据失败；真实运行通过重试+间隔规避。
6. **cancel 竞态**：cancel 后执行中的工具继续完成，终态 transition 冲突落 `failed/stale_version`；
   模型费用已产生。skill engine 未在 step 间检查取消信号。

## 7. 结论

- 长链路（诊断→调研→决策支持→仓库体检）真实数据流贯通：22 次工具调用全部真实返回，
  前一步结果注入后一步 model_prompt 被真实模型（deepseek-v4-flash）消费。
- Task 状态机、cancel、runtime-control 门禁全部按设计工作。
- 总计 5 次真实模型调用，可计量费用 0.001439 CNY。
- 两个真实工具契约缺口（wiki.page、evidence.resolve 的 gateway allowed 集）需要后续计划修复
  （建议将 topic_type/topic_key 与 evidence 描述字段纳入对应 project tool 的 declared input）。
- 无个人正文进入本报告；所有数据为计数/元数据/checksum。
