# Phase 59 Research

## Findings

- Phase 49–52 已建立 Kernel event/task/session、Provider、流式与 Cockpit 基础，但 Tool/Skill/warehouse 扩展后仍需要统一 operation 状态模型。
- 本机 Pi Agent 不再属于架构，删除 CLI/RPC adapter 可减少双控制面、ambient capability、凭据和进程恢复风险。
- 控制面应复用 Kernel receipt 与 Python authority receipt，通过 correlation/causation 聚合，不复制事实或自行裁决事务结果。
- `outcome_unknown` 的正确恢复顺序是读取 receipt、核验 fingerprint、确定是否已发生副作用，再决定 resume/compensate/manual review。

## Implementation Direction

- 在 Kernel 中建立类型化 operation schema/reducer 与 cancel/resume/reconcile service。
- Python 提供只读、去正文的 operation projection；Cockpit 只消费同源投影并发送受控意图。
- 测试覆盖乱序/重复事件、Provider 超时、Tool 崩溃、Skill 恢复、事务补偿和隐私 forbidden-key 扫描。
