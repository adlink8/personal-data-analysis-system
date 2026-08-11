# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# Compatibility shim，转发至已归档的 domains/conversation/build_conversation_segments
# （引用已删除的 Agent/GPT 旧路径）。勿调用。
# =============================================================================

"""Compatibility shim -> conversation.build_conversation_segments

Legacy CLI: python integration/scripts/build_conversation_segments.py
Preferred:  python -m conversation.build_conversation_segments
"""
from __future__ import annotations

from importlib import import_module
import sys

_real = import_module("personal_knowledge.domains.conversation.build_conversation_segments")

if __name__ == "__main__":
    # Do not rebind __main__; invoke real entrypoint cleanly.
    if hasattr(_real, "main") and callable(getattr(_real, "main")):
        raise SystemExit(_real.main())
    import runpy
    raise SystemExit(runpy.run_module("personal_knowledge.domains.conversation.build_conversation_segments", run_name="__main__"))

# When imported as legacy top-level name, rebind so private symbols work.
sys.modules[__name__] = _real
