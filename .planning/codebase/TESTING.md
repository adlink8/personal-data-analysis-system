# TESTING.md — 测试覆盖状态与验证方式

> 适用范围: `C:\Users\li\Desktop\数据分析`
> 分析日期: 2026-06-17

---

## 1. 当前测试覆盖状态

**项目已有 1 个可执行的 stdlib 自动化测试入口。**

- `tests/test_memory_contracts.py`
  覆盖 core / CLI / REST / MCP 四层记忆查询契约。
- 该测试不依赖外部网络；REST 在测试里临时启动和关闭，不留下后台进程。
- `.gitignore` 已包含 `.pytest_cache/` 和 `.ruff_cache/`，后续可继续扩展到 pytest。

当前自动化覆盖重点是 **Phase 05 记忆层契约**，不是全仓覆盖率。

---

## 2. 手动验证方式

### 2.1 API 健康检查

```powershell
# 启动服务
python 统合模块\脚本\api_server.py

# 健康检查（应返回 200 + JSON）
curl http://127.0.0.1:8000/health

# 数据库+向量库统计概览
curl http://127.0.0.1:8000/stats
```

### 2.2 统一检索层 CLI 验证

```powershell
# 统计概览
python 统合模块\脚本\unified_search.py stats

# 合并层压缩报告
python 统合模块\脚本\unified_search.py merge-stats

# 语义检索冒烟测试
python 统合模块\脚本\unified_search.py semantic "数据库调试" --top-k 3

# 记忆查询 + 证据摘要
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1
```

### 2.3 build_deep_profiles.py 统计输出

```powershell
python 统合模块\脚本\build_deep_profiles.py
# 观察 stdout 中事件计数、分类分布、思考模式分布

python 统合模块\脚本\build_deep_profiles.py --use-merged
# 对比去重前后数量差异，验证合并层生效
```

### 2.4 SQLite 直接查询

```powershell
sqlite3 统合模块\SQLite数据库\personal_system.sqlite
> SELECT COUNT(*) FROM unified_events;
> SELECT COUNT(*) FROM unified_events_rich;
> SELECT COUNT(*) FROM merge_clusters;
> SELECT name FROM sqlite_master WHERE type='table';
```

### 2.5 Dashboard 可视化验证

```powershell
streamlit run 统合模块\脚本\dashboard.py
# 浏览器打开确认图表正常渲染，侧栏状态灯全绿
```

### 2.6 Phase 05 自动化验证

```powershell
python tests\test_memory_contracts.py
python 统合模块\脚本\source_adapters\google_activities.py --limit 2
python 统合模块\脚本\run_pipeline.py --dry-run
python 统合模块\脚本\run_pipeline.py --only 5,6,7,8,9,11,12
python 统合模块\脚本\evaluate_memory_depth.py
```

### 2.7 Phase 06 深层画像验证

```powershell
python 统合模块\脚本\mine_deep_memory_graph.py --dry-run
python 统合模块\脚本\mine_deep_memory_graph.py --output-json
python 统合模块\脚本\build_deep_memory_profile.py
python 统合模块\脚本\build_deep_memory_profile.py --evaluate
```

检查点：

- dry-run 只列出 readiness 通过候选和跳过原因
- `deep_memory_mining.json` 至少含 5 条洞察候选
- `deep_memory_profile.md` 只包含 strong / moderate
- `deep_profile_evaluation.md` 明确给出 shallow vs deep 差异

### 2.8 Phase 07 Agent 对话规范化验证

```powershell
python Agent\结构化数据\脚本\normalize_agent_conversations.py --dry-run --limit-files 5
python Agent\结构化数据\脚本\normalize_agent_conversations.py --write
python 统合模块\脚本\build_conversation_segments.py --dry-run --source Agent --limit 20
python 统合模块\脚本\build_conversation_segments.py --write
python 统合模块\脚本\build_mem0_candidate_memory.py --dry-run --limit 10
python 统合模块\脚本\build_mem0_candidate_memory.py --sample --force-local
python tests\test_agent_conversation_normalization.py
```

