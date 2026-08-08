# Phase 51: Provider, Skill Registry and Full AI Workflow Migration — Context

<domain>
## Phase Boundary

统一 Provider/model adapter、受控 Skill registry，并把仓库内所有真实 AI 调用入口迁移到 Pi Kernel。迁移完成后 legacy 只能由显式 rollback adapter 调用；本阶段仍不把 Pi 切为 primary。
</domain>

<decisions>
## Implementation Decisions

- **D-01:** Provider auth 只由 supervisor/environment 注入到 Kernel；禁止读取 Codex/浏览器/宿主 Pi auth 文件。
- **D-02:** model route 必含 provider、model、timeout、max tokens、cost ceiling、retry policy 和 allowed purpose；未知 route 拒绝。
- **D-03:** Skill registry 只加载仓库内签名/校验和 allowlist，选择结果绑定 skill_id/version/checksum 和 evidence contract。
- **D-04:** 迁移清单覆盖 structured analysis、guarded orchestration generation、KU/summary extraction 和其他 `Provider.generate`/CLI 模型调用；不得遗漏并行主入口。
- **D-05:** legacy adapter 保留 exact input/output compatibility，但只能在 `legacy` 或 rollback mode 使用。
- **D-06:** migration parity 使用 replay/synthetic 先闭合；真实 Provider 基线和付费授权延至 Phase 53。

### the agent's Discretion

- Provider adapter 内部类名、Skill manifest 排版和迁移批次内顺序。
</decisions>

<canonical_refs>
## Canonical References

- `src/personal_knowledge/intelligence/analysis/providers.py` — ProviderRequest/Result/Telemetry 与现有 adapters。
- `src/personal_knowledge/services/orchestration_service.py` — generation runner seam。
- `src/personal_knowledge/application/knowledge/build_knowledge_units_prod.py` — extraction model path。
- `.planning/spikes/pi-frontier-controls/006-provider-auth-and-budget/README.md` — budget/auth prototype。
- `.planning/spikes/pi-embedded-personal-kernel/003-skill-artifact-isolation/README.md` — deterministic Skill gate。
</canonical_refs>
