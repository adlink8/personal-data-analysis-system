"""Same-origin, metadata-only Pi runtime projection for the Cockpit."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

PI_COCKPIT_SCHEMA = "pi_cockpit_event_v1"
SAFE_STATES = {"queued", "claimed", "running", "cancel_requested", "succeeded", "failed", "outcome_unknown", "offline", "stale"}
_TASKS: dict[str, dict[str, Any]] = {}

def _now() -> str: return datetime.now(timezone.utc).isoformat()

def safe_event(event: Mapping[str, Any]) -> dict[str, Any]:
    state = str(event.get("state") or "unknown")
    if state not in SAFE_STATES: state = "stale"
    return {"schema_version": PI_COCKPIT_SCHEMA, "event_id": str(event.get("event_id") or ""), "task_id": str(event.get("task_id") or ""), "session_id": str(event.get("session_id") or ""), "state": state, "version": int(event.get("version") or 0), "progress": max(0, min(100, int(event.get("progress") or 0))), "tool_label": str(event.get("tool_label") or ""), "evidence_refs": list(event.get("evidence_refs") or [])[:20], "recovery_action": str(event.get("recovery_action") or "inspect_status"), "observed_at": str(event.get("observed_at") or _now())}

def kernel_status() -> dict[str, Any]:
    return {"schema_version": PI_COCKPIT_SCHEMA, "service": "pi-kernel", "state": "ready", "host": "127.0.0.1", "port": 8790, "provider_calls": 0, "observed_at": _now(), "recovery_action": "none"}

def task_list() -> list[dict[str, Any]]: return [safe_event(task) for task in _TASKS.values()]

def mutate_task(action: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    task_id = str(payload.get("task_id") or "")
    if not task_id or not payload.get("idempotency_key"): return {"ok": False, "error": {"code": "task_identity_required"}}
    current = _TASKS.get(task_id, {"task_id": task_id, "version": 0, "state": "queued"})
    if int(payload.get("expected_version", -1)) != int(current.get("version", 0)): return {"ok": False, "error": {"code": "stale_task_version"}}
    if action == "cancel" and current["state"] not in {"queued", "claimed", "running"}: return {"ok": False, "error": {"code": "task_not_cancelable"}}
    if action == "resume" and current["state"] != "outcome_unknown": return {"ok": False, "error": {"code": "task_not_resumable"}}
    current = dict(current); current["state"] = "cancel_requested" if action == "cancel" else "queued"; current["version"] = int(current["version"]) + 1; current["observed_at"] = _now(); _TASKS[task_id] = current
    return {"ok": True, "data": safe_event(current)}

__all__ = ["PI_COCKPIT_SCHEMA", "kernel_status", "safe_event", "task_list", "mutate_task"]
