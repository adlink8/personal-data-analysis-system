from __future__ import annotations

import json
from pathlib import Path
import socket
import time
from http.client import HTTPConnection

from tests.contract.test_pi_kernel_host import _Server, _event, _fingerprints, _request


ROOT = Path(__file__).resolve().parents[2]


def _sse_after(server: _Server, cursor: str, expected_id: str) -> str:
    connection = HTTPConnection("127.0.0.1", server.port, timeout=5)
    connection.request("GET", "/v1/events/stream", headers={"Last-Event-ID": cursor})
    response = connection.getresponse()
    assert response.status == 200
    chunks = []
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        chunk = response.read(1)
        if not chunk:
            break
        chunks.append(chunk)
        if expected_id.encode() in b"".join(chunks):
            break
    connection.close()
    return b"".join(chunks).decode()


def test_restart_replay_cursor_and_exact_idempotency(tmp_path: Path) -> None:
    before = _fingerprints()
    first_server = _Server(tmp_path)
    first = _event(1)
    try:
        status, body = _request(first_server, "POST", "/v1/events", first)
        assert status == 201
        assert json.loads(body)["event_id"] == first["event_id"]
        status, duplicate_body = _request(first_server, "POST", "/v1/events", first)
        assert status == 200
        assert json.loads(duplicate_body)["status"] == "duplicate"
    finally:
        first_server.stop()

    restarted = _Server(tmp_path)
    second = _event(2, "tool_started")
    try:
        status, body = _request(restarted, "POST", "/v1/events", second)
        assert status == 201
        stream = _sse_after(restarted, first["event_id"], second["event_id"])
        assert stream.count(f"id: {second['event_id']}") == 1
        assert first["event_id"] not in stream
        assert "heartbeat" in stream or "kernel-event" in stream
    finally:
        restarted.stop()
    assert _fingerprints() == before


def test_forced_kill_preserves_durable_journal_and_port_can_restart(tmp_path: Path) -> None:
    server = _Server(tmp_path)
    first = _event(1)
    status, _ = _request(server, "POST", "/v1/events", first)
    assert status == 201
    port = server.port
    server.stop(force=True)

    restarted = _Server(tmp_path)
    try:
        assert restarted.port != 0
        status, body = _request(restarted, "POST", "/v1/events", first)
        assert status == 200
        assert json.loads(body)["status"] == "duplicate"
    finally:
        restarted.stop()


def test_sse_cursor_errors_and_heartbeat_are_bounded(tmp_path: Path) -> None:
    server = _Server(tmp_path)
    try:
        status, body = _request(server, "GET", "/v1/events/stream", headers={"Last-Event-ID": "credential-path-body"})
        assert status == 400
        assert json.loads(body) == {"ok": False, "error": {"code": "cursor_invalid"}}
        assert "credential-path-body" not in body
    finally:
        server.stop()
