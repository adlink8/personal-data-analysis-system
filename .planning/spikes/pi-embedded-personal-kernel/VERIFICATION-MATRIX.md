# Verification Matrix

## Global Invariants

| Gate | Evidence | Pass condition |
|---|---|---|
| No coding authority | final Tool/Resource registry + negative calls | 未加载或执行 coding/ambient tools |
| Zero-call empty Delta | task/session/model counters | 全部为 0 |
| One task per Delta | ledger unique key + concurrency test | 一个逻辑 task、最多一个 active attempt |
| Candidate evidence | schema/evaluation report | `task_id/source_cutoff/evidence_refs/checksum` 齐全 |
| Exact replay | duplicate/rerun report | 不新增第二 Candidate |
| Cancellation | event + ledger chain | terminal state 一致，无迟到副作用 |
| No authority mutation | before/after fingerprints | watermark、active pointer、canonical/KU 行及 checksum 不变 |
| Session isolation | three-store audit | Session 不含正式 Artifact/Knowledge，删除互不影响 |
| Feature rollback | flag test | 关闭后完全回到 legacy |
| Privacy | log/session/SSE/network audit | raw body、secret、provider payload 泄露数为 0 |

## End-to-End Scenarios

| Scenario | Trigger | Expected |
|---|---|---|
| A — no change | deterministic Delta=0 | task=0, session=0, model calls=0 |
| B — valuable delta | one eligible conversation Delta | one task, ≥2 Domain Tool calls, one evaluated Candidate, no promote |
| C — failure/recovery | fail Agent/Tool/model/eval at controlled points | typed terminal/retry state, no watermark/active mutation, restart recovery |
| D — high-impact correction | stale preference evidence | proposal only, explicit review required, no automatic supersede |

## Fault Injection Matrix

| Fault | Required observation | Forbidden outcome |
|---|---|---|
| Node crash before Tool | retryable attempt | Candidate or watermark change |
| Node crash after Tool response | replay/reconcile by call checksum | duplicate Candidate |
| Python crash during request | retryable or outcome_unknown | blind automatic write retry |
| model timeout | typed timeout + budget record | silent retry beyond policy |
| cancel during Tool | cancelling → cancelled/failed_terminal | orphan write |
| late Tool response | ignored or reconciled by attempt | state regression |
| duplicate event delivery | deduplicated by event id/sequence | duplicate UI action |
| Session replacement | re-subscribe/rebind evidence | missing terminal event |
| malicious Skill/Extension | rejected before execution | code/process/network access |
| stale Delta manifest | typed stale result | processing against changed cutoff |

## Qualification Thresholds

正式阈值在执行 Spike 时以 legacy baseline 固化；以下为最低安全门：

- privacy incident count = 0
- active knowledge pollution count = 0
- duplicate logical Candidate rate = 0
- unauthorized Tool execution count = 0
- empty Delta model calls = 0
- task terminal-state coverage = 100%
- evidence-required Candidate pass rate = 100%
- cancellation leaves no unregistered side effect = 100%

质量、token 与 latency 不预设虚假改善幅度；必须先测 legacy baseline，再在 `DECISION.md` 解释统计差异和样本限制。

