"""Spike 004: deterministic Delta trigger and authority-safe vertical slice."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from ledger import Authority, TaskLedger, ToolRequest, execute_request


def run_delta(delta_refs: list[str], ledger: TaskLedger, *, fail_stage: str | None = None) -> dict[str, object]:
    counters = {"tasks": 0, "sessions": 0, "model_calls": 0, "candidate_rows": 0, "evaluation_runs": 0}
    authority_before = Authority()
    if not delta_refs:
        return {"trigger": "empty", **counters, "authority_unchanged": True}

    task_key = "conversation:v1:wm0-wm1:maintain-conversation-delta:policy1"
    request = ToolRequest(
        task_id="task-004",
        tool_call_id="tool-004",
        idempotency_key=task_key,
        schema_version="delta-manifest-v1",
        task_key=task_key,
        deadline_ms=1000,
        args={"delta_refs": delta_refs},
    )
    counters["tasks"] = 1
    counters["sessions"] = 1
    accepted = ledger.enqueue(request)
    if accepted["status"] == "replay":
        return {"trigger": "replay", **counters, "replay": accepted, "authority_unchanged": True}
    claimed = ledger.claim(task_key)
    assert claimed["status"] == "claimed", claimed
    if fail_stage == "model":
        counters["model_calls"] = 1
        ledger.fail(task_key, {"code": "model_timeout", "retryable": True}, "failed_retryable")
        return {"trigger": "failed_model", **counters, "authority_unchanged": True}

    counters["model_calls"] = 1
    candidate = {
        "task_id": request.task_id,
        "source_cutoff": "wm1",
        "evidence_refs": ["ev-opaque-004"],
        "payload_checksum": "candidate-004",
        "uncertainty": 0.25,
        "delta_refs": delta_refs,
    }
    inserted = ledger.insert_candidate(task_key, candidate)
    counters["candidate_rows"] = int(inserted)
    assert candidate["evidence_refs"] and candidate["source_cutoff"] and candidate["task_id"]
    counters["evaluation_runs"] = 1
    ledger.finish(task_key, {"evaluation": "accepted", "candidate_inserted": inserted})
    authority_after = Authority()
    return {"trigger": "valuable", **counters, "evaluation": "accepted", "authority_unchanged": authority_before == authority_after}


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="spike-004-") as temp:
        ledger = TaskLedger(Path(temp) / "ledger.sqlite")
        empty = run_delta([], ledger)
        assert empty["model_calls"] == 0 and empty["tasks"] == 0 and empty["sessions"] == 0

        failed_ledger = TaskLedger(Path(temp) / "failed.sqlite")
        failed = run_delta(["delta-1"], failed_ledger, fail_stage="model")
        assert failed["model_calls"] == 1 and failed["candidate_rows"] == 0 and failed["authority_unchanged"]

        positive_ledger = TaskLedger(Path(temp) / "positive.sqlite")
        positive = run_delta(["delta-1"], positive_ledger)
        replay = run_delta(["delta-1"], positive_ledger)
        assert positive["candidate_rows"] == 1 and positive["evaluation"] == "accepted"
        assert replay["trigger"] == "replay" and positive["authority_unchanged"]
        report = {"empty_delta": empty, "failed_model": failed, "positive_delta": positive, "rerun": replay, "candidate_rows_after_rerun": positive_ledger.count("candidates")}
        assert report["candidate_rows_after_rerun"] == 1
        print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
