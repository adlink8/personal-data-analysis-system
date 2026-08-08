"""Spike 008: metadata-only retention and expiry independent from authority."""

from __future__ import annotations

import json
import re
import tempfile
import time
from pathlib import Path


SECRET = re.compile(r"(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]+|password\s*=)", re.I)


def safe_event(event: dict[str, object]) -> dict[str, object]:
    encoded = json.dumps(event, sort_keys=True)
    if SECRET.search(encoded) or "raw_body" in event or "provider_payload" in event:
        raise ValueError("privacy_violation")
    return {key: event[key] for key in ("event_id", "task_id", "category", "timestamp", "expires_at") if key in event}


def main() -> None:
    now = time.time()
    with tempfile.TemporaryDirectory(prefix="spike-008-") as temp:
        root = Path(temp)
        authority = root / "authority.json"
        authority.write_text(json.dumps({"watermark": "wm-1", "active": "active-1"}), encoding="utf-8")
        session = root / "session.jsonl"
        crash = root / "crash.json"
        session.write_text(json.dumps(safe_event({"event_id": "evt-1", "task_id": "task-8", "category": "tool", "timestamp": now - 100, "expires_at": now - 1})) + "\n", encoding="utf-8")
        crash.write_text(json.dumps({"kind": "metadata", "expires_at": now - 1}), encoding="utf-8")
        rejected_secret = False
        try:
            safe_event({"event_id": "bad", "task_id": "task-8", "secret": "sk-123456789"})
        except ValueError:
            rejected_secret = True
        for path in (session, crash):
            if json.loads(path.read_text(encoding="utf-8")).get("expires_at", now) < now:
                path.unlink()
        report = {
            "session_expired": not session.exists(),
            "crash_expired": not crash.exists(),
            "authority_survives": authority.exists(),
            "secret_write_rejected": rejected_secret,
            "raw_body_logged": False,
            "remaining_files": sorted(path.name for path in root.iterdir()),
        }
        assert all(report[key] for key in ("session_expired", "crash_expired", "authority_survives", "secret_write_rejected"))
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
