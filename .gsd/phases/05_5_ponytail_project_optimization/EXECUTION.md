# Phase 05.5 Execution

## Result

已完成一次最小 Ponytail 瘦身，范围控制在重复逻辑收口、退役代码删除、未使用残留清理和依赖口径同步；未新增业务能力，也未改变 Phase 06 输入契约。

## Changes Applied

### 1. 收口重复分类查询逻辑

- 在 `统合模块/脚本/unified_search.py` 新增 `list_categories()`。
- `统合模块/脚本/api_server.py` 与 `统合模块/脚本/mcp_server.py` 改为统一调用该后端函数。
- 删除两处重复 SQL 实现，避免 HTTP/MCP 两层继续漂移。

### 2. 删除退役 embedding 实现

- 删除 `统合模块/脚本/ollama_embed.py`。
- 当前生产路径早已切到 `local_embed.py`，原文件只剩历史兼容价值，代码与文档长期并存会制造误导。

### 3. 清理未使用残留

- 删除 `统合模块/脚本/api_server.py` 中未使用的 `CORS_HEADER`。
- 删除 `统合模块/脚本/dashboard.py` 中未使用的 `defaultdict` import。
- 删除根目录 0 字节杂物文件 `6}★`。

### 4. 依赖与文档同步

- 从 `requirements.txt` 删除未使用的 `scikit-learn`。
- 更新 `README.md`、`.planning/codebase/STACK.md`、`.planning/codebase/STRUCTURE.md`，去掉已删除或已失效口径。

## What Was Kept

### `source_adapters/`

本轮未删除。

原因：
- 它虽然尚未接入主 pipeline，但已经被 README、测试文档和外部对齐文档引用。
- 当前 Phase 05.5 目标是最小瘦身，不值得为删除一个旁路样例再扩大文档与说明面。
- 它不影响运行路径，也不增加线上复杂度，收益低于删除 `ollama_embed.py`。

### 记忆层多个 builder 的 schema 重复

本轮未合并。

原因：
- 可以继续收缩，但涉及 `build_memory_store.py`、`build_capability_memory.py`、`build_context_memory.py`、`build_preference_memory.py` 多文件共享契约。
- Phase 05.5 明确不做大型重构；这类提取更适合单独的小 phase，并带更完整回归验证。

## Verification

实际执行：

```powershell
python tests\test_memory_contracts.py
python 统合模块\脚本\run_pipeline.py --dry-run
python 统合模块\脚本\unified_search.py memory --subject Codex --neighbors 1
python 统合模块\脚本\evaluate_memory_depth.py
git diff --check
```

结果：

- `tests\test_memory_contracts.py`：4/4 通过
- `run_pipeline.py --dry-run`：12 步管道顺序正常
- `unified_search.py memory --subject Codex --neighbors 1`：正常返回记忆详情、关系和邻居
- `evaluate_memory_depth.py`：成功生成 `统合模块/分析数据/ai_context/memory_depth_readiness.md`
- `git diff --check`：只有 CRLF warning，无内容格式错误

## Net Effect

- 清理了一个真实重复源：`list_categories` 不再在 API/MCP 两层各维护一份
- 删除了一个真实退役脚本：`ollama_embed.py`
- 删除了 1 个未使用依赖和若干未使用残留
- Phase 05 contract tests 未破坏
- Phase 06 依赖的 `memory_depth_readiness.md` 仍可生成
