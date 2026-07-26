# 41-04 端到端演练执行笔记（count-only）

**执行时间：** 2026-07-26
**执行边界：** 按主流程约束，演练跑到付费门 / 写操作门前为止——付费 LLM 步骤（assistant 轨真实 prepare/extract）、真实 promote、迁移脚本 `--write` 一律未执行。

---

## 已执行步骤（全部只读或 dry-run）

### Step 1 — `pk-ku inspect`（41-01 切换后首次记录）

```
source_changed:     False
current_checksum:   87e24e2aa2e9f167989b4e4724ae9cd3
no_op:              True
affected_evidence:  0   new_refs: 0   deleted_refs: 0
affected_subjects:  0   deprecated: 0
exit: 0
```

**解读（R6）：** 本演练未观测到口径修正性 delta 突增——41-01/41-02/41-03 执行期间的 inspect 已吸收口径切换，当前 source checksum 与已提交状态一致（no_op）。这本身验证了 eligible 口径唯一化后 inspect 的稳定性：连续两次 inspect 不再因口径差产生伪 delta。

### Step 2 — 迁移脚本 dry-run（对真实库，未 --write）

**`python tools/migrations/rebuild_knowledge_unit_type_check.py`（dry-run，exit 0）：**
- `knowledge_units`：current CHECK 6 类 → new CHECK 9 类（+solution/decision_rationale/technical_conclusion），需重建 4 个索引（idx_ku_run/status/subject/type）
- `canonical_knowledge_units`（32,599 行）：同样 6→9 类，需重建 2 个索引（idx_cku_status/subject）

**`python tools/migrations/bootstrap_assistant_watermark.py`（dry-run，exit 0）：**
- 将写入 `knowledge_source_watermark` key=`committed_assistant`，value=`87e24e2aa2e9...`（= 当前 committed）
- 估算：bootstrap 后首次 `prepare --track assistant` 增量队列约 **19,702** 条 assistant 消息

### 当前真实库状态（只读核实）

- `knowledge_source_watermark` 现有 key：仅 `committed`（`87e24e2aa2e9`）——`committed_assistant` 尚未写入（等主流程 `--write`）
- `knowledge_units.unit_type` CHECK 仍为旧 6 类（等主流程 `--write`）

---

## 演练停止点

**停在 Step 3（prepare）之前。** prepare 虽不调 LLM，但会写 delta inventory 队列（knowledge_delta_inventories/knowledge_delta_items），属"真实 prepare"，按主流程约束留给统一执行。Step 4（extract）起为付费 LLM 步骤。

---

## 待主流程执行的付费 / 写操作命令清单

按 runbook 顺序（对应 PLAN task 4 步骤 2–9）：

```bash
# 0. 前置迁移（一次性，--write）
python tools/migrations/rebuild_knowledge_unit_type_check.py --write
python tools/migrations/bootstrap_assistant_watermark.py --write
#   验收：SELECT key FROM knowledge_source_watermark 同时存在 committed 与 committed_assistant

# 1. prepare（写 delta 队列；artifact 验收 extract_item_count 为增量级、active_changed=false）
pk-ku prepare --model gemini-3.5-flash-lite --provider vertex_google \
  --roles assistant --track assistant
#   注意：dry-run 估算全量增量 ~19,702 条；如需先 pilot，可加 --max-extract-items 控制队列

# 2. extract pilot（付费 LLM，20 条 smoke）
pk-ku extract --run <ir_*> --model gemini-3.5-flash-lite --max-items 20
pk-ku status
#   验收：记录 succeeded/abstained/terminal_failed/units_dropped_no_evidence 分布；role_mismatch=0

# 3. gate → canonical → publish → vector（含对称 Gate 8）
pk-ku extract-gate
pk-ku canonical --write
pk-ku publish --write
pk-ku vector --write

# 4. promote 前缀隔离验收（执行 promote 前后各跑一次）
#    SELECT substr(unit_id,1,3), status, COUNT(*) FROM knowledge_units GROUP BY 1,2
#    验收：v1|/l2|/ku| 的 current 计数不变，as| 由 staging→current

# 5. assistant eval 基线（首轮只记录不设阈值）
python -m personal_knowledge.evaluation.knowledge.evaluate_knowledge_unit_rag \
  --dataset frozen-test-assistant --candidate latest \
  --report var/reports/analysis/ai_context/ku_canary_gate_assistant_track_<date>.json
#   验收：报告含 Recall@5 数值；同时记录 4-gram 相似度分布观察，
#   给出 MERGE_SIMILARITY_THRESHOLD 是否需调的结论（R5，只出结论不改值）

# 6. canary → promote → watermark（只动 committed_assistant）
pk-ku canary … --strict
pk-ku promote --require-eval-pass
pk-ku watermark --advance --track assistant --from-canonical --write
#   验收：committed（user 轨）值不被改变

# 7. doctor 终验
pk-ku doctor --skip-ports
#   验收：exit 0；coverage_matrix check 出现且 as| pass 族在矩阵中显形
```

## 本轮无法验收、移交主流程的 PLAN 验收项

- Step 6 promote 前后 SQL 对比（v1|/l2|/ku| current 计数差为 0）
- Step 8 后 watermark 双 key 分立且 committed 不变
- eval 报告 JSON（含 Recall@5）落盘
- doctor coverage 矩阵含 as| 覆盖行（as| units 尚不存在，矩阵当前自然无此行）

## merge 阈值基线记录（PLAN step 7 部分）

4-gram 相似度分布观察依赖 as| units 产出，本轮无产出，观察与 `MERGE_SIMILARITY_THRESHOLD` 调值结论随主流程 pilot 一并进行（R5：只出结论不改值）。
