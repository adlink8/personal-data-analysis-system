"""Cross-process proof that Python production adapters are Pi-owned."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

from personal_knowledge.intelligence.analysis.providers import PiKernelProvider, ProviderRequest


ROOT = Path(__file__).resolve().parents[2]
NODE = "node"


def _read_listening(process: subprocess.Popen[str]) -> int:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        line = process.stdout.readline() if process.stdout is not None else ""
        if not line:
            if process.poll() is not None:
                raise AssertionError(process.stderr.read() if process.stderr else "kernel exited")
            time.sleep(0.05)
            continue
        payload = json.loads(line)
        if payload.get("event") == "listening":
            return int(payload["port"])
    raise AssertionError("kernel did not become ready")


def test_python_pi_provider_persists_task_session_event_and_candidate() -> None:
    with tempfile.TemporaryDirectory(prefix="pi-python-bridge-") as raw_dir:
        directory = Path(raw_dir)
        decision = directory / "decision.json"
        decision.write_text(json.dumps({
            "schema": "pi-package-decision-v1",
            "run_id": "piq_f7896e839999ed2eac87ebd4",
            "status": "accepted",
            "accepted": True,
            "expiry": "2099-01-01T00:00:00.000Z",
        }), encoding="utf-8")
        capability = "cross-process-test-capability"
        env = os.environ.copy()
        env.update({
            "PI_KERNEL_INTERNAL_CAPABILITY": capability,
            "PI_PROVIDER_MODE": "replay",
            "PI_KERNEL_URL": "http://127.0.0.1:8790",
        })
        process = subprocess.Popen(
            [
                NODE, "apps/personal_intelligence_kernel/src/server.mjs",
                "--port", "0", "--provider-mode", "replay",
                "--project-root", str(ROOT), "--decision-path", str(decision),
                "--database-path", str(directory / "events.sqlite"),
                "--cwd", str(directory), "--agent-dir", str(directory / "agent"),
            ],
            cwd=ROOT, env=env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        try:
            port = _read_listening(process)
            provider = PiKernelProvider(
                purpose="structured_analysis",
                base_url=f"http://127.0.0.1:{port}",
                capability=capability,
            )
            request = ProviderRequest(
                prompt="return json; private prompt must not be persisted",
                request_checksum="a" * 64,
                temperature=0,
                max_output_tokens=128,
                timeout_seconds=10,
            )
            result = provider.generate(request)
            staged = provider.stage_candidate(
                candidate_id="pi_cross_candidate_001",
                proposal={"kind": "analysis_candidate", "status": "pending"},
                evidence_refs=[{"ref": "artifact:e1", "checksum": "b" * 64}],
                candidate_checksum=result.response_checksum,
                run_checksum="c" * 64,
            )
            assert result.telemetry.provider == "replay"
            assert staged["ok"] is True

            for name in ("events", "pi_kernel_tasks", "pi_kernel_sessions", "pi_kernel_candidates"):
                assert (directory / f"{name}.sqlite").exists(), name
            for db_name, query, expected in (
                ("events.sqlite", "SELECT COUNT(*) FROM pi_kernel_events", 4),
                ("pi_kernel_sessions.sqlite", "SELECT COUNT(*) FROM pi_kernel_session_receipts", 2),
                ("pi_kernel_candidates.sqlite", "SELECT COUNT(*) FROM pi_kernel_candidates", 1),
            ):
                con = sqlite3.connect(directory / db_name)
                try:
                    assert con.execute(query).fetchone()[0] == expected
                finally:
                    con.close()
            con = sqlite3.connect(directory / "pi_kernel_tasks.sqlite")
            try:
                assert con.execute("SELECT state FROM pi_kernel_tasks").fetchone()[0] == "succeeded"
            finally:
                con.close()
            assert "return json" not in (directory / "events.sqlite").read_bytes().decode("utf-8", errors="ignore")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    sys.exit(0)
