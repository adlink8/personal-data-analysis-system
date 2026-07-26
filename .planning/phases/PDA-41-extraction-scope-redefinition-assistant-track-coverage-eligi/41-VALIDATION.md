# Phase 41 Validation: Nyquist 最小充分验证集

**来源:** 41-RESEARCH.md §8「Nyquist Validation Architecture」
**原则:** 每个行为类在最小样本上验证一次，不做重复全量测试。10 个行为类各 1 个代表用例。

---

## 行为类 → 最小用例映射

| # | 行为类 | Nyquist 用例（最小代表） | 层 | 所在 plan / 测试文件 |
|---|---|---|---|---|
| 1 | eligible 等价性 | 同一 fixture canonical DB：inspect 的 current_refs == prepare 的 after_hashes（集合相等，差集=0）——Gate B 噪声的回归锁 | unit（fixture sqlite） | 41-01 / tests/unit/test_knowledge_eligibility.py::test_inspect_prepare_eligible_set_equal |
| 2 | role 解耦 | 同一消息集按 roles=('user',) / ('assistant',) / 全量调用 `compute_eligible_messages`：role 只影响返回哪些行，不改变任何单条消息的 eligible 判定；两子集并集 == 全量结果 | unit | 41-01 / tests/unit/test_knowledge_eligibility.py::test_role_decoupling |
| 3 | assistant prompt schema | 模拟 LLM 返回 JSON：`AssistantExtractionResult` 接受 solution / decision_rationale / technical_conclusion，拒绝 6 个旧 user 类型（ValidationError）；`ExtractionResult` 反之 | unit | 41-02 / tests/unit/test_knowledge_unit_prod_assistant_track.py |
| 4 | quote 回查 | quote 锚 assistant 原文（截断后文本）过 `_evidence_supported` → unit 保留；quote 锚被 12000 截断切掉的部分 → unit 丢弃且 units_dropped_no_evidence ≥1 | unit | 41-02 / tests/unit/test_knowledge_unit_prod_assistant_track.py |
| 5 | run 级单轨 | `prepare_production_delta(track="assistant")` 的 run：manifest prompt_version=='v1_assistant'、artifact 含 "track":"assistant"、run items join canonical_messages.role 全为 'assistant'（无 'user'）；track 与显式 roles 冲突 → ValueError | unit/integration | 41-02 / tests/unit/test_knowledge_unit_prod_assistant_track.py |
| 6 | promote 前缀隔离 | as| run promote 后：v1|/l2|/ku| 的 current 行计数不变，as| staging→current；`TrackConfig` 构造断言 unit_id_prefix 恰好 3 字符（"asst|" 抛 AssertionError） | unit（构造断言）+ 端到端（promote 前后 GROUP BY 对比） | 41-02（断言）/ 41-04 task 4 步骤 6（端到端） |
| 7 | 覆盖矩阵 SQL | fixture DB 造 3 类未覆盖（abstained / terminal_failed / not_queued 各 1）+ 1 个 ku| 豁免行 + 1 个 as| 覆盖行：分类计数各为 1；ku| 计 grandfathered 不计 not_queued；每行守恒 covered + grandfathered + 三分类 == eligible_count | unit | 41-03 / tests/unit/test_coverage_matrix.py |
| 8 | doctor 注册 | 注入含 WARN 行的矩阵：coverage_matrix check 出现在 report、severity=='warn'、ok==True、exit_code==0（矩阵内容不影响退出码）；skip_coverage=True 时 detail=={"skipped": True} | unit（参照 tests/unit/test_doctor_ku.py 既有 probe 注入模式） | 41-03 / tests/unit/test_doctor_ku.py |
| 9 | eval 集加载 | `_load_eval_dataset("frozen-test-assistant")` 解析出 20 条、9 字段齐全、expected_abstain=true 恰 3 条、allowed_unit_types 与旧 6 类型无交集、gold refs 在 canonical DB 存在（后一项可标 integration） | unit | 41-04 / tests/unit/test_knowledge_unit_rag_eval.py |
| 10 | evidence resolver 放宽 | fixture 4 象限：user scope + eligible session → ok；assistant scope + eligible session → ok（不再 ineligible）；assistant scope + ineligible session → ineligible（红线不动）；is_system=1 → ineligible | unit | 41-04 / tests/unit/test_evidence_resolver_scope.py |

plan-checker 修订新增的两个行为（非 Nyquist 新行为类，随既有类同文件覆盖）：unit_type CHECK 表重建（knowledge_units + canonical_knowledge_units）由 41-02 task 0 的迁移验收（行数守恒、foreign_key_check=0、幂等 no_op、solution INSERT 成功）覆盖，先于用例 3-6 执行；确认信号修饰（D-03）由 41-02 task 6 单测覆盖（adopted +0.05 / corrected -0.2 封顶封底、unit 不被 gate 丢弃、user 轨零回归），归并在用例 4 同文件 tests/unit/test_knowledge_unit_prod_assistant_track.py。

---

## 集成 / 端到端（手动门，付费步骤需人工批准）

对应 41-04 task 4 的 10 步演练，关键点：

1. `pk-ku inspect`（eligible 统一后首次）delta 突增 = 口径修正（R6），不是缺陷。
2. bootstrap_assistant_watermark --write → `pk-ku prepare --roles assistant --track assistant`：extract_item_count 为增量而非 ~73k 全量（R4 闭环）。
3. `pk-ku extract --run <ir_*> --max-items 20`（**Vertex 付费，需批准**）→ `pk-ku status` 验收 succeeded/abstained/terminal_failed 分布，role_mismatch=0。
4. `pk-ku extract-gate`（含对称 Gate 8）→ canonical --write → publish --write → vector --write。
5. assistant eval 集跑 evaluate_candidate：Recall@5 基线记录到 var/reports/analysis/ai_context/ku_canary_gate_assistant_track_<date>.json，**首轮不预设阈值**（校准用途）。
6. `pk-ku canary … --strict` PASS → `promote --require-eval-pass` → `watermark --advance --track assistant --from-canonical --write`（committed_assistant，committed 不变）。
7. `pk-ku doctor --skip-ports`：coverage_matrix check 出现、as| pass 族显形、整体 exit 0。

## 不做

- 不重抽 ku| 世代（D-04）；不拆 user 轨 speaker gate；不动 L2 prompt 疆域/窗口（deferred）；确认信号的自动 supersede / lifecycle 自动路由（41-02 task 6 已承接信号检测 + confidence 修饰，lifecycle 修正留增量）；不动会话去重键（Phase 42）。
