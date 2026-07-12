"""Compatibility shim -> graph.build_graph_relation_candidates_v2

Legacy CLI: python integration/scripts/build_graph_relation_candidates_v2.py
Preferred:  python -m graph.build_graph_relation_candidates_v2
"""
from __future__ import annotations

from importlib import import_module
import sys

_real = import_module("graph.build_graph_relation_candidates_v2")

if __name__ == "__main__":
    # Do not rebind __main__; invoke real entrypoint cleanly.
    if hasattr(_real, "main") and callable(getattr(_real, "main")):
        raise SystemExit(_real.main())
    import runpy
    raise SystemExit(runpy.run_module("graph.build_graph_relation_candidates_v2", run_name="__main__"))

# When imported as legacy top-level name, rebind so private symbols work.
sys.modules[__name__] = _real
