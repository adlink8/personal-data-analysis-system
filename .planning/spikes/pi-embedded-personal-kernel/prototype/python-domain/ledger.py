"""Synthetic Node/Python task ledger used by Spike 002 and 004.

The module intentionally uses only the standard library and a private SQLite file.
It models the authority boundary; it is not production application code.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


def checksum(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ToolRequest:
    task_id: str
    tool_call_id: str
    idempotency_key: str
    schema_version: str
    task_key: str
    deadline_ms: int
    args: dict[str, Any]

    @property
    def args_checksum(self) -> str:
        return checksum(self.args)

    def envelope(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "args_checksum": self.args_checksum,
        }


class TypedProtocolError(RuntimeError):
    def __init__(self, code: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable

    def as_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": str(self), "retryable": self.retryable}


@dataclass(frozen=True)
class Authority:
    watermark: str = "wm-0"
    active_pointer: str = "active-0"
    canonical_rows: int = 10

    def fingerprint(self) -> str:
        return checksum(asdict(self))


class TaskLedger:
    """Small append-oriented task ledger with idempotent candidate insertion."""

    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._init_lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_schema(self) -> None:
        with self._init_lock:
            conn = self._connect()
            try:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS tasks (
                        task_key TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        idempotency_key TEXT NOT NULL UNIQUE,
                        args_checksum TEXT NOT NULL,
                        state TEXT NOT NULL,
                        result_json TEXT,
                        error_json TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS candidates (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_key TEXT NOT NULL,
                        candidate_checksum TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        UNIQUE(task_key, candidate_checksum)
                    );
                    CREATE TABLE IF NOT EXISTS transitions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_key TEXT NOT NULL,
                        state TEXT NOT NULL,
                        note TEXT NOT NULL,
                        created_at REAL NOT NULL
                    );
                    """
                )
            finally:
                conn.close()

    def enqueue(self, request: ToolRequest) -> dict[str, Any]:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM tasks WHERE idempotency_key = ? OR task_key = ?",
                (request.idempotency_key, request.task_key),
            ).fetchone()
            if row:
                if row["args_checksum"] != request.args_checksum:
                    conn.execute("ROLLBACK")
                    return {"status": "error", "error": TypedProtocolError("typed_conflict", "same key with different args").as_dict()}
                if row["state"] == "outcome_unknown":
                    conn.execute("ROLLBACK")
                    return {"status": "error", "error": TypedProtocolError("outcome_unknown", "manual reconciliation required").as_dict()}
                conn.execute("COMMIT")
                return {"status": "replay", "state": row["state"], "result": json.loads(row["result_json"]) if row["result_json"] else None}
            conn.execute(
                "INSERT INTO tasks(task_key, task_id, idempotency_key, args_checksum, state, created_at, updated_at) VALUES (?, ?, ?, ?, 'queued', ?, ?)",
                (request.task_key, request.task_id, request.idempotency_key, request.args_checksum, now, now),
            )
            conn.execute(
                "INSERT INTO transitions(task_key, state, note, created_at) VALUES (?, 'queued', 'accepted', ?)",
                (request.task_key, now),
            )
            conn.execute("COMMIT")
            return {"status": "accepted", "state": "queued"}
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def claim(self, task_key: str) -> dict[str, Any]:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute("SELECT * FROM tasks WHERE task_key = ?", (task_key,)).fetchone()
            if not row:
                conn.execute("ROLLBACK")
                return {"status": "error", "error": TypedProtocolError("not_found", "task missing").as_dict()}
            if row["state"] != "queued":
                conn.execute("COMMIT")
                return {"status": "busy", "state": row["state"]}
            conn.execute("UPDATE tasks SET state = 'running', updated_at = ? WHERE task_key = ?", (now, task_key))
            conn.execute("INSERT INTO transitions(task_key, state, note, created_at) VALUES (?, 'running', 'claimed', ?)", (task_key, now))
            conn.execute("COMMIT")
            return {"status": "claimed", "state": "running"}
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def insert_candidate(self, task_key: str, candidate: dict[str, Any]) -> bool:
        candidate_checksum = checksum(candidate)
        conn = self._connect()
        try:
            cur = conn.execute(
                "INSERT OR IGNORE INTO candidates(task_key, candidate_checksum, created_at) VALUES (?, ?, ?)",
                (task_key, candidate_checksum, time.time()),
            )
            return cur.rowcount == 1
        finally:
            conn.close()

    def finish(self, task_key: str, result: dict[str, Any]) -> None:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE tasks SET state = 'succeeded', result_json = ?, updated_at = ? WHERE task_key = ? AND state = 'running'", (json.dumps(result, sort_keys=True), now, task_key))
            conn.execute("INSERT INTO transitions(task_key, state, note, created_at) VALUES (?, 'succeeded', 'terminal', ?)", (task_key, now))
            conn.execute("COMMIT")
        finally:
            conn.close()

    def fail(self, task_key: str, error: dict[str, Any], state: str = "failed_terminal") -> None:
        now = time.time()
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("UPDATE tasks SET state = ?, error_json = ?, updated_at = ? WHERE task_key = ? AND state IN ('queued', 'running')", (state, json.dumps(error, sort_keys=True), now, task_key))
            conn.execute("INSERT INTO transitions(task_key, state, note, created_at) VALUES (?, ?, 'terminal', ?)", (task_key, state, now))
            conn.execute("COMMIT")
        finally:
            conn.close()

    def mark_unknown(self, task_key: str) -> None:
        self.fail(task_key, TypedProtocolError("outcome_unknown", "crash boundary requires manual reconciliation").as_dict(), "outcome_unknown")

    def count(self, table: str) -> int:
        if table not in {"tasks", "candidates", "transitions"}:
            raise ValueError(table)
        conn = self._connect()
        try:
            return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
        finally:
            conn.close()

    def task_state(self, task_key: str) -> str | None:
        conn = self._connect()
        try:
            row = conn.execute("SELECT state FROM tasks WHERE task_key = ?", (task_key,)).fetchone()
            return row[0] if row else None
        finally:
            conn.close()


def execute_request(
    ledger: TaskLedger,
    request: ToolRequest,
    candidate: dict[str, Any],
    *,
    cancel: threading.Event | None = None,
    crash_after_candidate: bool = False,
) -> dict[str, Any]:
    accepted = ledger.enqueue(request)
    if accepted["status"] in {"replay", "error"}:
        return accepted
    claimed = ledger.claim(request.task_key)
    if claimed["status"] != "claimed":
        return claimed
    if cancel and cancel.is_set():
        error = TypedProtocolError("cancelled", "cancelled before domain call").as_dict()
        ledger.fail(request.task_key, error, "cancelled")
        return {"status": "error", "error": error}
    inserted = ledger.insert_candidate(request.task_key, candidate)
    if crash_after_candidate:
        ledger.mark_unknown(request.task_key)
        return {"status": "error", "error": TypedProtocolError("outcome_unknown", "crash simulated after candidate insert").as_dict()}
    if cancel and cancel.is_set():
        error = TypedProtocolError("cancelled", "cancelled after domain call").as_dict()
        ledger.fail(request.task_key, error, "cancelled")
        return {"status": "error", "error": error}
    result = {"candidate_inserted": inserted, "candidate_checksum": checksum(candidate)}
    ledger.finish(request.task_key, result)
    return {"status": "succeeded", "result": result}
