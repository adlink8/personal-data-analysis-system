"""tests 全局夹具。

默认把 semantic_cards 的向量索引登记指向不存在的路径，使 search_cards 在
所有测试里稳定走关键词回退路径——不依赖真实 chroma 服务、登记文件与本机
embedding 模型。需要测向量路径的用例可在测试体内再次 monkeypatch
``semantic_cards.SEMANTIC_INDEX_REGISTRY`` 覆盖本默认（后设置的生效）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

import personal_knowledge.retrieval.semantic_cards as semantic_cards


@pytest.fixture(autouse=True)
def _no_vector_registry(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        semantic_cards,
        "SEMANTIC_INDEX_REGISTRY",
        tmp_path / "absent" / "semantic_index_registry.json",
    )
