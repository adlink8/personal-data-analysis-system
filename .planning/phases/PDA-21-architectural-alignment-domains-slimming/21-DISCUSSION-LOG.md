# Phase 21: Architectural Alignment - Domains Slimming - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-14
**Phase:** 21-Architectural Alignment - Domains Slimming
**Areas discussed:** 中心节点处理(LLM 原语), 迁移节奏, 死代码与兼容, 验收标准

---

## 中心节点处理(build_conversation_summary.py)

| Option | Description | Selected |
|--------|-------------|----------|
| 拆分:LLM helper→core/, build 逻辑→application/conversation/ | 按 plan 原方案,LLM 调用原语下沉 core/llm.py,build 编排移 application/conversation/,6 个 peer 改 import。最彻底但改动面最大 | ✓ |
| 整文件移到 application/conversation/,留 facade | 整文件移动+原位 re-export shim,peer 零改动,但留 facade 债务 | |
| 整文件移到 core/llm_assist.py,留 facade | 承认其本质是 LLM helper,整体下沉,语义最准但 build 逻辑进 core 超标 | |

**User's choice:** 拆分(LLM helper→core/, build 逻辑→application/conversation/)
**Notes:** 选最彻底方案,与「可控破坏」偏好一致——一次性做对,不留 facade 债务给后续清理。

---

## 迁移节奏

| Option | Description | Selected |
|--------|-------------|----------|
| 按子域分组批次迁移 | conversation→graph→knowledge→memory 四批,每批迁完跑测试。4 批可独立验证/回滚 | ✓ |
| 按类型批量迁移 | eval/compare 一批(14 个)+ build 一批(29 个)。批次少但单批改动大、回滚粒度粗 | |

**User's choice:** 按子域分组批次迁移
**Notes:** 节奏稳,中间状态可测。conversation 先迁因被依赖最多。

---

## 死代码与向后兼容

| Option | Description | Selected |
|--------|-------------|----------|
| 直接删死代码 + 留 re-export facade | v2 直接删,迁移脚本留 facade(保 30 天)。与阶段一 facade 策略一致 | ✓ |
| 删死代码 + 不留 facade(硬切) | v2 删,caller 同步改 import。最干净但漏改即 break | |
| 留死代码 + 留 facade(最保守) | v2 不删,全留 facade。零风险但留更多债务 | |

**User's choice:** 直接删死代码 + 留 re-export facade
**Notes:** v2 已确认死代码(src/tests 0 引用 + import 路径写错),安全删。迁移脚本留 facade 保 caller 零改动,与阶段一策略对齐。

---

## 验收标准

| Option | Description | Selected |
|--------|-------------|----------|
| 全量测试 + governance preflight + 服务健康 | 三重门禁:pytest(允许 17 已知 fail)+ preflight --ci + REST/MCP 健康端点 | ✓ |
| 只要求全量测试通过 | 最轻,但 governance 分层规则可能因移动报违例 | |
| 三重门禁 + domains/ LOC 硬指标 | 额外要求 domains <5000 LOC。量化明确但可能卡交付 | |

**User's choice:** 全量测试 + governance preflight + 服务健康
**Notes:** 与阶段一验收标准一致,避免 LOC 硬指标卡住。

---

## the agent's Discretion

- core/llm.py 的拆分边界(LLM 原语 vs build 编排)— plan 阶段据代码定
- evaluation/{子域}/ 子目录结构 — plan 据文件数定
- retrieval 层 4 个 eval/compare 脚本的 evaluation/ 归属 — plan 定

## Deferred Ideas

- 消除 retrieval/memory.py 的 3 处 domains.graph lazy import(阶段一隔离的违例)— domains 重组稳定后单独评估
- 删 .bak-phase20 6GB 备份 — 阶段 3,等 2026-08-13 窗口
- domains/ LOC 硬指标 — 未选,避免卡交付
