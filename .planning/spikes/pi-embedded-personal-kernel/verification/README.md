# Verification Evidence

执行时在本目录保存 metadata-only 证据：

```text
runtime-resource-registry.json
package-integrity-report.json
task-ledger-transitions.jsonl
fault-injection-report.json
authority-before.json
authority-after.json
delta-scenario-report.json
legacy-pi-comparison.json
stream-recovery-report.json
privacy-audit.json
```

禁止保存原始个人正文、完整 URL、HAR/video、凭据、provider request/response body、confirmation token 或真实数据库副本。

## Recorded This Run

- `runtime-resource-registry.json` — 001 的 Pi runtime allowlist 与资源计数
- `task-ledger-report.json` — 002 的幂等、取消、并发 claim、unknown outcome
- `delta-scenario-report.json` — 004 的 empty/valuable/failure/replay 计数
- `stream-recovery-report.json` — 005 的 cursor replay、duplicate、cancel 与安全投影
