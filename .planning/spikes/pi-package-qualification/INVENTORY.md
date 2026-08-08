# Candidate Package Inventory

版本信息核对日期：2026-08-03。版本只用于规划冻结；执行前必须再次核对 registry、源码 tag/commit 和 integrity。

## Official Candidates

| Package | Observed version | Initial role | Initial status |
|---|---:|---|---|
| `@earendil-works/pi-coding-agent` | 0.83.0 | Embedded AgentSession/Runtime/ResourceLoader | candidate P0 |
| `@earendil-works/pi-ai` | 0.83.0 | provider/model/event/usage abstraction | candidate P0 |
| `@earendil-works/pi-agent-core` | 0.83.0 | transitive core; direct fallback only | candidate transitive |
| `@earendil-works/pi-storage-sqlite-node` | 0.83.0 | Session trajectory storage | candidate P0 |
| `@earendil-works/pi-web-ui` | 0.75.3 | optional renderer/components | deferred compatibility |

`pi-web-ui` 与核心包观察版本不一致，必须先验证 event/message/tool/artifact/abort/attachment contract，不能默认兼容。

## Community Candidates

| Package | Observed version | Intended use | Initial status |
|---|---:|---|---|
| `@gotgenes/pi-permission-system` | 24.0.0 | permission model/adapter ideas | deferred; audit/fork only |
| `pi-mcp-adapter` | 2.18.0 | allowlisted external MCP only | deferred |
| `pi-web-access` | 0.17.1 | ExternalEvidenceCandidate only | deferred |
| `pi-hermes-memory` | 0.9.2 | scanner/fencing mechanisms only | extract-only candidate |
| `pi-memory` | 0.4.0 | scratchpad interaction idea | extract-only candidate |
| `pi-subagents` | 0.40.0 | future read-only reviewers | deferred after PIK-05 |
| `@narumitw/pi-goal` | 0.43.0 | circuit-breaker/state ideas | extract-only candidate |

## Rejected Categories by Policy

- Cron/task-scheduler Pi Package
- automatic Goal Loop
- swarm/dynamic multi-agent workflow
- self-installing/self-modifying Package
- arbitrary bash/file/SQL/browser-cookie access
- automatic Session Memory → long-term Personal Fact

