# Phase 58 Research

## Findings

- 当前 SkillRegistry 只验证 manifest，`pi-skills.json` 为空，尚无执行状态机。
- 最安全模式是 repo-owned manifest + instruction checksum + declarative step graph；不复用全局 `~/.pi` Skills。
- 个人智能 Skills 与数据维护 Skills 的失败/确认边界不同，应使用同一引擎、不同 profile/policy。
- Tool-sequence correctness、forbidden calls、resume/replay 比自然语言“好不好”更适合作为首要评测。

## Validation Architecture

- 每个 Skill 至少一个 success、abstain、tool-failure、resume 和 forbidden-step fixture。
- 状态机属性测试：only declared tools、bounded loops、no skipped checkpoint、at-most-once side effect。
- 10–20 个产品场景 rubric，人工复核高风险/歧义输出。
