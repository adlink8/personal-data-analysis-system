# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# Compatibility shim，转发至已归档的 domains/memory/build_mem0_candidate_memory
# （mem0 实验已在 Phase 07 降级，不在主路径）。勿调用。
# =============================================================================

"""Compatibility shim -> memory.build_mem0_candidate_memory

Legacy CLI: python integration/scripts/build_mem0_candidate_memory.py
Preferred:  python -m memory.build_mem0_candidate_memory
"""
from __future__ import annotations

from importlib import import_module
import sys

_real = import_module("personal_knowledge.domains.memory.build_mem0_candidate_memory")

if __name__ == "__main__":
    # Do not rebind __main__; invoke real entrypoint cleanly.
    if hasattr(_real, "main") and callable(getattr(_real, "main")):
        raise SystemExit(_real.main())
    import runpy
    raise SystemExit(runpy.run_module("personal_knowledge.domains.memory.build_mem0_candidate_memory", run_name="__main__"))

# When imported as legacy top-level name, rebind so private symbols work.
sys.modules[__name__] = _real
