"""PDA-41：证据派生置信度（替代 LLM 自报置信）。"""
from __future__ import annotations

from personal_knowledge.application.knowledge.confidence import (
    BASE,
    CAP,
    derive_confidence,
)

LONG_QUOTE = "这是一段足够长的证据引文，超过二十个字符"
SHORT_QUOTE = "短引文"


def test_user_dual_evidence_long_quote_hits_cap() -> None:
    conf = derive_confidence(
        evidence_count=2, evidence_scope="user", evidence_quote=LONG_QUOTE
    )
    assert conf == CAP  # 0.4+0.2+0.15+0.15+0.1 = 1.0 → 封顶 0.95


def test_user_single_evidence() -> None:
    conf = derive_confidence(
        evidence_count=1, evidence_scope="user", evidence_quote=LONG_QUOTE
    )
    assert conf == 0.85


def test_assistant_single_evidence_short_quote() -> None:
    conf = derive_confidence(
        evidence_count=1, evidence_scope="assistant", evidence_quote=SHORT_QUOTE
    )
    assert conf == 0.6


def test_window_scope_gets_no_user_bonus() -> None:
    conf = derive_confidence(
        evidence_count=1, evidence_scope="window", evidence_quote=LONG_QUOTE
    )
    assert conf == 0.7


def test_no_evidence_is_base() -> None:
    conf = derive_confidence(
        evidence_count=0, evidence_scope="assistant", evidence_quote=""
    )
    assert conf == BASE


def test_confirmation_modifiers() -> None:
    adopted = derive_confidence(
        evidence_count=1, evidence_scope="assistant",
        evidence_quote=SHORT_QUOTE, confirmation_signal="adopted",
    )
    corrected = derive_confidence(
        evidence_count=1, evidence_scope="assistant",
        evidence_quote=SHORT_QUOTE, confirmation_signal="corrected",
    )
    assert adopted == 0.65
    assert corrected == 0.4


def test_corrected_floors_at_zero() -> None:
    conf = derive_confidence(
        evidence_count=0, evidence_scope="assistant",
        evidence_quote="", confirmation_signal="corrected",
    )
    assert conf == 0.2  # BASE 0.4 - 0.2；若再低则封底 0.0


def test_never_full_confidence() -> None:
    conf = derive_confidence(
        evidence_count=5, evidence_scope="user",
        evidence_quote=LONG_QUOTE, confirmation_signal="adopted",
    )
    assert conf == CAP
