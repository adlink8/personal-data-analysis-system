"""Phase 14 Wave 2.1 测试：knowledge unit extraction。"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

_THIS_DIR = Path(__file__).resolve().parent
_ROOT = _THIS_DIR.parent

from personal_knowledge.domains.knowledge.build_knowledge_units import (  # noqa: E402
    KnowledgeUnit,
    ExtractionResult,
    strip_system_injections,
    is_meaningful,
    _clean_json,
)


# === Pydantic schema 测试 ===

def test_knowledge_unit_valid() -> None:
    """有效 KnowledgeUnit 通过验证。"""
    u = KnowledgeUnit(
        unit_type="preference", subject="shell",
        question="用什么 shell？", answer="PowerShell",
        confidence=0.9, evidence_quote="我用 PowerShell",
    )
    assert u.unit_type == "preference"
    assert u.lifecycle == "current"


def test_knowledge_unit_extra_forbid() -> None:
    """extra 字段被拒绝。"""
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            unit_type="preference", subject="x",
            question="q?", answer="a",
            confidence=0.9, evidence_quote="ev",
            extra_field="bad",
        )


def test_knowledge_unit_invalid_type() -> None:
    """无效 unit_type 被拒绝。"""
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            unit_type="invalid", subject="x",
            question="q?", answer="a",
            confidence=0.9, evidence_quote="ev",
        )


def test_knowledge_unit_confidence_range() -> None:
    """confidence 超范围被拒绝。"""
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            unit_type="preference", subject="x",
            question="q?", answer="a",
            confidence=1.5, evidence_quote="ev",
        )


def test_knowledge_unit_empty_evidence() -> None:
    """空 evidence_quote 被拒绝。"""
    with pytest.raises(ValidationError):
        KnowledgeUnit(
            unit_type="preference", subject="x",
            question="q?", answer="a",
            confidence=0.9, evidence_quote="",
        )


def test_extraction_result_abstain() -> None:
    """ExtractionResult abstain 模式。"""
    r = ExtractionResult(abstain=True, abstain_reason="too short")
    assert r.abstain is True
    assert len(r.units) == 0


def test_extraction_result_extra_forbid() -> None:
    """ExtractionResult extra 字段被拒绝。"""
    with pytest.raises(ValidationError):
        ExtractionResult(abstain=False, extra_field="bad")


# === System-reminder 预处理测试 ===

def test_strip_system_reminder() -> None:
    """剥离 <system-reminder> 标签。"""
    text = "<system-reminder data-role='user-context'>blah</system-reminder>用户实际指令"
    cleaned = strip_system_injections(text)
    assert "system-reminder" not in cleaned
    assert "用户实际指令" in cleaned


def test_strip_multiple_injections() -> None:
    """剥离多种注入标签。"""
    text = ("<system-reminder>sr</system-reminder>"
            "<environment_context>ec</environment_context>"
            "真实内容")
    cleaned = strip_system_injections(text)
    assert "真实内容" in cleaned
    assert "sr" not in cleaned
    assert "ec" not in cleaned


def test_strip_preserves_normal_text() -> None:
    """无注入的文本不受影响。"""
    text = "我习惯用 PowerShell 做所有本机操作"
    assert strip_system_injections(text) == text


def test_is_meaningful() -> None:
    """>30 字为有意义，否则无。"""
    assert is_meaningful("a" * 31)
    assert not is_meaningful("a" * 30)
    assert not is_meaningful("")
    assert not is_meaningful("   ")


# === JSON 清洗测试 ===

def test_clean_json_code_fence() -> None:
    """去除 markdown code fence。"""
    text = '```json\n{"units": [], "abstain": true}\n```'
    cleaned = _clean_json(text)
    assert cleaned.startswith("{")
    assert cleaned.endswith("}")


def test_clean_json_extra_brace() -> None:
    """去除多余闭合括号。"""
    text = '{"units": [], "abstain": true}\n}'
    cleaned = _clean_json(text)
    # 截取到最后一个 }
    parsed = json.loads(cleaned)
    assert parsed["abstain"] is True


def test_clean_json_plain() -> None:
    """正常 JSON 不受影响。"""
    text = '{"units": [{"unit_type": "preference"}], "abstain": false}'
    cleaned = _clean_json(text)
    assert json.loads(cleaned)["abstain"] is False