检查点：

- `--dry-run --limit-files 5` 输出 Codex 的 raw_type / payload_type 统计，0 解析失败
- `--write` 幂等：连跑两次 v2 表行数完全一致
- `agent_messages` 的 role 只有 user/assistant/developer 三值（无 user_message/agent_message）
- user 消息 turn_id 覆盖率 ≥ 96%
- 每条 `agent_messages` 都能回溯到 `raw_file + line_no`
- mem0 候选 `acceptance_status` 全部为 `candidate`，**不写入** `memory_items`
- mem0 依赖缺失时降级到本地启发式模式，不崩溃，前三波验证不受影响

---

## 3. 幂等验证机制

所有 `build_*` 脚本内置幂等保障，连续运行两次结果应完全一致：

| 验证方式 | 操作 |
|---------|------|
| 连续运行两次同一脚本 | 第二次结果与第一次完全一致，无重复行 |
| 比对行数 | 两次运行后 `SELECT COUNT(*)` 结果相同 |
| `merge_build_meta` 表 | 存储构建时间戳，可核查最后一次运行时间 |

验证命令示例：

```powershell
python 统合模块\脚本\build_merge_layer.py
sqlite3 统合模块\SQLite数据库\personal_system.sqlite "SELECT COUNT(*) FROM merge_clusters;" > count1.txt

python 统合模块\脚本\build_merge_layer.py
sqlite3 统合模块\SQLite数据库\personal_system.sqlite "SELECT COUNT(*) FROM merge_clusters;" > count2.txt

fc count1.txt count2.txt  # 应相同，无差异输出
```

---

## 4. 建议补充的测试点（优先级排序）

### P0 — 纯函数单元测试（`common.py`）

文件: `统合模块/脚本/tests/test_common.py`

```python
test_sha256_text_deterministic()       # 同输入同输出
test_norm_strips_whitespace()          # None → "", 多空格 → 单空格
test_short_truncates_at_limit()        # 超长文本截断
test_event_id_deterministic()          # 三元组 → 确定性 hash
test_extract_domain_empty_url()        # 空串不 crash
test_write_csv_utf8sig_header()        # 生成文件首行 BOM
```

### P1 — 分类规则回归测试（`rules.py`）

文件: `统合模块/脚本/tests/test_rules.py`

```python
test_pure_topic_rules_no_agent_selfhit()
# PURE_TOPIC_RULES 下 "agent/skill/memory" 文本不落入"AI 协作"的前5类
# 这是修复 96.8% 自我命中问题的核心回归测试

test_pure_thinking_rules_distribution()
# 修复后思考模式从单一"工具链驱动"变成三足鼎立

test_tool_names_no_duplicates()
test_pure_topic_default_is_used_for_unmatched()
```

### P2 — 扩展集成冒烟测试

文件: `统合模块/脚本/tests/test_smoke.py`

```python
# 使用临时 SQLite（不污染 personal_system.sqlite）
test_enrich_creates_rich_table()        # enrich 脚本跑完后表存在且非空
test_merge_layer_idempotent()           # 连跑两次 merge，count 不变
test_api_health_returns_200()           # api_server /health 响应正常
```

### P3 — 数据质量 assert

在各 `build_*` 脚本 `main()` 末尾加内联断言（不依赖 pytest）：

```python
# 例: build_merge_layer.py
n = con.execute("SELECT COUNT(*) FROM merge_clusters").fetchone()[0]
assert n > 0, "合并层为空，检查向量库或阈值配置"
```

---

## 5. 推荐测试工具链

```
# 建议添加到 requirements.txt dev 部分
pytest>=8.0
pytest-cov>=6.0
```

运行命令：

```powershell
python -m pytest 统合模块\脚本\tests\ -v
python -m pytest 统合模块\脚本\tests\ --cov=统合模块\脚本 --cov-report=term-missing
```
