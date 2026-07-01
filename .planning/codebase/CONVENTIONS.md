# CONVENTIONS.md — 代码规范约定

> 适用范围: `C:\Users\li\Desktop\数据分析` 整个项目。
> 依据: 对 `integration/scripts/` 下全部scripts的实际分析，2026-06-17。

---

## 1. 命名规范

### 1.1 文件与目录

| 层次 | 命名语言 | 示例 |
|------|---------|------|
| 顶层数据源目录 | **中文** | `Google/`、`GPT/`、`Agent/`、`integration/` |
| 功能子目录 | **中文** | `scripts/`、`analysis/`、`db/`、`raw/`、`structured/` |
| Python scripts文件 | **英文 snake_case** | `build_merge_layer.py`、`common.py`、`rules.py` |
| 配置/规划文件 | **英文** | `.gitignore`、`requirements.txt`、`_schema.py` |
| 数据产出文件 | **中文或英文均可** | `架构图.drawio`、`person_profile.md` |

### 1.2 Python 标识符

| 类型 | 规范 | 示例 |
|------|------|------|
| 函数 | `snake_case` 英文 | `sha256_text`, `write_csv`, `ensure_dirs`, `extract_domain` |
| 变量 | `snake_case` 英文 | `row_factory`, `has_rich`, `use_merged` |
| 常量 / 模块级全局 | `UPPER_SNAKE_CASE` 英文 | `TOOL_NAMES`, `TOPIC_RULES`, `ROOT`, `UNIFIED_DB`, `OUTPUT_SUFFIX` |
| 类 | `PascalCase` 英文 | （现有scripts以函数式为主，类名遵循此规则） |
| 数据库表/列 | `snake_case` 英文 | `merge_clusters`, `merge_members`, `unified_events`, `memory_items` |

### 1.3 数据库表命名约定

- 原始统合表: `unified_events`, `unified_*`
- 增强叠加表: `unified_events_rich`, `event_categories_v2`, `entity_links_v2`
- 合并层表: `merge_clusters`, `merge_members`, `merge_build_meta`
- 记忆层表: `memory_items`, `memory_links`, `memory_relations`
- 版本后缀: `_v2` 表示迭代版本，`_rich` 表示增强层，`_meta` 表示构建元数据

---

## 2. 中文命名使用范围

**中文只用于目录和文件名（数据组织层），代码内部完全使用英文。**

| 允许中文 | 禁止中文 |
|---------|---------|
| 目录名（`integration/`, `scripts/`） | Python 变量名、函数名、参数名 |
| 非scripts文件名（`架构图.drawio`） | SQL 表名、列名 |
| 注释与 docstring | 模块 import 路径（路径字符串可含中文） |
| 打印输出（`print(...)`） | |

路径字符串中含中文属于正常：
```python
ROOT / "integration" / "db" / "personal_system.sqlite"
```

---

## 3. 幂等性约定（DROP IF EXISTS 模式）

项目有两种幂等写入模式，**重复运行不积累数据、不报错**：

### 模式 A — 全量重建（用于"叠加分析表"）

```python
DROP TABLE IF EXISTS <table>;
CREATE TABLE <table> (...);
```

使用此模式的scripts: `build_merge_layer.py`, `enrich_unified_events.py`。
适用场景: 产出表是从源数据完整派生的，每次跑结果确定性一致。

### 模式 B — 建表后清空（用于"记忆层"）

```python
CREATE TABLE IF NOT EXISTS <table> (...);
-- 然后 DELETE WHERE type='xxx' 清空特定类型旧数据
```

使用此模式的scripts: `build_memory_store.py`, `build_capability_memory.py`,
`build_context_memory.py`, `build_preference_memory.py`, `build_memory_graph.py`。
适用场景: 表结构跨scripts共享，只清除自己负责的那一类记忆。

### 向量库幂等

`build_vector_store.py`: `delete_collection` 后重建。
`chroma_client.py`: HTTP 404 on DELETE 视为成功（幂等 delete）。

**约定**: 所有 build_* scripts必须满足"空库上跑 = 已有数据上重跑"结果一致。

---

## 4. 注释风格

```python
"""模块级 docstring：中文，说明scripts职责、解决问题、产出表和运行方式。

设计原则:
- 条目式描述
- 含「=== 节标题 ===」分隔多个部分（算法/产出表/运行方式）
"""

# 行内注释：中文，解释"为什么"而非"是什么"
# e.g.: # 这是抓"结构相似假阳性"的关键

def func(x: str) -> str:
    """单行函数 docstring：中文，一句话说明语义。"""
    ...

# noqa: E402  — 用于 sys.path.insert 后的延迟 import，保持 lint 静默
```

节标题格式: `# === 标题（中文）===` 或 `# === Title ===`

---

## 5. 共享模块职责划分

### `common.py` — 纯工具函数

- **职责**: 纯函数，无副作用，可跨scripts复用
- **依赖约束**: 只依赖 Python 标准库，不 import 项目内其他模块
- **提供**: `sha256_text`, `norm`, `short`, `event_id`, `entity_id`, `extract_domain`, `extract_tools`, `write_csv`, `write_json`, `ensure_dirs`
- **设计原则**: 向后兼容，所有scripts从此 import 而非各自重复定义

### `rules.py` — 分类规则与配置表

- **职责**: 纯数据常量，集中维护分类规则，消除多scripts间不一致
- **提供**:
  - `TOOL_NAMES`: 工具名表（实体抽取用）
  - `TOPIC_RULES`: 旧主题规则（v1，含元数据词，保留作对照基线）
  - `PURE_TOPIC_RULES` + `PURE_TOPIC_DEFAULT`: 新主题规则（v2，剥离元数据污染）
  - `THINKING_RULES` / `PURE_THINKING_RULES` + `PURE_THINKING_DEFAULT`: 思考模式规则
- **约定**: 业务scripts优先使用 `PURE_*` 系列；`TOPIC_RULES` 等老版本只用于生成 `category_v1` 对照列

### import 方式

```python
# 在scripts顶部插入当前目录到路径
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import rules as _rules
from common import sha256_text, norm, write_csv
```

---

## 6. scripts重跑链路约定

完整数据管道从原始输入到可用接口的执行顺序：

```
1. raw解析层
   python integration\scripts\build_integrated_system.py
       └─ 产出: unified_events 及其 9 张原始统合表

2. 语义增强层（必须紧跟步骤1）
   python integration\scripts\enrich_unified_events.py
       └─ 产出: unified_events_rich, event_categories_v2, entity_links_v2

3. 合并去重层
   python integration\scripts\build_merge_layer.py [--threshold-l1 N]
       └─ 产出: merge_clusters, merge_members, merge_build_meta

4. 画像与分析层（可并行）
   python integration\scripts\build_deep_profiles.py [--use-merged]
   python integration\scripts\build_memory_store.py
   python integration\scripts\build_capability_memory.py
   python integration\scripts\build_context_memory.py
   python integration\scripts\build_preference_memory.py
   python integration\scripts\build_memory_graph.py

5. 向量检索层
   python integration\scripts\build_vector_store.py [--resume]

6. AI 上下文层
   python integration\scripts\build_context_doc.py
```

**约定**: 每层幂等，单层重跑不影响其他层（叠加表而非修改原表）。
`--use-merged` 标志: `build_deep_profiles.py` 支持，合并层不存在时静默回退全量并打印提示。
