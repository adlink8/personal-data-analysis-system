# Phase 02: Agent 数据纳入

## 目标

把本机 Windows 与 WSL Ubuntu-D 上的 Codex、WorkBuddy、Hermes、Claude、Cline、Cursor、Gemini、Agents 等工具产生的数据纳入 `Agent` 数据源，用于后续分析 skills、memory、sessions、对话摘要和工具状态。

## 数据源

- `C:\Users\li\.codex`
- `C:\Users\li\.agents`
- `C:\Users\li\.workbuddy`
- `C:\Users\li\WorkBuddy`
- `C:\Users\li\.hermes`
- `C:\Users\li\.claude`
- `C:\Users\li\.cline`
- `C:\Users\li\.cursor`
- `C:\Users\li\.gemini`
- `C:\Users\li\.cagent`
- `C:\Users\li\.ollama`
- `C:\Users\li\AppData\Roaming\Codex`
- `C:\Users\li\AppData\Roaming\WorkBuddy`
- `C:\Users\li\AppData\Roaming\Hermes`
- `C:\Users\li\AppData\Roaming\Claude`
- `C:\Users\li\AppData\Local\Codex`
- `C:\Users\li\AppData\Local\WorkBuddy`
- `C:\Users\li\AppData\Local\hermes`
- `C:\Users\li\AppData\Local\Claude`
- `C:\Users\li\AppData\Local\OpenAI`
- `C:\Users\li\Documents\Codex`
- `C:\Users\li\Documents\Cline`
- `Ubuntu-D:/home/li/.codex`
- `Ubuntu-D:/home/li/.claude`
- `Ubuntu-D:/home/li/.gemini`
- `Ubuntu-D:/home/li/.hermes`
- `Ubuntu-D:/home/li/.codebuddy`
- `Ubuntu-D:/home/li/.copilot`
- `Ubuntu-D:/home/li/.ollama`

## 策略

- 不移动源目录。
- 只复制白名单数据：skills、memory、sessions、plans、tasks、SQLite 状态库、结构化配置。
- 使用 SQLite backup API 复制 `.sqlite` / `.db`，避免直接复制在线 WAL 状态。
- 排除认证、密钥、token、缓存、依赖、二进制、插件缓存、blobs、node_modules。
- 大型 session 文件只抽取有限消息摘要，完整原始文件保留在 `Agent/原始数据`。
- WSL 数据使用 `agent_data.tar.gz` 归档放入 `Agent/原始数据/WSL_UbuntuD_AgentArchive`，并生成 `agent_file_manifest.tsv`。

## 产物

- `Agent/README.md`
- `Agent/结构化数据/脚本/build_agent_dataset.py`
- `Agent/结构化数据/SQLite数据库/agent_data.sqlite`
- `Agent/结构化数据/原始数据索引/agent_source_files.csv`
- `Agent/结构化数据/明细数据/*.csv`
- `Agent/分析数据/报告HTML/agent_data_summary.html`
- `Agent/分析数据/classification_summary.json`

## 验收结果

- 原始文件：2932 个
- 原始副本体积：约 1327.31 MB
- WSL 归档：约 243.56 MB，清单 6145 行
- skills：527 条
- memory 文件：347 个
- session 文件：518 个
- session 消息摘要行：20324 行
- SQLite 表清单：83 行

## 已知事项

- 早期超时构建留下的未索引 WAL/SHM 和临时残留已清理。
