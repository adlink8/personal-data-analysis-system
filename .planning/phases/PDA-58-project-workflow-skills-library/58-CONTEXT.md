# Phase 58: Project Workflow Skills Library — Context

<domain>
## Phase Boundary

把现有稳定个人智能与数据维护流程注册为显式项目 Skills，并建立执行状态机与评测。Skill 只能组合 Phase 55–57 approved Tools，不加载 ambient Skills。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** Skill 是版本化业务流程，不是任意 prompt；必须声明 schema、allowed_tools、状态机、预算、停止和恢复。
- **D-02:** 首批个人智能 Skills：daily brief、knowledge research、decision support、project planning、outcome reflection、system diagnosis。
- **D-03:** 首批数据 Skills：knowledge maintenance、warehouse health、failed-batch recovery、retrieval rebuild、snapshot release。
- **D-04:** Skill selection 为零或一个；collision、checksum drift、expired、profile/tool escalation 时 abstain。
- **D-05:** Skill execution 记录每步 Tool receipt/correlation，resume 从已提交 step 继续，不重复副作用。
- **D-06:** Skill 共识或成功不构成事实/promotion 授权；L3 step 仍停在人类 checkpoint。

### the agent's Discretion

Skill instruction markdown 格式、状态机解释器内部表示和 fixture 文本。
</decisions>

<canonical_refs>
## Canonical References

- `.planning/research/v2.0-pi-capability-os/ARCHITECTURE.md`
- `apps/personal_intelligence_kernel/src/skills/registry.mjs`
- `governance/manifests/ai/pi-skills.json`
- `.planning/phases/PDA-55-unified-capability-registry-and-project-tool-surface/55-CONTEXT.md`
- `.planning/phases/PDA-57-semantic-retrieval-maintenance-and-guarded-release-tools/57-CONTEXT.md`
</canonical_refs>

<deferred>
## Deferred Ideas

Kernel 控制面与运行可观测性：Phase 59；真实 provider/primary：Phase 60。
</deferred>
