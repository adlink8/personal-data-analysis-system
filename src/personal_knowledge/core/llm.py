"""Generic OpenAI-compatible LLM client primitives (shared library layer).

Extracted from build_conversation_summary to break the cross-domain hub coupling (Phase 21 D-01).
"""

from __future__ import annotations

import os
import sys
import time

MAX_RETRY = 4  # 429/网络错误最大重试次数


def make_llm_client():
    """构造 OpenAI 兼容 client,配置全走环境变量。

    默认端点为小米 MiMo(token-plan-cn),与 README 文档一致;
    可用 OPENAI_BASE_URL / OPENAI_API_KEY 覆盖走其他兼容端点(如智谱、第三方中转)。

    两个工程适配(2026-06-28 Wave 8 加入):
    1. 代理:openai 库底层 httpx 不读 HTTPS_PROXY 环境变量,需显式注入 http_client。
    2. UA 伪装:部分第三方中转站按 X-Stainless-* / User-Agent 指纹拦截官方 SDK,
       改 UA 为 curl/8.0 绕过(直连官方端点时无影响)。
    """
    try:
        from openai import OpenAI
    except ImportError:
        sys.exit("[error] 未安装 openai 库,请运行: pip install openai")
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("MEM0_API_KEY")
    if not api_key:
        sys.exit("[error] 未设置 OPENAI_API_KEY / MEM0_API_KEY")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://token-plan-cn.xiaomimimo.com/v1")
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY")
    kw = {"base_url": base_url, "api_key": api_key, "timeout": 120,
          "default_headers": {"User-Agent": "curl/8.0"}}
    if proxy:
        try:
            import httpx
            kw["http_client"] = httpx.Client(
                proxy=proxy, timeout=120, headers={"User-Agent": "curl/8.0"})
        except ImportError:
            pass  # 无 httpx 则退回默认连接(直连场景)
    return OpenAI(**kw)


def _chat_with_retry(client, model: str, messages: list[dict], **kwargs) -> str:
    """带 429/网络错误指数退避重试的 chat 调用,返回 content 文本。

    MiMo token-plan 端点限流较硬(实测并发>4 路会批量 429),并发场景下
    必须重试才能保证成功率。退避间隔 2/4/8/16s,最多 MAX_RETRY 次。
    """
    last_exc = None
    for attempt in range(MAX_RETRY):
        try:
            resp = client.chat.completions.create(
                model=model, messages=messages, **kwargs
            )
            return resp.choices[0].message.content.strip()
        except Exception as exc:
            last_exc = exc
            # 429 限流或网络瞬断才重试;其他错误(鉴权/参数)直接抛
            name = type(exc).__name__
            if "RateLimit" in name or "Timeout" in name or "APIConnection" in name \
               or "APITimeout" in name or "ServiceUnavailable" in name:
                wait = 2 ** (attempt + 1)  # 2,4,8,16s
                time.sleep(wait)
                continue
            raise
    raise last_exc  # 重试用尽仍失败则抛最后错误
