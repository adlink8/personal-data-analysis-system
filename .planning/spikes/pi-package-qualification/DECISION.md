# Package Decisions

**Overall status:** CONDITIONAL

| Package | Decision | Allowed scope | Evidence | Review expiry |
|---|---|---|---|---|
| `@earendil-works/pi-coding-agent` | CONDITIONAL | Spike runtime only; no production/P0 acceptance | npm audit: undici + brace-expansion advisories | requalify after remediation |
| `@earendil-works/pi-ai` | CONDITIONAL | Spike model adapter only; no credential discovery | exact 0.83.0 lock; shared dependency audit | requalify after remediation |
| `@earendil-works/pi-agent-core` | CONDITIONAL | transitive; direct fallback requires new decision | exact 0.83.0 lock | requalify after remediation |
| `@earendil-works/pi-storage-sqlite-node` | CONDITIONAL | Session trajectory only | exact 0.83.0 lock; scripts ignored | requalify after remediation |
| `@earendil-works/pi-web-ui` | DEFERRED | renderer compatibility study only | version mismatch | — |
| all community candidates | DEFERRED | no runtime load in P0 | source/runtime audit required | — |

`PENDING` 和 `DEFERRED` 均不构成安装、生产依赖或运行授权。

`CONDITIONAL` 仅允许当前隔离 Spike 复现，不构成生产依赖授权。npm audit 使用 npmjs.org registry；本机 npmmirror audit endpoint 返回 404，未作为安全结论依据。
