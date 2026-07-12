---
phase: 13
name: codebase_refactoring
title: 代码库基础层重构 — 消除重复、统一路径、提取公共层
status: 完成 (Wave 4-5 verified 2026-07-10)
created: 2026-07-05
depends_on:
  - .gsd/phases/12_data_access_interfaces/VERIFICATION_2026-07-03.md
autonomous: true
---

# Phase 13: 代码库基础层重构

## Objective

消除 `integration/scripts/` 70+ 个脚本中因历史积累形成的结构性重复：工具函数多处重复定义、分类规则未统一、路径解析方式不一致。

本 Phase **不修改任何业务逻辑**，只做无歧义的"提取公共层 + 迁移导入"。

## Non-goals

- 不重构 memory pipeline 逻辑
- 不修改数据库 schema
- 不重命名对外 CLI / MCP 接口
- 不删除任何脚本

---

## 权威来源文件（只读，不能改内容）

以下两个文件是本 Phase 的"迁移目标"，所有脚本的函数/常量应从这里导入：

**`integration/scripts/common.py`** — 纯工具函数（无副作用）：
- `sha256_text(text: str) -> str`
- `norm(value: object) -> str`
- `short(value: object, limit: int = 2000) -> str`
- `event_id(source: str, source_table: str, source_id: object) -> str`
- `entity_id(entity_type: str, name: str) -> str`
- `extract_domain(url: str) -> str`
- `extract_tools(text: str, tool_names: list[str]) -> list[str]`  ← **注意：需传入 tool_names 参数**
- `write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None`
- `write_json(path: Path, data: object) -> None`
- `ensure_dirs(paths: list[Path]) -> None`

**`integration/scripts/rules.py`** — 分类规则与工具名：
- `TOPIC_RULES: list[tuple]`
- `TOOL_NAMES: list[str]`
- `THINKING_RULES: list[tuple]`
- `PURE_TOPIC_RULES: list[tuple]`

---

## 当前执行状态（2026-07-05）

| Wave | 内容 | 状态 |
|------|------|------|
| Wave 1 | 扫描报告 | ✅ 完成 — 产物：`integration/analysis/refactoring/phase13_verification.md` |
| Wave 2 | 创建 core/project_paths.py | ✅ 完成 — 文件已存在 |
| Wave 3 | 迁移 build_integrated_system.py 和 build_deep_profiles.py | ✅ 完成 |
| Wave 4 | 批量迁移其余命中脚本 | ✅ 完成 (2026-07-10) — 无可迁移残留 |
| Wave 5 | 全链路验证 | ✅ 完成 (2026-07-10) |

### Wave 4 实际执行结果（2026-07-10）

扫描 11 个目标文件，发现 PLAN 列出的重复定义**已无"可安全迁移"残留**：

- `build_memory_store.py` / `build_capability_memory.py` / `build_context_memory.py` / `build_preference_memory.py` / `build_memory_graph.py` / `mine_deep_memory_graph.py` / `build_deep_memory_profile.py` — 已正确 `from common/rules import`，无本地重复定义。
- `enrich_unified_events.py` — 已 `import common` / `import rules`，用 `common.short`/`common.sha256_text`/`rules.PURE_TOPIC_RULES`。
- `build_triple_store.py` / `build_vector_store.py` / `build_conversation_graph.py` — 不使用 common/rules 符号，无需迁移。

**ESCALATE（有意本地特化，不迁移）**——5 处同名函数签名/行为与权威版本不同，按 Escalation gate 保留：

| 文件 | 函数 | 差异 |
|------|------|------|
| `visualize_conversation_graph.py` | `short` | `limit=180`，加"…"省略号，不调 norm — 纯本地版 |
| `build_deep_profiles.py` | `write_csv` | `fieldnames` 默认 `sorted({...})`（所有行 key 并集排序）vs common 的 `list(rows[0].keys())` — deep_profiles 需并集 key 避免丢列 |
| `build_deep_profiles.py` | `write_json` | 行为等价但实现不同，按严格逐行规则 ESCALATE |
| `build_deep_profiles.py` | `ensure_dirs` | 无参版本，创建特定项目目录（签名不同） |
| `build_integrated_system.py` | `ensure_dirs` | 无参版本，创建 INPUT_INDEX/STRUCTURED 等（签名不同） |

