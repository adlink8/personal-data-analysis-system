# CONCERNS.md — 技术债、风险与待规划项

> 生成时间: 2026-06-17
> 数据来源: README.md、git log、chroma_client.py、build_memory_store.py、
>           build_context_memory.py、build_capability_memory.py、目录结构扫描

---

## 技术债

### 目录结构混乱

顶层存在多个含义不明的目录，无文档说明用途：

| 目录 | 问题 |
|------|------|
| `%DB%` | 目录名含 Shell 变量符号 `%`，在 Windows 路径中极易被误展开；内容为嵌套的 `%DB%` 子目录，实际用途未知，未纳入 git |
| `new_import/` | 含 `duplicate_audit/`、`pipelines/` 子目录，与 `imports/` 平行存在，命名含义重叠 |
| `imports/` | 含 `batches/`、`incoming/`、`README.md`，与 `new_import/` 职责区分不清 |
| `lib/` | 顶层 `lib/` 未纳入 git（`git status` 显示为 `??`），用途不明 |
| `classification_summary.json`、`_schema.json`、`_schema.py` | 顶层散落文件，无归属模块 |

### 脚本运行顺序强耦合（无 Makefile / pipeline 管理）

README 明确列出 6 步固定运行顺序，且有严格依赖：

```
build_integrated_system.py     ← 重建整个 SQLite，会删除库文件
enrich_unified_events.py       ← 必须紧跟步骤1，否则增强表丢失
build_merge_layer.py           ← 依赖步骤2的 content_rich
build_deep_profiles.py         ← 依赖增强表
build_vector_store.py          ← 依赖前4步
build_context_doc.py           ← 依赖前5步
```

无任何自动化工具（Makefile、invoke、doit、shell 脚本）保障顺序，完全靠人工记忆和 README 文字约束。

### ChromaDB 客户端绕行方案（自写 REST 客户端）

`统合模块/脚本/chroma_client.py` 是因官方 `chromadb` 包的 `httpx` 兼容性问题（本地 chroma 服务返回 502）而自行实现的轻量 REST 客户端。这是一个绕行补丁，不是长期方案：

- 需要手动跟进 Chroma REST API v2 的变动
- 无官方包的类型提示、版本兼容层、重试策略
- 约 230 行维护负担落在项目本身

---

## 依赖风险

### Chroma httpx 兼容性问题

根本原因未解决：官方 `chromadb` Python 客户端与本地 chroma 服务之间的 `httpx` 502 问题仍存在，绕行方案依赖 `requests` 库。若 Chroma 升级 API 版本，`chroma_client.py` 需同步手动更新。

### 本地模型路径硬编码风险

`README.md` 和多个脚本使用固定路径：

```
D:\models\bge-small-zh-v1.5
```

该路径硬编码在脚本中，不可跨机复用，换机/换盘符/模型迁移后会直接报错。`local_embed.py` 无配置文件或环境变量覆盖机制。

**建议修复：** 在 `local_embed.py` 顶部读取 `PERSONAL_DATA_MODEL_PATH` 环境变量，回退到硬编码路径。

### 无鉴权的 REST API 与 MCP Server

- `api_server.py`：README 明确说明"API 本身不带鉴权"，默认 `127.0.0.1:8000`
- `mcp_server.py`：MCP 配置直接暴露本机路径（`C:/Users/li/Desktop/...`），无访问控制
- ChromaDB 服务：不对外暴露，但本机其他进程可直接访问 `localhost:8001`，无鉴权

风险场景：若 `api_server.py` 误绑定到 `0.0.0.0` 或处于同一局域网，个人历史数据无保护。

---

## 数据风险

### 增强表依赖运行顺序（重建库会丢失增强表）

`build_integrated_system.py`（步骤1）**删除并重建整个 `personal_system.sqlite`**，增强表（`unified_events_rich` / `event_categories_v2` / `entity_links_v2`）随之丢失。必须手动重跑步骤2。

如果只跑步骤1而忘记跑步骤2：
- `build_deep_profiles.py` 回退到"修复前的污染数据"（README 原文）
- `dashboard.py` 的分类数据失效
- MCP / REST API 的 `search_semantic` 依赖的 `content_rich` 变为空

目前无任何保护机制（如事务、备份、完成标记检查）。

### 向量库与 SQLite 不同步风险

向量库（Chroma `personal_events`）与 SQLite（`personal_system.sqlite`）独立存储，没有版本对齐机制：

- 重跑步骤1-4 后，若不重跑步骤5（`build_vector_store.py`），向量库仍是旧 embedding，`event_id` 指向已被覆写的 SQLite 行
- `build_vector_store.py` 有 `--resume` 断点续传，但进度文件（`vector_build_progress.json`）与 SQLite 重建无关联

### 个人数据本地存储安全边界

所有原始个人数字足迹（Google 历史、GPT 对话、Agent 会话）本地明文存储：

- SQLite 数据库无加密
- `content_rich` 字段含真实对话内容
- 向量库 metadata 含时间、来源、分类等行为标签
- `统合模块/分析数据/ai_context/person_profile.md` 汇总个人画像，可直接被读取

无磁盘加密、数据库加密或访问日志记录。

---

## 待规划

### Phase 04 记忆层升级状态

git log 显示最新 commit（`bc0f7ab`）为"纳入 Phase 04 记忆层升级规划(CONTEXT + PLAN)"，`.gsd/phases/04_memory_layer_upgrade/` 下有 `CONTEXT.md` 和 `PLAN.md`。

Phase 04 相关脚本**全部未纳入 git**（`git status` 标记为 `??`）：

```
统合模块/脚本/build_capability_memory.py   ← 未追踪
统合模块/脚本/build_context_memory.py      ← 未追踪
统合模块/脚本/build_memory_graph.py        ← 未追踪
统合模块/脚本/build_memory_store.py        ← 未追踪
统合模块/脚本/build_preference_memory.py   ← 未追踪
统合模块/脚本/query_graph.py              ← 未追踪
```

这些脚本已在开发但未提交，存在丢失风险（无法回滚、无法 diff）。**建议尽快 git add + commit。**

### 未纳入 git 的其他文件

- `%DB%/`（完整目录）
- `lib/`（完整目录）

建议明确决策：纳入 git（加 `.gitignore` 精确排除大文件）或在 README 中说明忽略原因。

### 缺少数据备份策略

- `personal_system.sqlite` 无定期备份（每次 `build_integrated_system.py` 重建即覆盖）
- Chroma 向量库无备份脚本
- 无备份时间点记录
- 构建一次约需完整运行链路（估算 > 30 分钟含向量化），一旦数据损坏恢复成本高

**建议**: 在步骤1运行前自动备份 SQLite（`shutil.copy` 加时间戳后缀），代价极低。

### 无统一管道入口

当前需要手动依次运行 6 条命令。建议新增 `run_pipeline.py` 或 `Makefile`：

```powershell
# 理想使用方式
python 统合模块\脚本\run_pipeline.py         # 全量重跑
python 统合模块\脚本\run_pipeline.py --from 2 # 从步骤2开始
python 统合模块\脚本\run_pipeline.py --dry-run # 只打印顺序不执行
```

---

*文档由 ZCode 基于代码库静态分析生成，未运行任何脚本。*
