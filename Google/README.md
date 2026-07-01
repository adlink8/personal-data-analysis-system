# Google 数据模块

本模块按raw、structured、analysis三层组织。原始 Takeout 数据保留在：

`C:\Users\li\Desktop\数据分析\Google\raw\Takeout`

## 目录结构

- `structured/raw_index`：原始 Takeout 一级模块索引。
- `structured/details_csv`：从 Takeout 抽取出的可分析明细和汇总表。
- `structured/db`：SQLite 数据库、schema、查询说明。
- `structured/by_topic`：按内容主题拆分的活动明细。
- `structured/by_service`：按 Google 服务拆分的活动明细。
- `structured/scripts`：分析、建库、整理scripts。
- `analysis/reports_html`：已生成的分析报告。
- `analysis/charts_png`：报告图表。

## 当前统计

- 活动明细：1696
- 主题分类：8
- 服务分类：5

## 主要主题

- AI / 编程 / 工具: 724
- 娱乐 / 体育 / 生活内容: 573
- 其他 / 未分类: 162
- 政治 / 时政 / 社会: 119
- 账号 / 安全 / 浏览器: 43
- 课程 / 学习 / 资料: 38
- 支付 / 金融 / 卡: 19
- 地图 / 地点 / 本地生活: 18

## 主要服务

- Gemini Apps: 720
- YouTube: 700
- Search: 263
- Maps: 12
- AI Mode: 1