`ensure_dirs()` 无参与 `ensure_dirs(paths)` 是不同契约，不存在遮蔽风险。

### Wave 5 验证结果（2026-07-10）

- [1] `sha256_text` / `norm` / `event_id` / `entity_id` / `extract_tools` / `extract_domain` — 仅 common.py 定义 ✓
- [2] `TOPIC_RULES` / `TOOL_NAMES` / `THINKING_RULES` / `PURE_TOPIC_RULES` — 仅 rules.py 定义 ✓
- [3] `extract_tools` 所有调用点均传 `tool_names` ✓
- [4] 69 个 .py 文件 py_compile 全部 PASS ✓
- [5] `pytest tests/test_memory_contracts.py` — 4 passed ✓
- [6] `run_pipeline.py --dry-run` — 12 步全部正确解析 ✓

### Wave 3 已迁移详情

**`build_integrated_system.py`**（全量迁移完成）：
- 删除：`sha256_text`, `norm`, `short`, `event_id`, `entity_id`, `extract_domain`, `extract_tools`, `write_csv`（本地定义）
- 删除：`TOPIC_RULES`, `TOOL_NAMES`（本地常量）
- 删除：`import csv`, `import hashlib`, `from urllib.parse import urlparse`（不再需要）
- 修复：`ROOT = Path.cwd().resolve()` → `ROOT = Path(__file__).resolve().parents[2]`
- 新增：`from common import sha256_text, norm, short, event_id, entity_id, extract_domain, extract_tools, write_csv`
- 新增：`from rules import TOOL_NAMES, TOPIC_RULES`
- 更新调用点：`extract_tools(text)` → `extract_tools(text, TOOL_NAMES)`

**`build_deep_profiles.py`**（部分迁移完成）：
- 删除：本地 `def norm()` 定义
- 新增：`from common import norm`

---

## Wave 2 产物：core/project_paths.py

文件路径：`integration/scripts/core/project_paths.py`

**完整内容**（如文件不存在，按此创建）：

```python
"""统一项目路径常量。

从 __file__ 派生，不依赖运行目录 (Path.cwd())。
所有脚本应从这里 import，而不是各自用 parents[N] 魔法数字。
"""
from __future__ import annotations
from pathlib import Path

# 文件位于 integration/scripts/core/project_paths.py
# parents[0] = core/
# parents[1] = scripts/
# parents[2] = integration/
# parents[3] = 项目根目录
ROOT = Path(__file__).resolve().parents[3]

INTEGRATION_DIR = ROOT / "integration"
DB_DIR = INTEGRATION_DIR / "db"
SCRIPTS_DIR = INTEGRATION_DIR / "scripts"
ANALYSIS_DIR = INTEGRATION_DIR / "analysis"
AI_CONTEXT_DIR = ANALYSIS_DIR / "ai_context"

# 常用数据库路径
UNIFIED_DB = DB_DIR / "personal_system.sqlite"
CONV_GRAPH_DB = DB_DIR / "conversation_graph.duckdb"

# 源数据库
GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
GPT_DB = ROOT / "GPT" / "structured" / "db" / "chatgpt_data.db"
AGENT_DB = ROOT / "Agent" / "structured" / "db" / "agent_data.sqlite"

SOURCE_DBS = {
    "Google": GOOGLE_DB,
    "GPT": GPT_DB,
    "Agent": AGENT_DB,
}
```

同时确认 `integration/scripts/core/__init__.py` 存在（空文件即可）。

---

## Wave 4: 批量迁移其余脚本（已完成 — 无可迁移残留，详见上方 Wave 4 实际执行结果）

### 操作规则

对每个目标文件，执行以下固定步骤：

1. **检查**：在文件中搜索下方"需迁移的标识符"是否存在本地定义（`def xxx` 或 `xxx =`）
2. **对比**：将本地定义与 `common.py` / `rules.py` 中的权威版本逐行比对
3. **迁移（仅当完全一致时）**：
   - 在文件顶部 `sys.path.insert` 行之后（或 `from pathlib import Path` 之后）添加导入
   - 删除本地重复定义
