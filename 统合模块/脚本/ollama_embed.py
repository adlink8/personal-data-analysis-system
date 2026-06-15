"""ollama embedding 客户端。

封装 ollama 的 /api/embeddings 接口,提供单条/批量文本向量化。
build_vector_store.py 和 search_vectors.py 共用。

支持模型(配置项 EMBED_MODEL):
- bge-m3:1024 维,中英双语最佳(首选)
- nomic-embed-text:768 维,英文优先
- 其他 ollama 支持的 embedding 模型

设计:
- 单条 embed():返回一条文本的向量
- 批量 embed_batch():返回多条,带进度打印,失败重试
- 自动检测模型是否可用(避免拉模型期间误调)
"""

from __future__ import annotations

import time
from typing import Optional

import requests


# === 配置 ===
OLLAMA_HOST = "localhost"
OLLAMA_PORT = 11434
EMBED_MODEL = "bge-m3"  # 阶段二选定;换模型只改这一处
EMBED_TIMEOUT = 120  # 单次 embedding 请求超时(秒)
EMBED_DIM = 1024  # bge-m3 维度(换模型时同步改)


def _url(path: str) -> str:
    return f"http://{OLLAMA_HOST}:{OLLAMA_PORT}{path}"


def is_model_available(model: str = EMBED_MODEL, timeout: int = 10) -> bool:
    """检查 ollama 里是否已安装指定模型。"""
    try:
        r = requests.post(
            _url("/api/show"),
            json={"name": model},
            timeout=timeout,
        )
        if r.status_code == 200:
            return True
        # 404 = 未找到
        return False
    except requests.RequestException:
        return False


def embed(text: str, model: str = EMBED_MODEL, timeout: int = EMBED_TIMEOUT) -> list[float]:
    """单条文本向量化。返回 float 向量(维度由模型决定)。

    注意:单条调用较慢(bge-m3 约 21s/条,因为 ollama 每次重复加载开销)。
    批量请用 embed_batch(),32 条批量时每条仅 0.7s。

    失败抛 RuntimeError(网络/模型不存在/返回空)。
    """
    if not text or not text.strip():
        raise ValueError("空文本无法 embedding")
    r = requests.post(
        _url("/api/embeddings"),
        json={"model": model, "prompt": text},
        timeout=timeout,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ollama embedding 失败: {r.status_code} {r.text[:200]}")
    vec = r.json().get("embedding")
    if not vec:
        raise RuntimeError(f"ollama 返回空 embedding(模型 {model} 可能不支持 embedding)")
    return vec


def embed_batch_native(
    texts: list[str],
    model: str = EMBED_MODEL,
    timeout: int = 180,
    retries: int = 3,
) -> list[Optional[list[float]]]:
    """批量向量化(用 ollama /api/embed 批量接口,高效)。

    ollama 新版 /api/embed 支持 input 数组,32 条批量时每条仅 0.7s
    (vs 逐条 /api/embeddings 的 21s/条)。

    timeout 较短(180s),避免 ollama 偶尔 hang 导致整个进程卡死。
    整批失败时降级为 8 条小批重试,小批仍失败再降级逐条。

    返回与 texts 等长的列表,空文本对应 None,失败重试后仍失败为 None。
    """
    # 过滤空文本,记录原始位置
    indices_ok: list[int] = []
    clean_texts: list[str] = []
    for i, t in enumerate(texts):
        c = (t or "").strip()
        if c:
            indices_ok.append(i)
            clean_texts.append(c)

    results: list[Optional[list[float]]] = [None] * len(texts)
    if not clean_texts:
        return results

    # 尝试整批请求
    batch_ok = False
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                _url("/api/embed"),
                json={"model": model, "input": clean_texts},
                timeout=timeout,
            )
            if r.status_code == 200:
                embs = r.json().get("embeddings", [])
                if len(embs) == len(clean_texts):
                    for idx, emb in zip(indices_ok, embs):
                        results[idx] = emb
                    batch_ok = True
                    break
        except requests.RequestException:
            pass
        if attempt < retries:
            time.sleep(2.0 * (attempt + 1))

    if batch_ok:
        return results

    # 整批失败:拆成 8 条小批重试
    SUB_BATCH = 8
    for sub_start in range(0, len(clean_texts), SUB_BATCH):
        sub_texts = clean_texts[sub_start : sub_start + SUB_BATCH]
        sub_indices = indices_ok[sub_start : sub_start + SUB_BATCH]
        got = False
        for attempt in range(retries + 1):
            try:
                r = requests.post(
                    _url("/api/embed"),
                    json={"model": model, "input": sub_texts},
                    timeout=120,
                )
                if r.status_code == 200:
                    embs = r.json().get("embeddings", [])
                    if len(embs) == len(sub_texts):
                        for idx, emb in zip(sub_indices, embs):
                            results[idx] = emb
                        got = True
                        break
            except requests.RequestException:
                pass
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
        if not got:
            # 小批也失败,最后降级逐条
            for idx, t in zip(sub_indices, sub_texts):
                for attempt in range(retries):
                    try:
                        results[idx] = embed(t, model=model)
                        break
                    except (RuntimeError, requests.RequestException):
                        time.sleep(1.0 * (attempt + 1))
    return results


def embed_batch(
    texts: list[str],
    model: str = EMBED_MODEL,
    retries: int = 2,
    progress_every: int = 50,
) -> list[Optional[list[float]]]:
    """批量向量化(兼容接口,内部用高效的 embed_batch_native)。

    保留这个函数名以兼容旧调用。progress_every 在批量接口下意义不大
    (整个批次一次完成),保留参数但不频繁打印。
    """
    return embed_batch_native(texts, model=model, retries=retries)


def verify_model(model: str = EMBED_MODEL) -> tuple[bool, str, Optional[int]]:
    """验证模型可用性。返回 (可用, 说明, 维度)。

    用批量接口验证(比单条快,一次请求测通即可)。
    在构建向量库前调用,提前发现"模型未安装/不支持 embedding"等问题。
    """
    if not is_model_available(model):
        return False, f"模型 {model} 未安装,请先 ollama pull {model}", None
    try:
        # 用批量接口验证(两条,一次请求)
        results = embed_batch_native(["test 验证", "dimension check"], model=model, retries=1)
        vec = results[0]
        if vec:
            return True, f"模型 {model} 可用", len(vec)
        return False, f"模型 {model} 返回空 embedding(可能不支持)", None
    except Exception as e:
        return False, str(e), None
