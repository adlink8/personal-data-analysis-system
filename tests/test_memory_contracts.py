"""记忆查询契约测试。

覆盖 core / CLI / REST / MCP 四层入口。

运行:
  python tests\test_memory_contracts.py
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "统合模块" / "脚本"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import unified_search as us  # noqa: E402


def _run_json_command(args: list[str]) -> dict:
    """运行 CLI 并读取 JSON stdout。"""
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return json.loads(proc.stdout)


def _http_json(url: str) -> dict:
    """GET 一个本地 HTTP 接口并解析 JSON。"""
    with urllib.request.urlopen(url, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def _find_free_port() -> int:
    """找一个本地临时端口。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_http(url: str, timeout: float = 15.0) -> None:
    """等待本地服务起来。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.2)
    raise TimeoutError(f"service not ready: {url}")


class ApiServerProcess:
    """测试用临时 API 进程,退出时显式清理。"""
    def __init__(self) -> None:
        self.port = _find_free_port()
        self.proc: subprocess.Popen[str] | None = None

    def __enter__(self) -> "ApiServerProcess":
        env = os.environ.copy()
        self.proc = subprocess.Popen(
            [
                sys.executable,
                str(SCRIPTS_DIR / "api_server.py"),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
        _wait_for_http(f"http://127.0.0.1:{self.port}/health")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.proc is None:
            return
        self.proc.terminate()
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=5)
        for stream in (self.proc.stdout, self.proc.stderr):
            if stream is not None:
                stream.close()


def _profile_contract(data: dict) -> dict:
    """提取 profile contract 的最小比较形状。"""
    items = data.get("items") or []
    return {
        "ok": bool(data.get("ok")),
        "available": bool(data.get("available")),
        "count": int(data.get("count", -1)),
        "memory_type": (data.get("filter") or {}).get("memory_type"),
        "item_ids": [item.get("memory_id") for item in items],
    }


def _subject_contract(data: dict) -> dict:
    """提取 subject contract 的最小比较形状。"""
    memory = data.get("memory") or {}
    relations = data.get("relations") or []
    neighbors = data.get("neighbors") or {}
    return {
        "ok": bool(data.get("ok")),
        "count": int(data.get("count", -1)),
        "memory_id": memory.get("memory_id"),
        "subject": memory.get("subject"),
        "relation_count": len(relations),
        "neighbor_count": int(neighbors.get("count", 0)),
    }


class MemoryContractTests(unittest.TestCase):
    maxDiff = None

    def test_core_and_cli_profile_contract_match(self) -> None:
        core = us.get_memory_profile(memory_type="tooling", limit=2)
        cli = _run_json_command(
            [
                str(SCRIPTS_DIR / "unified_search.py"),
                "memory",
                "--type",
                "tooling",
                "--limit",
                "2",
                "--json",
            ]
        )
        self.assertEqual(_profile_contract(core), _profile_contract(cli))

    def test_core_and_cli_subject_contract_match(self) -> None:
        core = us.get_memory_by_subject("Codex")
        self.assertIsNotNone(core)
        assert core is not None
        core["neighbors"] = us.get_memory_neighbors("Codex", 1)
        cli = _run_json_command(
            [
                str(SCRIPTS_DIR / "unified_search.py"),
                "memory",
                "--subject",
                "Codex",
                "--neighbors",
                "1",
                "--json",
            ]
        )
        self.assertEqual(_subject_contract(core), _subject_contract(cli))

    def test_rest_profile_and_subject_contract_match_core(self) -> None:
        core_profile = us.get_memory_profile(memory_type="tooling", limit=2)
        core_subject = us.get_memory_by_subject("Codex")
        self.assertIsNotNone(core_subject)
        assert core_subject is not None
        core_subject["neighbors"] = us.get_memory_neighbors("Codex", 1)

        with ApiServerProcess() as api:
            profile_url = (
                f"http://127.0.0.1:{api.port}/memory?"
                + urllib.parse.urlencode({"type": "tooling", "limit": 2})
            )
            subject_url = (
                f"http://127.0.0.1:{api.port}/memory/"
                + urllib.parse.quote("Codex")
                + "?"
                + urllib.parse.urlencode({"neighbors": 1})
            )
            profile_data = _http_json(profile_url)
            subject_data = _http_json(subject_url)

        self.assertTrue(profile_data["ok"])
        self.assertTrue(subject_data["ok"])
        self.assertEqual(_profile_contract(core_profile), _profile_contract(profile_data["data"]))
        self.assertEqual(_subject_contract(core_subject), _subject_contract(subject_data["data"]))

    def test_mcp_memory_tools_are_exposed_and_callable(self) -> None:
        async def _run() -> tuple[list[str], str, str]:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client

            params = StdioServerParameters(
                command=sys.executable,
                args=[str(SCRIPTS_DIR / "mcp_server.py")],
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    profile = await session.call_tool(
                        "get_memory_profile",
                        {"memory_type": "tooling", "limit": 2},
                    )
                    subject = await session.call_tool(
                        "get_memory_by_subject",
                        {"subject": "Codex", "neighbors": 1},
                    )
                    return (
                        [tool.name for tool in tools.tools],
                        profile.content[0].text,
                        subject.content[0].text,
                    )

        tool_names, profile_text, subject_text = asyncio.run(_run())
        self.assertIn("get_memory_profile", tool_names)
        self.assertIn("get_memory_by_subject", tool_names)
        self.assertIn("记忆总数", profile_text)
        self.assertIn("Codex", subject_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