4. **跳过（存在差异时）**：输出 `ESCALATE: <文件名> <标识符名>: <差异说明>`，不做任何修改
5. **验证**：运行 `python -m py_compile <文件路径>`

### sys.path 注入模板

所有脚本如果没有以下两行，需在导入共享模块前加上：

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
```

### common.py 导入模板

```python
from common import sha256_text, norm, short, event_id, entity_id  # 按实际使用情况选择
```

**注意**：`extract_tools` 的签名变化：
- 旧签名：`extract_tools(text)` — 闭包捕获 TOOL_NAMES
- 新签名：`extract_tools(text, tool_names)` — 需显式传入
- 调用点必须同步改为 `extract_tools(text, TOOL_NAMES)`

### rules.py 导入模板

```python
from rules import TOPIC_RULES, TOOL_NAMES  # 按实际使用情况选择
```

### 目标文件清单（根据 Wave 1 扫描报告，共 ~25 个，优先级排序）

**高优先级（被其他脚本 import 或入口脚本）**：

| 文件 | 疑似重复的标识符 |
|------|----------------|
| `integration/scripts/build_memory_store.py` | sha256_text, norm, event_id, entity_id |
| `integration/scripts/build_capability_memory.py` | sha256_text, norm, event_id |
| `integration/scripts/build_context_memory.py` | sha256_text, norm, event_id |
| `integration/scripts/build_preference_memory.py` | sha256_text, norm, event_id |
| `integration/scripts/build_memory_graph.py` | sha256_text, norm, event_id, entity_id |
| `integration/scripts/enrich_unified_events.py` | norm, short（如有本地定义） |

**中优先级（独立脚本）**：

| 文件 | 疑似重复的标识符 |
|------|----------------|
| `integration/scripts/build_triple_store.py` | sha256_text, norm, event_id |
| `integration/scripts/build_vector_store.py` | norm（如有） |
| `integration/scripts/build_conversation_graph.py` | sha256_text, norm |
| `integration/scripts/mine_deep_memory_graph.py` | norm（如有本地定义） |
| `integration/scripts/build_deep_memory_profile.py` | norm, sha256_text（如有） |

**每个文件的操作完成后必须记录**：
- 文件名
- 删除了哪些本地定义
- 添加了哪些 import
- py_compile 结果（PASS / FAIL / SKIP）
- 若 ESCALATE：差异说明

---

## Wave 5: 验证

在项目根目录执行以下命令，全部通过才算 Phase 13 完成：

```powershell
# 1. 检查 sha256_text 只在 common.py 定义
python -c "
import subprocess, re
result = subprocess.run(['python', '-m', 'grep', '-rn', 'def sha256_text', 'integration/scripts/'], capture_output=True, text=True)
print(result.stdout)
"

# 2. 检查 TOPIC_RULES 只在 rules.py 定义  
python -c "
import subprocess
result = subprocess.run(['python', '-m', 'grep', '-rn', 'TOPIC_RULES\s*=', 'integration/scripts/'], capture_output=True, text=True)
print(result.stdout)
"

# 3. 运行测试
python tests\test_memory_contracts.py

# 4. 管道 dry-run
python integration\scripts\run_pipeline.py --dry-run
```

---

## GSD Planning Gates

- **Pre-flight**: 执行 Wave 4 前，先确认 `integration/scripts/common.py` 和 `integration/scripts/rules.py` 存在且内容完整。
- **Abort gate**: 任何文件 `py_compile` 失败，立即停止该文件的后续改动，回滚到原始内容。
- **Escalation gate**: 本地函数体与 `common.py` 有任何差异（包括空格/编码），不自动合并，标记 ESCALATE。

## Risks

| Risk | Mitigation |
|------|-----------|
| extract_tools 调用点漏改 | 每次迁移后全文搜索 `extract_tools(` 确认所有调用都传了 tool_names |
| py_compile 通过但运行时 ImportError | 确保每个文件的 sys.path.insert 在 from common import 之前 |
| 本地函数行为细微不同 | 严格逐行对比，不同则 ESCALATE，不允许"大致相同"通过 |
