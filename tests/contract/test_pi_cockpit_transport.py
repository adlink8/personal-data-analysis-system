from __future__ import annotations

from personal_knowledge.services.pi_runtime_projection import PI_COCKPIT_SCHEMA, mutate_task, safe_event


def test_event_projection_is_metadata_only():
    event = safe_event({"event_id": "e1", "task_id": "t1", "session_id": "s1", "state": "running", "version": 2, "prompt": "secret prompt", "completion": "secret result", "provider_body": "secret"})
    assert event["schema_version"] == PI_COCKPIT_SCHEMA
    assert all(key not in event for key in ("prompt", "completion", "provider_body", "credentials", "path"))


def test_stale_and_cross_origin_like_mutations_are_zero_write():
    stale = mutate_task("cancel", {"task_id": "t-stale", "expected_version": 1, "idempotency_key": "i1"})
    assert stale["ok"] is False and stale["error"]["code"] == "stale_task_version"
    ok = mutate_task("cancel", {"task_id": "t-stale", "expected_version": 0, "idempotency_key": "i2"})
    assert ok["ok"] is True and ok["data"]["state"] == "cancel_requested"
    stale_again = mutate_task("resume", {"task_id": "t-stale", "expected_version": 0, "idempotency_key": "i3"})
    assert stale_again["ok"] is False
