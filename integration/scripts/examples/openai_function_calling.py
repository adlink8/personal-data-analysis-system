"""示例 1:把个人数据接进 OpenAI / 兼容 OpenAI 协议的 Agent(函数调用)。

适用:OpenAI 官方 API、DeepSeek、通义千问、Moonshot、本地 vLLM/Ollama 等
      任何兼容 OpenAI function-calling 协议的模型。

思路:把 unified_search 的 4 个能力注册成 functions/tools,让模型自己决定
      何时检索用户历史。这是"Agent 接入"最直接的形态 —— 模型按需调你的数据。

运行前:
    pip install openai
    set OPENAI_API_KEY=sk-...        (Windows cmd)
    或用兼容端点时额外设置 OPENAI_BASE_URL

运行:
    python examples/openai_function_calling.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# 让本脚本能 import 上层的 unified_search
_THIS_DIR = Path(__file__).resolve().parent
_SCRIPTS = _THIS_DIR.parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import unified_search as us  # noqa: E402

try:
    from openai import OpenAI  # noqa: E402
except ImportError:
    sys.exit("请先安装: pip install openai")


# === 1. 把检索能力声明成 OpenAI tools ====================================
# 模型看到这份 schema,就知道"可以检索用户历史"以及怎么调。

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_semantic",
            "description": "语义检索用户的历史事件(模糊召回)。用户说'我之前好像做过X'时用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "自然语言查询"},
                    "top_k": {"type": "integer", "description": "返回条数", "default": 5},
                    "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_events",
            "description": "按结构化条件精确过滤用户事件(时间/分类/关键词)。用户说'列出某月某类事件'时用。",
            "parameters": {
                "type": "object",
                "properties": {
                    "source": {"type": "string", "enum": ["Google", "GPT", "Agent"]},
                    "month": {"type": "string", "description": "如 2025-03"},
                    "category": {"type": "string", "description": "category_v2 子串"},
                    "keyword": {"type": "string"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
]

# name → 真实函数 的映射表
DISPATCH = {
    "search_semantic": us.search_semantic,
    "query_events": us.query_events,
}


# === 2. 跑一轮对话(模型可能多次回调 tool) ===============================
def chat(user_message: str, model: str = "gpt-4o-mini") -> str:
    client = OpenAI()  # 自动读 OPENAI_API_KEY / OPENAI_BASE_URL

    messages = [
        {
            "role": "system",
            "content": (
                "你能检索用户的历史数据(Google搜索/GPT对话/Agent操作记录)。"
                "当用户问到自己的过往时,先用 tool 检索真实记录再回答,不要凭空编造。"
            ),
        },
        {"role": "user", "content": user_message},
    ]

    for _ in range(4):  # 最多 4 轮 tool 调用,防死循环
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=TOOLS, tool_choice="auto"
        )
        msg = resp.choices[0].message
        messages.append(msg)

        # 模型没要调 tool,直接出最终回答
        if not msg.tool_calls:
            return msg.content or "(无回复)"

        # 执行模型要求的 tool 调用,把结果喂回去
        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            print(f"  [tool] {name}({args})")
            try:
                data = DISPATCH[name](**args)
                result = json.dumps(data, ensure_ascii=False, default=str)[:2000]
            except Exception as e:
                result = f"工具调用失败: {e}"
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": result,
                }
            )

    return "(超过最大 tool 调用轮数)"


if __name__ == "__main__":
    question = " ".join(sys.argv[1:]) or "我最近在折腾什么和 PPT 有关的事?帮我回忆一下"
    print(f"用户: {question}\n")
    answer = chat(question)
    print(f"\nAI: {answer}")
