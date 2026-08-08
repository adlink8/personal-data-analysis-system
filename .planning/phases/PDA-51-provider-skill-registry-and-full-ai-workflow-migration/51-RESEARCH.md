# Phase 51 Research — Provider, Skills and Migration

## Findings

- Existing Python `ProviderRequest/ProviderResult/ProviderTelemetry` are valuable project-owned contracts. Pi should implement them through Domain Gateway receipts rather than replacing downstream schemas.
- `CodexCliProvider` and OpenAI-compatible paths currently own auth/error/usage behavior; migration needs a route inventory before any deletion or disabling.
- Pi Skill discovery is ambient by default and auto-selection is not guaranteed. Production needs explicit registry plus deterministic selector policy/tests.
- “Full migration” means every model side effect receives one Pi task/event/session identity, while deterministic readers and non-AI rules remain Python-native.

## Validation Architecture

- Static inventory gate: every model/CLI/provider callsite classified as migrated, deterministic-non-AI, test-only or rollback-only.
- Provider replay parity: same request → schema-equivalent result/telemetry and safe errors.
- Skill fixtures: exact selection, no collision, checksum drift rejection, no ambient load.
- Zero parallel control: primary-disabled phase can shadow, but one request cannot invoke both model paths outside explicit comparison harness.
