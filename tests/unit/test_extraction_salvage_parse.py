"""_tolerant_parse schema 抢救解析单测（2026-07-26,assistant 轨 schema_invalid 实测模式）。

覆盖四类真实失败模式 + 不可救路径:
1. 多 unit 响应中第 2 个起缺 question → 连坐解除,好 unit 保留
2. unit 带 extra 字段(question_context/solution) → 剥字段后保留
3. Windows 路径非法反斜杠转义 → 修复后可解析
4. 彻底损坏 / 全 unit 无效且非 abstain → 维持 None(schema_invalid)
抢救不降证据标准:输出仍走下游 _evidence_supported gate(此处不重复测)。
"""

import json

import pytest

from personal_knowledge.application.knowledge.build_knowledge_units_prod import (
    ASSISTANT_TRACK,
    _tolerant_parse,
)


def _unit(**over):
    base = {
        "unit_type": "solution",
        "subject": "测试主题",
        "question": "这是一个足够长的问题吗？",
        "answer": "这是一个足够长的答案内容。",
        "confidence": 0.9,
        "evidence_quote": "证据片段证据片段证据片段",
    }
    base.update(over)
    return base


def test_strict_valid_passes_through():
    raw = json.dumps({"units": [_unit()], "abstain": False, "abstain_reason": ""})
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is not None and len(result.units) == 1 and dropped == 0


def test_missing_question_in_second_unit_keeps_first():
    bad = _unit()
    del bad["question"]
    raw = json.dumps({"units": [_unit(), bad], "abstain": False})
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is not None
    assert len(result.units) == 1
    assert dropped == 1
    assert not result.abstain


def test_extra_field_in_unit_is_stripped_not_fatal():
    raw = json.dumps({
        "units": [_unit(question_context="模型自创的字段")],
        "abstain": False,
    })
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is not None and len(result.units) == 1 and dropped == 0


def test_invalid_windows_path_escape_repaired():
    # \U 在 JSON 中是非法转义(合法仅 \u+4hex) —— Windows 路径实测主因
    raw = (
        '{"units": [{"unit_type": "solution", "subject": "路径问题", '
        '"question": "配置文件放在哪个目录下？", '
        '"answer": "放在 C:\\Users\\li 的配置目录下即可。", '
        '"confidence": 0.9, "evidence_quote": "证据片段证据片段证据片段"}], '
        '"abstain": false}'
    )
    with pytest.raises(json.JSONDecodeError):
        json.loads(raw)
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is not None and len(result.units) == 1
    assert "C:\\Users\\li" in result.units[0].answer


def test_markdown_fence_still_handled():
    inner = json.dumps({"units": [_unit()], "abstain": False})
    result, _ = _tolerant_parse(ASSISTANT_TRACK, f"```json\n{inner}\n```")
    assert result is not None and len(result.units) == 1


def test_abstain_with_extra_top_key_salvaged():
    raw = json.dumps({"units": [], "abstain": True,
                      "abstain_reason": "无可抽取", "note": "extra"})
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is not None and result.abstain and dropped == 0


def test_all_units_invalid_not_abstain_stays_dead():
    bad = _unit()
    del bad["answer"]
    raw = json.dumps({"units": [bad], "abstain": False})
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is None and dropped == 1


def test_garbage_stays_dead():
    assert _tolerant_parse(ASSISTANT_TRACK, "完全不是 JSON 的输出") == (None, 0)


def test_wrong_unit_type_for_track_dropped():
    # user 轨类型出现在 assistant 轨 → 该 unit 无效
    raw = json.dumps({"units": [_unit(unit_type="preference")], "abstain": False})
    result, dropped = _tolerant_parse(ASSISTANT_TRACK, raw)
    assert result is None and dropped == 1
