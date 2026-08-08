"""Spike 002: typed Node/Python protocol, idempotency, cancel and recovery."""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

from ledger import Authority, TaskLedger, ToolRequest, execute_request


def request(task_key: str = "source:v1:wm0-wm1:skill:policy") -> ToolRequest:
    return ToolRequest(
        task_id="task-001",
        tool_call_id="tool-001",
        idempotency_key=task_key,
        schema_version="personal_domain_tool_request_v1",
        task_key=task_key,
        deadline_ms=1000,
        args={"source_cutoff": "wm1", "scope": "synthetic"},
    )


def main() -> None:
    evidence: dict[str, object] = {"schema": "personal_domain_tool_request_v1"}
    authority_before = Authority().fingerprint()
    with tempfile.TemporaryDirectory(prefix="spike-002-") as temp:
        db = Path(temp) / "ledger.sqlite"
        ledger = TaskLedger(db)
        req = request()
        candidate = {"task_id": req.task_id, "source_cutoff": "wm1", "evidence_refs": ["ev-1"], "uncertainty": 0.2}

        first = execute_request(ledger, req, candidate)
        replay = execute_request(TaskLedger(db), req, candidate)
        conflict_req = ToolRequest(**{**req.__dict__, "args": {"source_cutoff": "wm2"}})
        conflict = execute_request(TaskLedger(db), conflict_req, candidate)
        assert first["status"] == "succeeded", first
        assert replay["status"] == "replay" and replay["state"] == "succeeded", replay
        assert conflict["status"] == "error" and conflict["error"]["code"] == "typed_conflict", conflict
        evidence["idempotency"] = {"first": first, "replay": replay, "conflict_code": conflict["error"]["code"]}

        cancel_req = request("source:v1:wm0-wm2:cancel")
        cancel = threading.Event()
        cancel.set()
        cancelled = execute_request(ledger, cancel_req, candidate, cancel=cancel)
        assert cancelled["status"] == "error" and cancelled["error"]["code"] == "cancelled", cancelled
        assert ledger.task_state(cancel_req.task_key) == "cancelled"
        evidence["cancel"] = cancelled

        unknown_req = request("source:v1:wm0-wm3:unknown")
        unknown = execute_request(ledger, unknown_req, candidate, crash_after_candidate=True)
        restarted = TaskLedger(db)
        retry_unknown = execute_request(restarted, unknown_req, candidate)
        assert unknown["error"]["code"] == "outcome_unknown", unknown
        assert retry_unknown["error"]["code"] == "outcome_unknown", retry_unknown
        assert restarted.count("candidates") == 2, restarted.count("candidates")
        evidence["unknown_outcome"] = {"first": unknown, "after_restart": retry_unknown, "candidate_rows": restarted.count("candidates")}

        claim_req = request("source:v1:wm0-wm4:claim")
        ledger.enqueue(claim_req)
        barrier = threading.Barrier(3)
        claims: list[dict[str, object]] = []
        claim_lock = threading.Lock()

        def claim_once() -> None:
            barrier.wait()
            result = TaskLedger(db).claim(claim_req.task_key)
            with claim_lock:
                claims.append(result)

        workers = [threading.Thread(target=claim_once) for _ in range(2)]
        for worker in workers:
            worker.start()
        barrier.wait()
        for worker in workers:
            worker.join()
        assert sum(result["status"] == "claimed" for result in claims) == 1, claims
        assert sum(result["status"] == "busy" for result in claims) == 1, claims
        evidence["concurrent_claim"] = claims

        authority_after = Authority().fingerprint()
        assert authority_before == authority_after
        evidence["authority_unchanged"] = authority_before == authority_after
        evidence["ledger_counts"] = {table: ledger.count(table) for table in ("tasks", "candidates", "transitions")}

    print(json.dumps(evidence, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
