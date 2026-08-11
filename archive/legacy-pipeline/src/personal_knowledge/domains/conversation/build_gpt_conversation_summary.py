# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# Re-export facade，转发至已归档的 application/conversation/build_gpt_conversation_summary.py
# （该 canonical 模块引用已删除的 GPT 旧路径）。勿调用。
# =============================================================================

"""Re-export facade — retained for backward compatibility during the 2026-08-13 cleanup window.
Canonical location: application/conversation/build_gpt_conversation_summary.py
Do not add new logic here; import from the canonical path in new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_canonical = _import_module("personal_knowledge.application.conversation.build_gpt_conversation_summary")
_sys.modules[__name__] = _canonical
