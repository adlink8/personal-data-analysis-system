---
spike: 008
name: session-retention-and-privacy-expiry
type: standard
validates: "Given metadata-only Session/log/crash artifacts, when expiry runs, then expired artifacts disappear, secrets are rejected and formal authority survives."
verdict: VALIDATED
related: [001, 003, 005]
tags: [privacy, retention, erasure]
---

# Spike 008: Session Retention and Privacy Expiry

## How to Run

```powershell
python <repo-root>\.planning\spikes\pi-frontier-controls\retention_privacy.py
```

## Results

通过 synthetic metadata-only retention：Session/crash 过期文件被清理，authority sentinel 保留；secret/raw body 写入被拒绝；剩余文件仅 authority metadata。
