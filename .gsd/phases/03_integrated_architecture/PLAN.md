# Phase 03: 实现架构图

## 目标

按用户提供的架构图实现项目结构：

- 数据模块：Google、GPT、Agent。
- 每个数据模块内部保留原始数据、结构化数据、分析数据。
- 新增统合模块。
- 统合模块接收各数据模块结构化数据。
- 统合模块建立跨模块实体连接。
- 统合模块输出跨模块结构化数据和综合分析数据。

## 实现

- 新增 `统合模块/`。
- 新增 `统合模块/脚本/build_integrated_system.py`。
- 读取三大结构化库：
  - `Google/结构化数据/SQLite数据库/google_data.sqlite`
  - `GPT/结构化数据/SQLite数据库/chatgpt_data.db`
  - `Agent/结构化数据/SQLite数据库/agent_data.sqlite`
- 输出统一库：
  - `统合模块/SQLite数据库/personal_system.sqlite`
- 输出 CSV 和 HTML 分析产物。

## 验收

- `personal_system.sqlite` 存在。
- `source_modules` 覆盖 Google / GPT / Agent。
- `unified_events` 有来自三大模块的记录。
- `entities` 有主题、工具、域名、文件、会话、技能等实体。
- `entity_links` 有跨模块连接。
- `cross_module_insights` 有综合分析结果。
- `README.md` 说明该模块在架构图中的角色。
