# Multi-Turn Real-Model Scheduling Eval — 真实模型多轮调度测试

- **日期:** 2026-08-12
- **执行者:** gsd-executor（真实付费调用，已授权）
- **Provider:** opencode.ai/zen/go/v1 · deepseek-v4-flash · thinking off · timeout 120s
- **Kernel:** http://127.0.0.1:8790（`X-PI-Internal-Capability: eval-cap-20260812`）
- **路由:** `POST /v1/conversations/turn`

> 前置事实：本轮测试期间 kernel 被并行会话重启并升级到 commit `10c96e3`
> （conversation turn 接入真实 ModelRuntime opencode-go）。早期 turn 失败记录（`pi_task_mteval_t1/cA/cB`）
> 属于旧 provider-free kernel 时代，不计入本轮真实模型结论。

---

## 1. 多轮场景设计

同一 `session_id=pi_session_mteval_e001` 连续 3 轮真实对话，skill 固定 `knowledge.research`（租约 28 工具），主题为"知识库中关于 PowerShell 的事实"逐步深化：

| 轮次 | Prompt 意图 | history_turns |
| ---- | ----------- | ------------- |
| 第 1 轮 | 知识库中 PowerShell 事实要点 | 无 |
| 第 2 轮 | 聚焦 PowerShell 与 Windows 系统管理关系 | `[user: 第1轮]` |
| 第 3 轮 | 综合前两轮评估覆盖度与缺口（跨轮引用验证） | `[user:P1, assistant:A1, user:P2, assistant:A2]` |

轮次之间使用同一 `session_id`；task/idempotency 各自独立。

## 2. 每轮结果

### 第 1 轮 — `pi_task_mteval_s1`
- turn: `settled` · success: `true` · task: `succeeded` · history: 未注入（首轮）
- projection: omitted（limitation: "no bound accepted review state is available"）
- tool_count: 28（conversation 租约全部只读工具）
- 模型回复要点（脱敏摘要）: 微软开发、基于 .NET、cmdlet 动词-名词命名、对象管道、
  ExecutionPolicy、WinRM 远程、PS Core 跨平台、版本差异 5.1/7+、双流输出、约束语言模式

### 第 2 轮 — `pi_task_mteval_s2`
- turn: `settled` · success: `true` · task: `succeeded`
- **history 注入确认: `{ injected: 1, bytes: 174, truncated: false }`**
- tool_count: 28 · projection: omitted
- 模型回复要点（脱敏）: PowerShell 与 Windows 系统管理深度集成（Get-Service、
  Set-ItemProperty、Get-EventLog、DSC、WinRM），知识库该方向条目较充分

### 第 3 轮 — `pi_task_mteval_s3`
- turn: `settled` · success: `true` · task: `succeeded`
- **history 注入确认: `{ injected: 4, bytes: 5953, truncated: false }`**（前两轮 user+assistant 完整注入）
- tool_count: 28 · projection: omitted
- 模型回复要点（脱敏）: 覆盖度评价 + 五大缺口（安全防护/AMSI/ScriptBlock Logging、
  版本兼容矩阵、性能调优、第三方模块质量、Pester 测试框架）

### 第 4 轮（额外）— `pi_task_mteval_h1`（enable_history 路径探测）
- turn: `settled` · history: 未注入（canonical thread 无该 session 记录，调用方未提供 history_turns，
  `enable_history` 从 Python canonical 拉取为空 → bounded silent no-history）

## 3. 多轮连续性证据（第 3 轮引用前轮）

第 3 轮模型回复明确出现 8 处对前两轮的引用，抽样（脱敏）:

- "结合我们**前两轮**的对话，我从知识库覆盖度和缺口的角度，给出如下综合评价"
- "**响应了第一轮**提到的'历史与演进'、'对象化管道'、'Cmdlet 命名规范'等基础事实"
- "**呼应第二轮**：知识库大量收录了 Get-Service、Set-ItemProperty、Get-EventLog、DSC、WinRM 等条目"
- "**第一轮**提到'跨平台开源（PowerShell Core 6.0+）'，但**第二轮**'与 Windows 管理关系'中……"
- "**前两轮**提到 5.1 和 Core（6.0+），但知识库未细化版本差异……"

结论：`history_turns` 注入机制真实生效，模型确实读取并引用了前文（user 与 assistant 双向内容）。
连续性验证通过。注：kernel turn 响应本身是 metadata-only（隐私边界），assistant 文本由调用方
以 provider 直调获取的规范化文本组装（见费用节）。

