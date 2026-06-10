# 统合模块

统合模块对应架构图左侧的大模块：接收 Google、GPT、Agent 等数据模块已经清洗好的结构化数据，建立跨模块实体连接，并生成面向个人系统的综合分析数据。

## 角色

```text
Google / GPT / Agent 数据模块
  -> 结构化 SQLite
  -> 统合模块
  -> 统一事件 / 实体 / 关系 / 综合分析
```

统合模块不保存各来源的原始导出文件。原始数据继续留在各数据模块中。

## 目录

```text
统合模块/
  原始输入索引/
  结构化数据/
  分析数据/
  SQLite数据库/
  脚本/
  README.md
```

## 输入

- `Google/结构化数据/SQLite数据库/google_data.sqlite`
- `GPT/结构化数据/SQLite数据库/chatgpt_data.db`
- `Agent/结构化数据/SQLite数据库/agent_data.sqlite`

## 输出

- `SQLite数据库/personal_system.sqlite`
- `结构化数据/unified_events.csv`
- `结构化数据/entities.csv`
- `结构化数据/event_entities.csv`
- `结构化数据/entity_links.csv`
- `分析数据/module_summary.csv`
- `分析数据/cross_module_insights.csv`
- `分析数据/integrated_system_report.html`
- `分析数据/统合画像.md`
- `分析数据/统合画像.html`
- `分析数据/统合画像.json`
- `分析数据/统合画像_数据流向.csv`
- `分析数据/统合画像_数据增长_按月.csv`
- `分析数据/统合画像_数据增长图.png`
- `分析数据/统合画像_关注点.csv`
- `分析数据/统合画像_个人思考模式.csv`

## 重建

从数据分析根目录运行：

```powershell
python 统合模块\脚本\build_integrated_system.py
```

生成深度画像：

```powershell
python 统合模块\脚本\build_deep_profiles.py
```

## 核心表

- `source_modules`：来源模块清单。
- `unified_events`：统一事件表。
- `entities`：主题、工具、域名、文件、会话、技能等实体。
- `event_entities`：事件和实体的关系。
- `entity_links`：跨模块实体连接。
- `module_summaries`：模块级摘要。
- `cross_module_insights`：综合分析结果。

## 深度画像

深度画像基于 `personal_system.sqlite` 生成，不改变原始数据和结构化数据库。

- 模块画像：输出到 `Google/GPT/Agent` 各自的 `分析数据/模块画像.*`。
- 统合画像：输出到 `统合模块/分析数据/统合画像.*`。
- 数据流向：说明 `原始数据 -> 结构化数据 -> 分析数据 -> 统合模块` 的证据链。
- 数据增长：按月统计各来源进入统合层的事件增长。
- 关注点：按主题、服务/工具、原始分类聚合。
- 个人思考：基于行为文本的模式推断，用于复盘和 AI 上下文建设，不是心理诊断。
