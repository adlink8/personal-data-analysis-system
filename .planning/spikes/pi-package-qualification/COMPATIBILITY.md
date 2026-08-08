# Compatibility Matrix

**Status:** PARTIAL EXECUTION — 2026-08-04

| Consumer | Provider | Contract | Planned check | Result |
|---|---|---|---|---|
| coding-agent 0.83.0 | agent-core 0.83.0 | AgentEvent/Tool/Message | runtime allowlist + custom tool state | PASS |
| coding-agent 0.83.0 | pi-ai 0.83.0 | model/stream/usage/auth | provider stub + usage reconciliation | NOT_RUN — real provider deferred |
| coding-agent 0.83.0 | sqlite storage 0.83.0 | session create/resume/fork | crash/reopen/branch tests | NOT_RUN — separate storage study needed |
| Cockpit adapter | coding-agent 0.83.0 | safe SSE event projection | schema/ordering/replay tests | PASS — synthetic 005 |
| pi-web-ui 0.75.3 | agent-core 0.83.0 | message/tool/artifact/abort | build + fixture renderer test | DEFERRED/RISK — version mismatch |
| Python Domain API | Node runtime | request/result/error/cancel | contract + fault injection | PASS — synthetic 002; HTTP transport not run |

版本号相等不等于运行时兼容；每一行必须有可执行 fixture 或故障注入证据。
