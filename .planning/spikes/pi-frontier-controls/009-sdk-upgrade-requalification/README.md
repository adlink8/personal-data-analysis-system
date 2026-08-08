---
spike: 009
name: sdk-upgrade-and-requalification
type: standard
validates: "Given an accepted exact package lock, when version, integrity, API or event schema drifts, then qualification fails closed and the feature flag returns to legacy."
verdict: VALIDATED
related: [001, 005]
tags: [upgrade, schema, supply-chain, rollback]
---

# Spike 009: SDK Upgrade and Requalification

## How to Run

```powershell
python D:\ADLINK\数据分析\.planning\spikes\pi-frontier-controls\upgrade_requalification.py
```

## Investigation Trail

- 读取 Spike 001 的真实 `package-lock.json`，以 Pi coding-agent 0.83.0 及依赖集合形成 baseline fingerprint。
- 修改 version 或 event fingerprint 后，资格检查分别返回 `version_drift` / `event_fingerprint_drift`。
- drift 时 feature flag 路由到 legacy，未发生任何 authority 写入。

## Results

通过 deterministic drift detection 与 rollback 夹具；真实新版本升级安装尚未执行。
