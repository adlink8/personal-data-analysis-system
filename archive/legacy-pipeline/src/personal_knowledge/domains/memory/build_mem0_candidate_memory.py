# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# Re-export facade，转发至已归档的 application/memory/build_mem0_candidate_memory.py
# （mem0 实验已在 Phase 07 降级，不在主路径）。勿调用。
# =============================================================================

"""Re-export facade — retained for backward compatibility during the 2026-08-13 cleanup window.
Canonical location: application/memory/build_mem0_candidate_memory.py
Do not add new logic here; import from the canonical path in new code.
"""
from importlib import import_module as _import_module
import sys as _sys

_canonical = _import_module("personal_knowledge.application.memory.build_mem0_candidate_memory")
_sys.modules[__name__] = _canonical
