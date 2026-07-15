"""Stable console entry points during the Phase 19 source transition."""

from __future__ import annotations

import importlib
import inspect
import asyncio
import sys
from pathlib import Path


def _entry_main(canonical: str, legacy: str, function: str = "main") -> object:
    try:
        target = importlib.import_module(canonical)
        result = getattr(target, function)()
        return asyncio.run(result) if inspect.isawaitable(result) else result
    except ModuleNotFoundError as exc:
        if not (exc.name == canonical or canonical.startswith(f"{exc.name}.")):
            raise
    scripts = Path(__file__).resolve().parents[2] / "integration" / "scripts"
    if not scripts.is_dir():
        raise RuntimeError("legacy scripts tree is unavailable; install the consolidated package")
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    target = importlib.import_module(legacy)
    result = getattr(target, function)()
    return asyncio.run(result) if inspect.isawaitable(result) else result


def _help(command: str, description: str) -> bool:
    if not any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        return False
    print(f"usage: {command} [options]\n\n{description}")
    return True


def pipeline() -> object:
    if _help("rag-pipeline", "Run the personal knowledge ingestion pipeline."):
        return 0
    return _entry_main("personal_knowledge.application.run_pipeline", "pipeline.run_pipeline")


def search() -> object:
    if _help("rag-search", "Search the consolidated personal knowledge index."):
        return 0
    return _entry_main("personal_knowledge.retrieval.unified_search", "vector.unified_search", "_cli")


def api() -> object:
    if _help("rag-api", "Run the local personal knowledge REST API."):
        return 0
    return _entry_main("personal_knowledge.services.api_server", "services.api_server")


def mcp() -> object:
    if _help("rag-mcp", "Run the personal knowledge MCP stdio server."):
        return 0
    return _entry_main("personal_knowledge.services.mcp_server", "services.mcp_server")


def dashboard() -> object:
    if _help("rag-dashboard", "Run the local personal knowledge dashboard."):
        return 0
    return _entry_main("personal_knowledge.services.dashboard", "services.dashboard")
