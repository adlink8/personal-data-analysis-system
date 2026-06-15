# 接入示例

本目录给出把个人数据系统接进各种 AI 应用的可运行示例。所有示例都基于
**同一个 `unified_search` 后端**(或它的 HTTP 封装 `api_server.py`),
保证四种接入方式行为一致。

## 接入方式对照

| 示例文件 | 接入方式 | 适用场景 | 依赖 |
|---|---|---|---|
| `openai_function_calling.py` | OpenAI 函数调用 | 让 GPT/DeepSeek/千问 等模型按需检索历史 | `openai` |
| `langchain_tool.py` | LangChain Tool | 已用 LangChain/LangGraph 的项目加"翻历史"能力 | `langchain` 全家桶 |
| `rag_inject.py` | RAG 上下文注入 | Dify/FastGPT/自建 RAG,静默增强 prompt | 仅标准库(调 HTTP API) |

## 选哪个?

- **想要 Agent 自己决定何时查数据** → `openai_function_calling.py` 或 `langchain_tool.py`
  (模型走 ReAct/工具调用循环,问"我之前做过 X 吗"它会自动检索)
- **想要无脑增强每次回答** → `rag_inject.py`
  (不依赖模型支持 function-calling,任何 LLM 都能用)
- **在 Dify/FastGPT 等平台** → 用 `api_server.py` 暴露的 HTTP 接口配成"自定义工具"
  (见根目录 README 的"REST API 接入"节)

## 运行前准备

1. 确保数据已构建(跑过重跑链路的 5 步,向量库已建)
2. **RAG 注入示例**需要先启动 API:`python ../api_server.py`
3. **OpenAI/LangChain 示例**需要 `pip install -r <对应依赖>` 并设 `OPENAI_API_KEY`
4. 用兼容端点(DeepSeek 等)时额外设 `OPENAI_BASE_URL`

## 跑法

```powershell
cd 统合模块\脚本

python examples/openai_function_calling.py "我最近在折腾什么和 PPT 有关的事?"
python examples/langchain_tool.py        "我最近做过哪些和数据库调试有关的事?"

# 先启动 API,再跑 RAG 示例
python api_server.py                      # 另开一个终端
python examples/rag_inject.py             "上次怎么调试 Docker 的"
```
