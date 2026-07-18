---
phase: 34
status: draft
nyquist: enabled
created: 2026-07-19
---

# Phase 34 Validation

## Gates

1. 同一 service result 经 REST/stdio compact adapter 完全相等。
2. success envelope 始终含 summary/ids/limitations/next_actions/evidence_links/budget。
3. error taxonomy 的八类错误均有稳定 code、retryable 和 allowlisted recovery action。
4. 默认序列化大小不超过 16 KiB，provider body/secret/capability/私密正文匹配数为零。
5. Node 工具只透传 shared compact contract，不再重建错误或 evidence 语义。
6. 固定对话 eval 对工具选择和恢复提示达到 100% expected action match。

## Commands

- `python -m pytest tests/unit/test_agent_compact_contract.py tests/contract/test_agent_ux_interfaces.py -q`
- `node --test apps/personal_data_chatgpt/test/agent-ux-tools.test.mjs`
- Phase 32/33 adjacent regression suites.
