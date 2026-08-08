"""Spike 003: deterministic Skill binding and Session/Candidate isolation."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import tempfile
from pathlib import Path


class GateError(RuntimeError):
    pass


SKILLS = {
    "maintain-conversation-delta": {
        "version": "1",
        "allowed_tools": {"inspect_personal_delta", "search_personal_knowledge", "get_conversation_evidence", "create_candidate_artifact"},
    }
}
SECRET = re.compile(r"(sk-[A-Za-z0-9]{8,}|Bearer\s+[A-Za-z0-9._-]+|password\s*=)", re.I)


def checksum(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def init_db(path: Path, table: str) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        conn.commit()
    finally:
        conn.close()


def count(path: Path, table: str) -> int:
    conn = sqlite3.connect(path)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    finally:
        conn.close()


def run_skill(skill_name: str, tool_names: list[str], output: dict[str, object], session_db: Path, candidate_db: Path) -> dict[str, object]:
    skill = SKILLS.get(skill_name)
    if not skill:
        raise GateError("skill_not_registered")
    if not set(tool_names) <= skill["allowed_tools"]:
        raise GateError("tool_not_allowed")
    required = {"task_id", "source_cutoff", "evidence_refs", "payload_checksum", "uncertainty"}
    if not required <= output.keys():
        raise GateError("candidate_missing_evidence_contract")
    if SECRET.search(json.dumps(output)):
        raise GateError("raw_secret_rejected")

    session_payload = {"skill": skill_name, "skill_version": skill["version"], "task_id": output["task_id"], "evidence_refs": output["evidence_refs"]}
    conn = sqlite3.connect(session_db)
    try:
        conn.execute("INSERT INTO sessions(id, payload) VALUES (?, ?)", (output["task_id"], json.dumps(session_payload, sort_keys=True)))
        conn.commit()
    finally:
        conn.close()

    candidate_checksum = checksum(output)
    conn = sqlite3.connect(candidate_db)
    try:
        conn.execute("INSERT OR IGNORE INTO candidates(id, payload) VALUES (?, ?)", (candidate_checksum, json.dumps(output, sort_keys=True)))
        conn.commit()
    finally:
        conn.close()
    return {"selected_skill": skill_name, "skill_version": skill["version"], "candidate_checksum": candidate_checksum}


def expect_gate(fn, code: str) -> str:
    try:
        fn()
    except GateError as exc:
        assert str(exc) == code, (str(exc), code)
        return str(exc)
    raise AssertionError(f"expected {code}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="spike-003-") as temp:
        root = Path(temp)
        session_db = root / "session.sqlite"
        candidate_db = root / "candidate.sqlite"
        init_db(session_db, "sessions")
        init_db(candidate_db, "candidates")
        output = {
            "task_id": "task-003",
            "source_cutoff": "wm-1",
            "evidence_refs": ["ev-opaque-1"],
            "payload_checksum": "candidate-payload-checksum",
            "uncertainty": 0.2,
        }
        success = run_skill("maintain-conversation-delta", ["inspect_personal_delta", "get_conversation_evidence", "create_candidate_artifact"], output, session_db, candidate_db)
        replay = run_skill("maintain-conversation-delta", ["inspect_personal_delta", "create_candidate_artifact"], output | {"task_id": "task-003-replay"}, session_db, candidate_db)
        assert success["selected_skill"] == "maintain-conversation-delta"
        assert replay["candidate_checksum"] != success["candidate_checksum"]
        assert count(session_db, "sessions") == 2
        assert count(candidate_db, "candidates") == 2

        rejected = {
            "unknown_skill": expect_gate(lambda: run_skill("auto-select", [], output, session_db, candidate_db), "skill_not_registered"),
            "forbidden_tool": expect_gate(lambda: run_skill("maintain-conversation-delta", ["bash"], output, session_db, candidate_db), "tool_not_allowed"),
            "missing_evidence": expect_gate(lambda: run_skill("maintain-conversation-delta", ["create_candidate_artifact"], {"task_id": "bad"}, session_db, candidate_db), "candidate_missing_evidence_contract"),
            "secret": expect_gate(lambda: run_skill("maintain-conversation-delta", ["create_candidate_artifact"], output | {"secret": "sk-123456789"}, session_db, candidate_db), "raw_secret_rejected"),
        }

        session_db.unlink()
        assert count(candidate_db, "candidates") == 2
        print(json.dumps({
            "deterministic_binding": success,
            "replay_candidate_count": count(candidate_db, "candidates"),
            "rejections": rejected,
            "session_delete_does_not_delete_candidate": True,
            "candidate_store": str(candidate_db.name),
        }, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
