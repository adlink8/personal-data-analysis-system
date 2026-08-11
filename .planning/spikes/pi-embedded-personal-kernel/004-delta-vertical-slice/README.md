---
spike: 004
name: delta-triggered-vertical-slice
type: standard
validates: "Given a deterministic conversation Delta, when the trigger policy runs, then empty Delta makes zero model calls and valuable Delta creates one evaluated Candidate without authority mutation."
verdict: VALIDATED
related: [002, 003]
tags: [delta, watermark, evaluation, idempotency]
---

# Spike 004: Delta-triggered Vertical Slice

## How to Run

```powershell
cd <repo-root>\.planning\spikes\pi-embedded-personal-kernel\prototype\python-domain
python delta_vertical_slice.py
```

## Investigation Trail

- Delta=0 在创建 task/session 前停止，计数为 task=0、session=0、model_calls=0。
- valuable Delta 创建单 task、单 session、单 model call、单 Candidate，并运行一次 deterministic evaluation。
- model failure 进入 retryable terminal，Candidate=0；同一 Delta 重跑返回 replay，Candidate 总数仍为 1。

## Results

通过 synthetic vertical slice。正式 watermark、active pointer 与 authority fingerprint 全程不变；真实 cohort 尚未执行。
