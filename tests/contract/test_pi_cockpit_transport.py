from __future__ import annotations

import personal_knowledge.services.pi_runtime_projection as projection
from personal_knowledge.services.pi_runtime_projection import PI_COCKPIT_SCHEMA, mutate_task, safe_event


def test_event_projection_is_metadata_only():
    event = safe_event({"event_id": "e1", "task_id": "t1", "session_id": "s1", "state": "running", "version": 2, "prompt": "secret prompt", "completion": "secret result", "provider_body": "secret"})
    assert event["schema_version"] == PI_COCKPIT_SCHEMA
    assert all(key not in event for key in ("prompt", "completion", "provider_body", "credentials", "path"))


def test_stale_and_cross_origin_like_mutations_are_zero_write(monkeypatch):
    def fake_request(method, path, payload=None):
        assert method == "POST"
        if path.endswith("/cancel") and payload["expected_version"] == 0:
            return 200, {"ok": True, "task": {"task_id": "t-stale", "state": "cancel_requested", "version": 1}}
        return 409, {"ok": False, "error": {"code": "stale_version"}}

    monkeypatch.setattr(projection, "_request_json", fake_request)
    stale = mutate_task("cancel", {"task_id": "t-stale", "expected_version": 1, "idempotency_key": "i1"})
    assert stale["ok"] is False and stale["error"]["code"] == "stale_version"
    ok = mutate_task("cancel", {"task_id": "t-stale", "expected_version": 0, "idempotency_key": "i2"})
    assert ok["ok"] is True and ok["data"]["state"] == "cancel_requested"
    stale_again = mutate_task("resume", {"task_id": "t-stale", "expected_version": 0, "idempotency_key": "i3"})
    assert stale_again["ok"] is False


def test_kernel_unreachable_is_typed_offline(monkeypatch):
    monkeypatch.setattr(projection, "_request_json", lambda *args, **kwargs: (0, {}))
    status = projection.kernel_status()
    assert status["state"] == "offline"
    result = mutate_task("cancel", {"task_id": "t-offline", "expected_version": 1, "idempotency_key": "i-offline"})
    assert result == {"ok": False, "error": {"code": "kernel_offline"}}
