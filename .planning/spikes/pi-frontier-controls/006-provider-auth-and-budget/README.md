---
spike: 006
name: provider-auth-and-budget-fail-closed
type: standard
validates: "Given a provider boundary with injected credentials and a fixed budget, when auth/quota/timeout/oversize failures occur, then errors are typed, secrets stay out of evidence and authority is unchanged."
verdict: PARTIAL
related: [001, 004]
tags: [provider, auth, budget, fail-closed]
---

# Spike 006: Provider Auth and Budget Fail-Closed

## How to Run

```powershell
python D:\ADLINK\数据分析\.planning\spikes\pi-frontier-controls\provider_budget.py
```

## Results

Synthetic provider harness通过：缺鉴权、timeout、quota、oversized response 和 budget exhaustion 均返回 typed error；只记录 credential hash，不记录 credential value；authority fingerprint 不变。未调用真实付费 Provider，因此判定 `PARTIAL`。
