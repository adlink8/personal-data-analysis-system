# Phase 06 Execution

## Result

Phase 06 已完成。

本阶段把 Phase 05 的浅层记忆图谱提升为旁路深挖层：只消费 readiness gate 通过的主题，产出带证据链、时间跨度、关系强度和反例约束的深层洞察与可注入 profile，且**不回写长期 memory store**。

## Delivered

### Wave 1 / 2: 深挖输入层 + 模式挖掘

新增：

- `统合模块/脚本/mine_deep_memory_graph.py`

能力：

- 读取 `memory_depth_readiness.md`
- 只加载 readiness 通过的 3 个候选主题
- 跳过 17 个浅层/阻塞主题
- 从 `memory_items` / `memory_links` / `memory_relations` 回溯证据
- 计算：
  - `evidence_count`
  - `time_span_days`
  - `recurrence_count`
  - `relation_count`
  - `relation_strength_avg`
  - `contradiction_count`
- 生成 6 条深层洞察候选

输出：

- `统合模块/分析数据/ai_context/deep_memory_mining.json`
- `统合模块/分析数据/ai_context/deep_memory_mining.md`

### Wave 3 / 4: 深层 profile 构建 + 对比评估

新增：

- `统合模块/脚本/build_deep_memory_profile.py`

能力：

- 把 deep mining JSON 转成 include / review / exclude 三类
- 只把 `strong` / `moderate` 洞察写入最终 profile
- 生成浅层 `person_profile_v2.md` 与深层 profile 的对比评估

输出：

- `统合模块/分析数据/ai_context/deep_memory_insights.json`
- `统合模块/分析数据/ai_context/deep_memory_insights.md`
- `统合模块/分析数据/ai_context/deep_memory_profile.md`
- `统合模块/分析数据/ai_context/deep_profile_evaluation.md`

### Wave 5: 文档

已更新：

- `README.md`
- `统合模块/README.md`
- `.planning/codebase/ARCHITECTURE.md`
- `.planning/codebase/TESTING.md`

补充内容：

- `person_profile_v2.md` 与 `deep_memory_profile.md` 的使用边界
- Phase 06 的复现命令
- Phase 06 不回写 `memory_items`

## Actual Insight Output

本次实际生成的 include 洞察共 6 条：

1. `Claude 从主力工具转入衰减阶段` (`decaying_interest`, strong)
2. `Claude 使用衰减但 workflow 关联仍在` (`contradiction_or_tension`, moderate)
3. `Obsidian 同时是环境事实和项目对象` (`project_cluster`, moderate)
4. `Obsidian 呈现跨类型稳定偏好` (`stable_preference`, moderate)
5. `windows-powershell-escaping 长期归属于 开发技术栈 主题簇` (`project_cluster`, strong)
6. `windows-powershell-escaping 体现开发能力形成路径` (`capability_path`, strong)

## Verification

实际执行：

```powershell
python tests\test_memory_contracts.py
python 统合模块\脚本\mine_deep_memory_graph.py --dry-run
python 统合模块\脚本\mine_deep_memory_graph.py --output-json
python 统合模块\脚本\build_deep_memory_profile.py
python 统合模块\脚本\build_deep_memory_profile.py --evaluate
git diff --check
```

结果：

- `tests\test_memory_contracts.py`：4/4 通过
- `mine_deep_memory_graph.py --dry-run`：只列出 3 个 readiness 通过主题，且打印跳过原因
- `mine_deep_memory_graph.py --output-json`：成功生成 mining JSON / Markdown
- `build_deep_memory_profile.py`：成功生成 insights JSON / Markdown + profile
- `build_deep_memory_profile.py --evaluate`：成功生成 deep profile evaluation
- `git diff --check`：只有 CRLF warning，无内容格式错误

## Acceptance Check

- 深层洞察有证据链、时间跨度、关系强度和反例检查：满足
- 输出区分 `strong/moderate/weak/unsupported`：满足
- `deep_memory_profile.md` 比浅层 profile 多出 pattern / evolution / contradiction：满足
- 不可靠洞察不进入最终可注入 profile：满足（当前 include 为 6，review/exclude 为 0）
- 本地优先，不引入外部托管服务：满足

## Notes

- 本轮没有把深层洞察回写到 `memory_items`；这是有意为之。
- 目前 deep mining 仍是规则化轻量实现，不是完整 GraphRAG。
- 若后续要继续 Phase 07，更合理的方向是把深层 profile 接入 MCP/REST 的消费层，而不是先扩大挖掘框架。
