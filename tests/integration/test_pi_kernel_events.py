from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import time
from http.client import HTTPConnection

import pytest

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


# ---------------------------------------------------------------------------
# Plan 61-12 Task 1 extension: recovery-route truthfulness (T-61-VERIFY-02).
#
# cancel / resume / outcome_unknown reconcile must NEVER claim success before an
# actual reconciliation happens. Every recovery route below runs against the
# real Kernel server subprocess; none of them touches activation/promotion/
# rollback/pointer authority, none makes a paid call, and every rejection body
# stays metadata-only (no success claim, no prompt/credential/raw-body leak).
# ---------------------------------------------------------------------------

def _assert_no_success_claim(body: str) -> None:
    """A recovery rejection may not present itself as success."""
    assert json.loads(body)["ok"] is False
    assert "succeeded" not in body
    assert "success" not in body


def test_recovery_routes_reject_without_actual_reconciliation(tmp_path: Path) -> None:
    """cancel/resume/reconcile fail closed for unknown tasks and invalid states."""
    before = _fingerprints()
    server = _Server(tmp_path)
    try:
        cancel = _request(server, "POST", "/v1/conversations/cancel", {
            "task_id": "pi_task_nonexistent_0001",
            "idempotency_key": "idem:cancel:none:1",
        })
        assert cancel[0] == 400
        assert json.loads(cancel[1]) == {"ok": False, "error": {"code": "task_not_found"}}
        _assert_no_success_claim(cancel[1])

        for label, body in (
            ("invalid reconcile state", {"task_id": "pi_task_nonexistent_0001", "state": "succeeded_now",
                                         "idempotency_key": "idem:reconcile:bad:1"}),
            ("missing reconcile state", {"task_id": "pi_task_nonexistent_0001",
                                         "idempotency_key": "idem:reconcile:none:1"}),
        ):
            status, text = _request(server, "POST", "/v1/conversations/reconcile", body)
            assert status == 400, label
            assert json.loads(text)["error"]["code"] == "task_reconcile_state_required", label
            _assert_no_success_claim(text)

        resume = _request(server, "POST", "/v1/conversations/resume", {
            "task_id": "pi_task_nonexistent_0001",
            "state": "succeeded",
            "idempotency_key": "idem:resume:none:1",
        })
        assert resume[0] == 400
        assert json.loads(resume[1])["ok"] is False
        _assert_no_success_claim(resume[1])

        # Nothing was enqueued and no task was fabricated by the failed recovery.
        assert json.loads(_request(server, "GET", "/v1/tasks")[1])["tasks"] == []
    finally:
        server.stop()
    assert _fingerprints() == before


def test_recovery_rejections_never_append_success_events_or_false_cursor(tmp_path: Path) -> None:
    """Failed cancel/reconcile attempts append no success lifecycle event."""
    server = _Server(tmp_path)
    event = _event(1)
    try:
        status, _ = _request(server, "POST", "/v1/events", event)
        assert status == 201

        for _ in range(2):
            _request(server, "POST", "/v1/conversations/cancel", {
                "task_id": "pi_task_nonexistent_0001", "idempotency_key": "idem:cancel:replay:1",
            })
            _request(server, "POST", "/v1/conversations/reconcile", {
                "task_id": "pi_task_nonexistent_0001", "state": "succeeded",
                "idempotency_key": "idem:reconcile:replay:1",
            })

        # SSE cursor truth: only the single real event replays; no fabricated
        # task_completed / success event may appear in the stream.
        stream = _sse_after(server, "", event["event_id"])
        assert stream.count(f"id: {event['event_id']}") == 1
        assert "task_completed" not in stream
        assert "succeeded" not in stream
    finally:
        server.stop()


@pytest.fixture
def replay_server(tmp_path: Path):
    """Real Kernel subprocess pinned to the deterministic zero-paid replay
    provider, so a real task completes without any paid/network call and its
    recovery truth can be asserted deterministically."""
    previous = os.environ.get("PI_PROVIDER_MODE")
    os.environ["PI_PROVIDER_MODE"] = "replay"
    server = _Server(tmp_path)
    yield server
    server.stop()
    if previous is None:
        os.environ.pop("PI_PROVIDER_MODE", None)
    else:
        os.environ["PI_PROVIDER_MODE"] = previous


def test_replay_task_recovery_never_claims_false_success(replay_server) -> None:
    """A real succeeded replay task can never be cancelled or blind-reconciled.

    This is the T-61-VERIFY-02 guard: a success state must be earned by the
    real lifecycle; cancel/resume/reconcile over a non-resumable task fail
    closed instead of reporting a fabricated success.
    """
    status, body = _request(replay_server, "POST", "/v1/tasks", {
        "task_id": "pi_task_replay_recovery_0001",
        "idempotency_key": "idem:replay:recovery:1",
        "prompt": "redacted replay recovery prompt",
    })
    assert status == 201
    payload = json.loads(body)
    assert payload["ok"] is True
    assert payload["task"]["state"] == "succeeded"
    assert payload["receipt"]["response_checksum"]
    version = payload["task"]["version"]

    # A succeeded task is not cancelable.
    cancel = _request(replay_server, "POST", "/v1/conversations/cancel", {
        "task_id": "pi_task_replay_recovery_0001", "expected_version": version,
        "idempotency_key": "idem:replay:cancel:1",
    })
    assert cancel[0] == 400
    assert json.loads(cancel[1])["error"]["code"] == "task_not_cancelable"
    _assert_no_success_claim(cancel[1])

    # outcome_unknown reconcile requires an actual outcome_unknown task; a
    # succeeded task is never re-resolved to a new success claim.
    reconcile = _request(replay_server, "POST", "/v1/conversations/reconcile", {
        "task_id": "pi_task_replay_recovery_0001", "expected_version": version,
        "state": "succeeded", "idempotency_key": "idem:replay:reconcile:1",
    })
    assert reconcile[0] == 400
    assert json.loads(reconcile[1])["error"]["code"] == "task_not_resumable"
    _assert_no_success_claim(reconcile[1])

    # The task state is unchanged: the ledger still reports the one real success.
    status, body = _request(replay_server, "GET", "/v1/tasks/pi_task_replay_recovery_0001")
    assert status == 200
    assert json.loads(body)["task"]["state"] == "succeeded"
