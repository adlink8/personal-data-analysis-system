---
phase: PDA-43-l2-scope-redefinition-cross-turn-state-ownership-and-increme
plan: 04
status: complete
---

# 43-04 Summary

完成 L1 v2 接线：新增 `v2_main.md`、`v2_assistant.md`，增加 `--prompt-version v2|v2_assistant`，manifest 记录实际版本；v1 默认行为保留。v2 按 `db_path` 构建 current canonical subject index，先做最长 subject 优先的确定性扫描，再把注入块放在既有 LLM 输入之前。

提交层只接受注入清单内的 `duplicate_of`，非法引用丢弃并计数；状态清单命中时强制 `lifecycle='candidate'`，不接受模型自报 candidate。新增统计键：`invalid_duplicate_of`、`units_downgraded_candidate`、`injection_embed_unavailable`。

验证：L1/assistant/evidence 回归与 `tests/integration/test_l2g01_dedup_gate.py` 通过。