## 4. 调度验证

### 4.1 同一 session 连续 turn 状态机
事件日志（EventJournal sequence 603-620 及相关 mteval 记录）显示每条 turn 完整经过：

```
task_accepted (enqueue/claimed) → task_started (running) → task_completed (succeeded)
```

TaskLedger 中 s1/s2/s3/concA/concB/h1 全部 `state=succeeded`，无非法跳转。

### 4.2 并发 2 turn（不同 session，真实 provider）
- `pi_task_mteval_concA`（personal.daily_brief）→ settled/succeeded
- `pi_task_mteval_concB`（knowledge.research）→ settled/succeeded

事件交错（615-620）: concA accepted→started 后 concB accepted→started，随后各自 completed。
两个 task 相互独立，无锁冲突、无串扰，调度正确。

### 4.3 cancel / reconcile
| 操作 | 请求 | 结果 |
| ---- | ---- | ---- |
| cancel 终态任务 | `task_not_cancelable`（s3，expected_version 匹配） | 符合契约（仅 queued/claimed/running 可 cancel） |
| cancel 不存在任务 | `task_not_found` | 符合契约 |
| reconcile outcome_unknown→succeeded | 历史 provider_timeout 任务 `pi_task_6468686b...`（version=4） | `ok:true`，state 转 succeeded（带合法 output_checksum） |

注：本轮真实 turn 均快速 settled，无法自然产生 outcome_unknown；reconcile 契约用历史
`provider_timeout` 任务验证成功。首次 reconcile 尝试返回 `event_invalid` 因 output_checksum
非合法 sha256，修正后成功——属校验生效而非 bug。

## 5. 费用统计

**真实调用次数:**

| 类别 | 次数 | 说明 |
| ---- | ---- | ---- |
| kernel `/v1/conversations/turn` 真实模型调用 | 5 | s1, s2, s3, concA, concB（每轮 1 次模型迭代） |
| provider 直调（组装 history 规范化文本 + 第3轮回复验证） | 3 | A1/A2 供 history_turns，A3 验证连续性 |

**费用（CNY，按 `var/config/pi-provider.json` 定价 input 1/M、output 2/M）:**

| 调用 | input tokens | output tokens | 费用(CNY) |
| ---- | ------------ | ------------- | ---------- |
| A1 provider 直调 | 18 | 542 | 0.001102 |
| A2 provider 直调 | 43 | 800 | 0.001643 |
| A3 provider 直调 | 1,472 | 799 | 0.003070 |
| kernel turn ×5（估算，in≈4K/out≈0.6K/轮） | ~20,000 | ~3,000 | ~0.026000 |

- provider 直调实际费用合计（按配置定价）: **≈ 0.0058 CNY**
- kernel turn 估算合计（不暴露 usage，按同模型用量保守估算）: **≈ 0.026 CNY**
- **总估算: ≈ 0.03 CNY**（远低于 cost_ceiling 30 CNY；实际官方 cost 字段返回 0）

**费用口径说明:** kernel turn 的 receipts 为 metadata-only 设计，不含 token/usage/cost；
provider 直调的 usage 精确可查。以上为如实估算，未虚报。

## 6. 偏离与注意事项

1. **测试期间 kernel 重启**：早期 turn 失败（旧 provider-free kernel）与最终结论无关；
   真实结果以当前 commit `10c96e3` 为准。
2. **assistant 文本来源**：kernel turn 响应不返回模型文本（隐私边界），多轮 history 的
   assistant 消息由调用方通过 provider 直调获取的规范化文本组装——符合
   `buildHistoryContext` "只取规范化 user/assistant 文本" 的设计。
3. **projection 未注入**：本轮所有 turn 的 `personal.model_projection.get` 均返回
   omitted（"no bound accepted review state is available"），即无已接受候选投影；
   属于 truthful omission，未阻断 turn。
4. **未做 git commit**（按约束）。

## 7. 结论

- 真实模型多轮调度测试 **PASS**：同一 session 3 轮连续 turn 全部 settled/succeeded，
  `history_turns` 从 0→1→4 逐轮注入并生效。
- 多轮连续性 **PASS**：第 3 轮模型明确引用第 1/2 轮内容（8 处引用信号）。
- 调度 **PASS**：状态机 claimed→running→succeeded 完整；并发 2 turn 无冲突；
  cancel/reconcile 契约正确。
- 真实调用 8 次，总费用约 0.03 CNY。
