# Phase 03: 实现架构图

## 目标

按用户提供的架构图实现项目结构：

- 数据模块：Google、GPT、Agent。
- 每个数据模块内部保留raw、structured、analysis。
- 新增integration。
- integration接收各数据模块structured。
- integration建立跨模块实体连接。
- integration输出跨模块structured和综合analysis。

## 实现

- 新增 `integration/`。
- 新增 `integration/scripts/build_integrated_system.py`。
- 读取三大结构化库：
  - `Google/structured/db/google_data.sqlite`
  - `GPT/structured/db/chatgpt_data.db`
  - `Agent/structured/db/agent_data.sqlite`
- 输出统一库：
  - `integration/db/personal_system.sqlite`
- 输出 CSV 和 HTML 分析产物。

## 验收

- `personal_system.sqlite` 存在。
- `source_modules` 覆盖 Google / GPT / Agent。
- `unified_events` 有来自三大模块的记录。
- `entities` 有主题、工具、域名、文件、会话、技能等实体。
- `entity_links` 有跨模块连接。
- `cross_module_insights` 有综合分析结果。
- `README.md` 说明该模块在架构图中的角色。
