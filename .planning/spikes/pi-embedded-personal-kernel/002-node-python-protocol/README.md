---
spike: 002
name: node-python-protocol-and-task-ledger
type: standard
validates: "Given Python owns the task ledger, when duplicate, concurrent, cancelled, crashed and restarted calls occur, then typed state and side effects remain recoverable and idempotent."
verdict: VALIDATED
related: [001, 003, 004]
tags: [protocol, idempotency, cancellation, recovery]
---

# Spike 002: Node/Python Protocol and Task Ledger

## How to Run

```powershell
cd D:\ADLINK\数据分析\.planning\spikes\pi-embedded-personal-kernel\prototype\python-domain
python protocol_spike.py
```

## Investigation Trail

- 使用独立 SQLite ledger 和 synthetic Candidate；请求包含 `task_id`、`tool_call_id`、`idempotency_key`、`schema_version`、`task_key`、deadline 与 args checksum。
- 相同 key 重放返回 exact replay；不同 args 返回 `typed_conflict`。
- 取消在 Domain 调用前终止；崩溃发生在 Candidate 插入后进入 `outcome_unknown`，重启后禁止盲目重放。
- 两个线程同时 claim 同一 task，结果为一个 `claimed`、一个 `busy`。

## Results

通过。2 个 Candidate（成功 1、崩溃边界 1）无重复；authority fingerprint 前后不变；取消、unknown outcome、重启恢复与并发 claim 均有可复现输出。
