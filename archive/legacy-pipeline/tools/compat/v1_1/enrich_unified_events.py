# =============================================================================
# DEPRECATED — 死代码（PDA-2 旧管线关闭）
# Compatibility shim，转发至已归档的 personal_knowledge.application.enrich_unified_events
# （引用已删除的 Agent 旧路径）。勿调用。
# =============================================================================

"""Compatibility shim -> pipeline.enrich_unified_events

Legacy CLI: python integration/scripts/enrich_unified_events.py
Preferred:  python -m pipeline.enrich_unified_events
"""
from __future__ import annotations

from importlib import import_module
import sys

_real = import_module("personal_knowledge.application.enrich_unified_events")

if __name__ == "__main__":
    # Do not rebind __main__; invoke real entrypoint cleanly.
    if hasattr(_real, "main") and callable(getattr(_real, "main")):
        raise SystemExit(_real.main())
    import runpy
    raise SystemExit(runpy.run_module("personal_knowledge.application.enrich_unified_events", run_name="__main__"))

# When imported as legacy top-level name, rebind so private symbols work.
sys.modules[__name__] = _real
