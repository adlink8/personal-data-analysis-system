# v2.0 Pi Personal Intelligence Capability OS — Architecture Summary

**Decided:** 2026-08-05  
**Status:** Approved input for GSD Phase 55–60 planning

## Outcome

项目从“Pi 只负责上层模型编排”扩展为“Pi 可编排并执行受控底仓操作的个人智能能力操作系统”。现有项目功能注册为 Domain Tools，稳定业务流程注册为 Skills；Pi SDK Kernel 是唯一 AI 协调内核并消费统一能力 SSOT。Python 仍是事实、事务、一致性和正式生命周期权威。

## Layer Contract

| Layer | Responsibility | Authority boundary |
|---|---|---|
| Project Capability Registry | Tool/Skill/Event schema、版本、权限、隐私、预算和回执 SSOT | 任何消费者不得自行扩展能力 |
| Pi SDK Kernel | 常驻任务、Session、事件、模型、Skill 选择和 Tool 编排 | production profile；无 ambient 资源和任意系统能力 |
| Python Domain/Data Authority | 参数校验、事务、canonical/evidence/watermark/eval/promotion/rollback | 独占底仓规则和最终提交语义 |
| Cockpit/Wiki/MCP | 用户观察、搜索、控制、确认和证据下钻 | 不直连数据库，不形成影子 SSOT |

## Tool Principle

- 项目能力工具化，不把内部 Python 函数或脚本逐个暴露。
- Tool 是稳定、原子、schema-validated、idempotent、bounded 的领域能力。
- Read Tool 可自动执行；Candidate/derived write 可按策略执行；canonical append、promotion、active pointer 和 rollback 使用 exact preview 与明确确认。
- 禁止任意 SQL、任意文件路径、任意 Python callable、直接 DELETE/TRUNCATE、未批准 schema migration 和 gate bypass。

## Skill Principle

- Skill 是带版本/checksum、purpose、输入输出 schema、allowed_tools、状态机、预算、停止条件和验收规则的项目流程。
- 首批 Skills：personal daily brief、knowledge research、decision support、project planning、outcome reflection、knowledge maintenance、warehouse health、failed batch recovery、retrieval rebuild、snapshot release、system diagnosis。
- Skill 输出仍是 Candidate 或带回执的确定性操作结果；两个 Agent 达成一致也不能自动把生成内容提升为事实。

## Data-plane Protocol

所有正式底仓操作固定为：

`plan → dry-run → exact preview/checksum → confirm or approved policy → idempotent execute → invariant/fingerprint verify → append-only receipt → compensate/rollback`

权限等级：

- L0：统计、血缘、状态和只读检查，可自动。
- L1：临时计算、隔离区和 Candidate，可自动。
- L2：可重建 S/R/A 制品，满足策略后可自动。
- L3：canonical append/correction、promotion、active snapshot、rollback，必须明确确认。
- L4：任意 SQL、破坏性删除和未批准 schema 变更，禁止。

## Activation Boundary

本机 Pi Agent、Local Pi RPC Adapter、双 Agent handoff 和第二套 operator runtime 均不属于目标架构。Phase 48–54 的安全、Kernel、Task、Provider、Cockpit 和 rollback 基础继续复用。Phase 53 的真实 paired baseline 仍为 `revise`，Phase 54 primary 仍不得激活。Phase 55–59 完成后，Phase 60 必须重新执行 capability/data/Skill/control-plane UAT，并且只有 Phase 53 accepted baseline 与用户明确授权同时成立时才能进入最终 primary。
