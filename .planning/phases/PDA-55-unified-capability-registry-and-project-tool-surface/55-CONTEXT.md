# Phase 55: Unified Capability Registry and Project Tool Surface — Context

<domain>
## Phase Boundary

建立 Project Capability Registry，并让 REST/MCP/Pi Kernel 从同一契约生成或验证 descriptor。把现有只读项目能力收敛为稳定 Domain Tools。本阶段不开放底仓正式写入、不创建 Skills。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** registry 是能力 SSOT；REST/MCP/Pi adapter 不再各自维护冲突的 schema。
- **D-02:** Tool 名称使用 `domain.operation` namespace，内部 Python 函数、脚本、路径和表名不属于公共契约。
- **D-03:** 每项能力声明 profile、privacy、authority、side effect、budget、timeout、idempotency、confirmation 和 receipt。
- **D-04:** production/operator profile 由 registry 过滤；unknown、checksum drift、tool escalation fail-closed。
- **D-05:** 首批只读域覆盖 knowledge、retrieval、state、external、decision、action/outcome、evidence、wiki、data quality 和 system health。
- **D-06:** descriptor generation 必须确定性；现有 MCP 用户可见名称在兼容映射中保留一个版本周期。

### the agent's Discretion

JSON schema 文件拆分、Python/Node codegen 模块布局和 descriptor 快照格式。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `apps/personal_data_chatgpt/server.mjs`
- `governance/manifests/ai/pi-domain-tools.json`
- `governance/manifests/ai/pi-tool-registry.json`
- `src/personal_knowledge/services/pi_domain_gateway.py`
- `src/personal_knowledge/services/agent_contract.py`
</canonical_refs>

<deferred>
## Deferred Ideas

底仓写 Tool：Phase 56–57；Skills：Phase 58；Kernel 控制面收口：Phase 59。
</deferred>
