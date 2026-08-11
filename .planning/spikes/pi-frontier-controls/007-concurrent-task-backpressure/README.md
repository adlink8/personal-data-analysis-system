---
spike: 007
name: concurrent-task-backpressure
type: standard
validates: "Given multiple Delta tasks, when workers contend under bounded capacity, then duplicate keys coalesce and active work stays within backpressure limits."
verdict: PARTIAL
related: [002, 004]
tags: [concurrency, backpressure, quotas]
---

# Spike 007: Concurrent Task Backpressure

## How to Run

```powershell
python <repo-root>\.planning\spikes\pi-frontier-controls\backpressure.py
```

## Results

2 worker/4 queue harness通过：最大 active=2，重复 `A-1` 只接受一次，超出队列的 `E-1` 被明确 backpressure 拒绝，A/B/C/D 均完成。判定 `PARTIAL`：尚未在真实 Provider rate limit 或跨进程 worker 集群上验证。
