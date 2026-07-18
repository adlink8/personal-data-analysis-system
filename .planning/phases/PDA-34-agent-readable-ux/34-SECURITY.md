---
phase: 34
status: verified
threats_open: 0
created: 2026-07-19
---

# Phase 34 Security

| Threat | Mitigation | Status |
|---|---|---|
| Large-context disclosure | 16 KiB budget; oversized detail removed; full evidence requires drill-down | closed |
| Capability/secret leakage | capability, credentials, provider/raw body keys removed; privacy guard retained | closed |
| Prompt-induced unsafe recovery | recovery operations are static allowlists, never authority/provider text | closed |
| Duplicate unknown provider calls | unknown outcome is non-retryable; resume/inspect/manual review only | closed |
| Automatic promotion suggestion | no recovery entry can promote; calibration limitation stays explicit | closed |
| Cross-transport semantic drift | REST/stdio equality and Node passthrough tests | closed |

No accepted risks. `threats_open: 0`.
