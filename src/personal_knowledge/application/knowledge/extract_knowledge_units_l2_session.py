"""L2 dual-pass knowledge extraction: session-window second pass.

Complements L1 (1 message = 1 LLM call). For each eligible session with enough
user messages, build a chronological user window and extract units that need
cross-turn context. Evidence quotes must match a concrete cm| message.

Usage::

    python -m personal_knowledge.application.knowledge.extract_knowledge_units_l2_session --dry-run
    python -m personal_knowledge.application.knowledge.extract_knowledge_units_l2_session --write --limit 20
    python -m personal_knowledge.application.knowledge.extract_knowledge_units_l2_session --write --resume <run_id>
    python -m personal_knowledge.application.knowledge.extract_knowledge_units_l2_session --status <run_id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from personal_knowledge.core.sqlite import connect_rw

from pydantic import ValidationError

from personal_knowledge.core.project_paths import UNIFIED_DB, AGENT_CONVERSATIONS_DB, AI_CONTEXT_DIR
from personal_knowledge.application.knowledge.build_knowledge_units import (
    ExtractionResult,
    strip_system_injections,
    is_meaningful,
    _clean_json,
)
from personal_knowledge.application.knowledge.build_knowledge_units_prod import (
    call_llm_with_retry,
    TokenProvider,
    RequestRateLimiter,
    compute_cache_key,
    get_cached_response,
    put_cached_response,
    DEFAULT_WORKERS,
    DEFAULT_MIN_REQUEST_INTERVAL,
)
from personal_knowledge.application.knowledge.knowledge_unit_pipeline import RunManifest
from personal_knowledge.application.knowledge.migrate_add_knowledge_unit_tables import SCHEMA_SQL

PROMPT_PATH = (
    Path(__file__).resolve().parents[4] / "assets" / "prompts" / "knowledge_unit_extractor" / "v1_session_window.md"
)
PROMPT_VERSION = "v1_session_window"
MAX_WINDOW_CHARS = 12000
MIN_USER_MSGS = 2
REPORT_PATH = AI_CONTEXT_DIR / "knowledge_l2_session_extract_report.json"

JOBS_SCHEMA = """
CREATE TABLE IF NOT EXISTS knowledge_l2_session_jobs (
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    position INTEGER NOT NULL,
    window_hash TEXT NOT NULL,
    message_ids_json TEXT NOT NULL,
    status TEXT NOT NULL,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    unit_count INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (run_id, session_id)
);
CREATE INDEX IF NOT EXISTS idx_l2_jobs_status ON knowledge_l2_session_jobs(run_id, status);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _evidence_supported(quote: str, source: str) -> bool:
    if not quote or not source:
        return False
    if quote in source:
        return True
    q = quote.strip()
    if len(q) < 10:
        return q in source
    # any contiguous 10-char window of quote in source
    for i in range(0, max(1, len(q) - 9)):
        frag = q[i : i + 10]
        if frag in source:
            return True
    return False


def _best_message_for_quote(quote: str, messages: list[dict]) -> str | None:
    """Return canonical_message_id whose content best supports quote."""
    if not quote:
        return None
    # prefer exact contain, then longest message among supporters
    supporters = []
    for m in messages:
        if _evidence_supported(quote, m["cleaned"]):
            score = 2 if quote in m["cleaned"] else 1
            supporters.append((score, len(m["cleaned"]), m["message_id"]))
    if not supporters:
        return None
    supporters.sort(reverse=True)
    return supporters[0][2]


def list_l2_sessions(
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    *,
    min_user_msgs: int = MIN_USER_MSGS,
    limit: int | None = None,
) -> list[dict]:
    """Sessions eligible for L2: enough cleaned user messages."""
    con = sqlite3.connect(f"file:{canonical_db.as_posix()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT m.canonical_session_id AS sid, m.canonical_message_id AS mid,
               m.content, m.timestamp, s.agent, s.started_at
        FROM canonical_messages m
        JOIN canonical_sessions s ON m.canonical_session_id = s.canonical_session_id
        WHERE s.evidence_eligible = 1
          AND m.role = 'user'
          AND m.content IS NOT NULL
          AND length(m.content) > 20
        ORDER BY s.started_at DESC, m.timestamp ASC, m.canonical_message_id ASC
        """
    ).fetchall()
    con.close()

    by_session: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    for r in rows:
        cleaned = strip_system_injections(r["content"] or "")
        if not is_meaningful(cleaned):
            continue
        sid = r["sid"]
        by_session.setdefault(sid, []).append(
            {
                "message_id": r["mid"],
                "cleaned": cleaned,
                "timestamp": r["timestamp"] or "",
            }
        )
        meta[sid] = {"agent": r["agent"] or "", "started_at": r["started_at"] or ""}

    sessions = []
    for sid, msgs in by_session.items():
        if len(msgs) < min_user_msgs:
            continue
        window_msgs, window_text = build_window(msgs)
        if not window_text:
            continue
        sessions.append(
            {
                "session_id": sid,
                "agent": meta[sid]["agent"],
                "started_at": meta[sid]["started_at"],
                "messages": window_msgs,
                "window_text": window_text,
                "window_hash": hashlib.sha256(window_text.encode()).hexdigest()[:32],
                "message_ids": [m["message_id"] for m in window_msgs],
            }
        )
    # started_at DESC already from query grouping order — re-sort
    sessions.sort(key=lambda s: s["started_at"], reverse=True)
    if limit is not None:
        sessions = sessions[: max(0, limit)]
    return sessions


def build_window(
    messages: list[dict],
    *,
    max_chars: int = MAX_WINDOW_CHARS,
) -> tuple[list[dict], str]:
    """Build chronological window text, dropping oldest if over max_chars."""
    # Prefer keeping the most recent messages within budget
    selected: list[dict] = []
    total = 0
    for m in reversed(messages):
        block = f"[msg {m['message_id']}]\n{m['cleaned']}\n"
        if selected and total + len(block) > max_chars:
            break
        if not selected and len(block) > max_chars:
            # single oversized message: hard truncate tail of content
            cut = m["cleaned"][: max_chars - 80]
            m = {**m, "cleaned": cut + "\n…[truncated]"}
            block = f"[msg {m['message_id']}]\n{m['cleaned']}\n"
            selected.append(m)
            total = len(block)
            break
        selected.append(m)
        total += len(block)
    selected.reverse()
    parts = [f"[msg {m['message_id']}]\n{m['cleaned']}" for m in selected]
    header = (
        f"以下为同一会话的多条用户消息（按时间排序，共 {len(selected)} 条）。\n"
        f"每条以 [msg cm|…] 标记；evidence_quote 必须来自其中某条原文。\n\n"
    )
    text = header + "\n\n---\n\n".join(parts)
    if len(text) > max_chars:
        text = text[: max_chars - 20] + "\n…[truncated]"
    return selected, text


def ensure_schema(db_path: Path) -> None:
    con = connect_rw(db_path)
    con.executescript(SCHEMA_SQL)
    con.executescript(JOBS_SCHEMA)
    con.commit()
    con.close()


def start_l2_run(
    sessions: list[dict],
    *,
    model: str,
    db_path: Path = UNIFIED_DB,
) -> str:
    ensure_schema(db_path)
    payload = {
        "n_sessions": len(sessions),
        "session_ids": [s["session_id"] for s in sessions[:50]],
        "prompt": PROMPT_VERSION,
    }
    # knowledge_build_runs CHECK only allows extraction|merge|index|promote|incremental
    manifest = RunManifest.create(
        run_type="extraction",
        source_build_id="l2_session_window",
        input_data=payload,
        prompt_version=PROMPT_VERSION,
        model=model,
        config={
            "pass": "l2_session_window",
            "max_window_chars": MAX_WINDOW_CHARS,
            "min_user_msgs": MIN_USER_MSGS,
        },
    )
    con = connect_rw(db_path)
    con.execute(
        "INSERT OR REPLACE INTO knowledge_build_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            manifest.run_id,
            "extraction",
            manifest.generated_at,
            "l2_session_window",
            manifest.input_hash,
            PROMPT_VERSION,
            "v1",
            model,
            "",
            hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16],
            "",
            "",
            "staging",
            json.dumps({"pass": "l2_session_window"}, ensure_ascii=False),
            "",
        ),
    )
    now = _utc_now()
    for i, s in enumerate(sessions):
        con.execute(
            "INSERT OR REPLACE INTO knowledge_l2_session_jobs "
            "(run_id, session_id, position, window_hash, message_ids_json, status, "
            "attempt_count, unit_count, last_error, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                manifest.run_id,
                s["session_id"],
                i,
                s["window_hash"],
                json.dumps(s["message_ids"], ensure_ascii=False),
                "pending",
                0,
                0,
                None,
                now,
            ),
        )
    con.commit()
    con.close()
    return manifest.run_id


def _job_stats(con: sqlite3.Connection, run_id: str) -> dict:
    out = {}
    for st, n in con.execute(
        "SELECT status, COUNT(*) FROM knowledge_l2_session_jobs WHERE run_id=? GROUP BY 1",
        (run_id,),
    ):
        out[st] = n
    return out


def process_l2_run(
    run_id: str,
    *,
    model: str,
    db_path: Path = UNIFIED_DB,
    canonical_db: Path = AGENT_CONVERSATIONS_DB,
    workers: int = DEFAULT_WORKERS,
    min_request_interval: float = DEFAULT_MIN_REQUEST_INTERVAL,
    max_jobs: int | None = None,
    min_user_msgs: int = MIN_USER_MSGS,
) -> dict:
    ensure_schema(db_path)
    prompt_text = PROMPT_PATH.read_text(encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_text.encode()).hexdigest()[:16]
    schema_hash = "v1_session_window"
    config_hash = hashlib.sha256(
        f"l2|{MAX_WINDOW_CHARS}|{min_user_msgs}".encode()
    ).hexdigest()[:16]

    # Reload session windows for pending jobs
    sessions_by_id = {
        s["session_id"]: s
        for s in list_l2_sessions(canonical_db, min_user_msgs=min_user_msgs, limit=None)
    }

    con = connect_rw(db_path, timeout=60)
    token_provider = TokenProvider()
    rate_limiter = RequestRateLimiter(min_request_interval)
    stats = {
        "processed": 0,
        "succeeded": 0,
        "abstained": 0,
        "failed": 0,
        "units": 0,
        "units_dropped_no_evidence": 0,
        "cache_hits": 0,
        "workers": max(1, workers),
    }
    t0 = time.time()
    workers = max(1, int(workers))

    def _worker(payload: dict) -> dict:
        resp = call_llm_with_retry(
            prompt_text,
            payload["window_text"],
            model,
            token_provider,
            max_retries=2,
            rate_limiter=rate_limiter,
        )
        if "error" in resp:
            return {
                "session_id": payload["session_id"],
                "kind": "llm_error",
                "error": resp.get("error"),
                "error_class": resp.get("error_class", "terminal"),
                "cache_key": payload["cache_key"],
                "input_hash": payload["input_hash"],
            }
        return {
            "session_id": payload["session_id"],
            "kind": "ok",
            "raw_text": resp["text"],
            "cache_key": payload["cache_key"],
            "input_hash": payload["input_hash"],
            "write_cache": True,
        }

    def _commit(session_id: str, work: dict, session: dict) -> None:
        now = _utc_now()
        if work.get("kind") == "llm_error":
            con.execute(
                "UPDATE knowledge_l2_session_jobs SET status=?, last_error=?, "
                "attempt_count=attempt_count+1, updated_at=? WHERE run_id=? AND session_id=?",
                (
                    "retryable" if work.get("error_class") == "retryable" else "terminal_failed",
                    str(work.get("error") or "")[:300],
                    now,
                    run_id,
                    session_id,
                ),
            )
            stats["failed"] += 1
            stats["processed"] += 1
            con.commit()
            return

        raw_text = work["raw_text"]
        if work.get("write_cache"):
            response_hash = hashlib.sha256(raw_text.encode()).hexdigest()[:32]
            put_cached_response(
                con,
                work["cache_key"],
                model,
                prompt_hash,
                schema_hash,
                work["input_hash"],
                config_hash,
                raw_text,
                response_hash,
                run_id,
            )
        try:
            parsed = json.loads(_clean_json(raw_text))
            result = ExtractionResult(**parsed)
        except (json.JSONDecodeError, ValidationError, TypeError) as e:
            con.execute(
                "UPDATE knowledge_l2_session_jobs SET status=?, last_error=?, "
                "attempt_count=attempt_count+1, updated_at=? WHERE run_id=? AND session_id=?",
                ("terminal_failed", f"schema:{e}"[:300], now, run_id, session_id),
            )
            stats["failed"] += 1
            stats["processed"] += 1
            con.commit()
            return

        if result.abstain or not result.units:
            con.execute(
                "UPDATE knowledge_l2_session_jobs SET status='abstained', unit_count=0, "
                "updated_at=? WHERE run_id=? AND session_id=?",
                (now, run_id, session_id),
            )
            stats["abstained"] += 1
            stats["processed"] += 1
            con.commit()
            return

        kept = 0
        for ordinal, unit in enumerate(result.units, 1):
            mid = _best_message_for_quote(unit.evidence_quote, session["messages"])
            if not mid:
                stats["units_dropped_no_evidence"] += 1
                continue
            unit_id = "l2|" + hashlib.sha256(
                f"{run_id}|{session_id}|{ordinal}|{unit.subject}|{unit.answer}".encode()
            ).hexdigest()[:28]
            lifecycle = unit.lifecycle if unit.lifecycle in (
                "current", "deprecated", "superseded", "conflict"
            ) else "current"
            con.execute(
                "INSERT OR REPLACE INTO knowledge_units "
                "(unit_id, run_id, unit_type, subject, question, answer, confidence, "
                "evidence_quote, lifecycle, source_session_id, source_message_ref, "
                "source_agent, evidence_scope, status, version, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    unit_id,
                    run_id,
                    unit.unit_type,
                    unit.subject,
                    unit.question,
                    unit.answer,
                    unit.confidence,
                    unit.evidence_quote,
                    lifecycle,
                    session_id,
                    mid,
                    session.get("agent") or "l2_session_window",
                    "user",  # CHECK constraint; L2 marked via unit_id prefix l2| + run source_build_id
                    "staging",
                    1,
                    now,
                ),
            )
            con.execute(
                "INSERT OR IGNORE INTO knowledge_unit_evidence (unit_id, evidence_ref) VALUES (?,?)",
                (unit_id, mid),
            )
            kept += 1
            stats["units"] += 1

        if kept == 0:
            con.execute(
                "UPDATE knowledge_l2_session_jobs SET status='abstained', unit_count=0, "
                "last_error=?, updated_at=? WHERE run_id=? AND session_id=?",
                ("all units failed evidence gate", now, run_id, session_id),
            )
            stats["abstained"] += 1
        else:
            con.execute(
                "UPDATE knowledge_l2_session_jobs SET status='succeeded', unit_count=?, "
                "updated_at=? WHERE run_id=? AND session_id=?",
                (kept, now, run_id, session_id),
            )
            stats["succeeded"] += 1
        stats["processed"] += 1
        con.commit()

    while True:
        q = (
            "SELECT session_id FROM knowledge_l2_session_jobs "
            "WHERE run_id=? AND status IN ('pending','retryable') "
            "ORDER BY position ASC LIMIT ?"
        )
        take = max(workers * 2, 8)
        if max_jobs is not None:
            remain = max_jobs - stats["processed"]
            if remain <= 0:
                break
            take = min(take, remain)
        jobs = [r[0] for r in con.execute(q, (run_id, take)).fetchall()]
        if not jobs:
            break

        payloads = []
        cache_ready = []
        for sid in jobs:
            session = sessions_by_id.get(sid)
            if not session:
                # rebuild single session window from DB if missing
                rebuild = [
                    s
                    for s in list_l2_sessions(
                        canonical_db, min_user_msgs=min_user_msgs, limit=None
                    )
                    if s["session_id"] == sid
                ]
                if not rebuild:
                    con.execute(
                        "UPDATE knowledge_l2_session_jobs SET status='terminal_failed', "
                        "last_error=?, updated_at=? WHERE run_id=? AND session_id=?",
                        ("session not rebuildable", _utc_now(), run_id, sid),
                    )
                    stats["failed"] += 1
                    stats["processed"] += 1
                    con.commit()
                    continue
                session = rebuild[0]
                sessions_by_id[sid] = session

            input_hash = session["window_hash"]
            cache_key = compute_cache_key(
                model, prompt_hash, schema_hash, input_hash, config_hash
            )
            cached = get_cached_response(con, cache_key)
            if cached is not None:
                stats["cache_hits"] += 1
                cache_ready.append(
                    (
                        sid,
                        session,
                        {
                            "kind": "ok",
                            "raw_text": cached,
                            "cache_key": cache_key,
                            "input_hash": input_hash,
                            "write_cache": False,
                        },
                    )
                )
            else:
                payloads.append(
                    {
                        "session_id": sid,
                        "window_text": session["window_text"],
                        "cache_key": cache_key,
                        "input_hash": input_hash,
                        "session": session,
                    }
                )

        for sid, session, work in cache_ready:
            _commit(sid, work, session)

        if payloads:
            with ThreadPoolExecutor(max_workers=workers) as ex:
                futs = {ex.submit(_worker, p): p for p in payloads}
                for fut in as_completed(futs):
                    p = futs[fut]
                    try:
                        work = fut.result()
                    except Exception as e:  # noqa: BLE001
                        work = {
                            "kind": "llm_error",
                            "error": f"{type(e).__name__}: {e}",
                            "error_class": "retryable",
                            "cache_key": p["cache_key"],
                            "input_hash": p["input_hash"],
                        }
                    _commit(p["session_id"], work, p["session"])
                    if stats["processed"] % 5 == 0:
                        print(
                            f"[l2] processed={stats['processed']} ok={stats['succeeded']} "
                            f"abs={stats['abstained']} fail={stats['failed']} "
                            f"units={stats['units']} cache={stats['cache_hits']}",
                            flush=True,
                        )

    # finalize run status
    st = _job_stats(con, run_id)
    rem = st.get("pending", 0) + st.get("retryable", 0)
    final = "validated" if rem == 0 else "staging"
    con.execute(
        "UPDATE knowledge_build_runs SET status=? WHERE run_id=?",
        (final, run_id),
    )
    con.commit()
    con.close()
    stats["elapsed_sec"] = round(time.time() - t0, 1)
    stats["job_stats"] = st
    stats["run_status"] = final
    return stats


def write_report(run_id: str, stats: dict, path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "generated_at": _utc_now(),
        "phase": "l2_session_window",
        "run_id": run_id,
        "prompt_version": PROMPT_VERSION,
        "stats": stats,
        "notes": [
            "L2 complements L1 message extraction; units stored status=staging.",
            "evidence_quote must match a cm| message in the session window.",
            "Canonical merge of L2 staging is a separate promote step.",
        ],
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="L2 session-window dual-pass KU extraction")
    p.add_argument("--dry-run", action="store_true", help="List sessions only, no LLM")
    p.add_argument("--write", action="store_true", help="Start new L2 run and process")
    p.add_argument("--resume", metavar="RUN_ID", help="Resume existing L2 run")
    p.add_argument("--status", metavar="RUN_ID", help="Show job stats")
    p.add_argument("--limit", type=int, default=None, help="Max sessions (newest first)")
    p.add_argument("--max-jobs", type=int, default=None, help="Max jobs this process")
    p.add_argument("--min-user-msgs", type=int, default=MIN_USER_MSGS)
    p.add_argument("--model", default="gemini-2.5-flash")
    p.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    p.add_argument("--min-request-interval", type=float, default=DEFAULT_MIN_REQUEST_INTERVAL)
    p.add_argument("--db", type=Path, default=UNIFIED_DB)
    p.add_argument("--canonical-db", type=Path, default=AGENT_CONVERSATIONS_DB)
    p.add_argument("--report", type=Path, default=REPORT_PATH)
    args = p.parse_args(argv)

    if args.status:
        ensure_schema(args.db)
        con = connect_rw(args.db)
        st = _job_stats(con, args.status)
        n_units = con.execute(
            "SELECT COUNT(*) FROM knowledge_units WHERE run_id=?", (args.status,)
        ).fetchone()[0]
        con.close()
        print(json.dumps({"run_id": args.status, "jobs": st, "units": n_units}, indent=2))
        return 0

    min_user = args.min_user_msgs
    sessions = list_l2_sessions(
        args.canonical_db, min_user_msgs=min_user, limit=args.limit
    )
    print(f"[l2] eligible sessions: {len(sessions)} (min_user_msgs={min_user})")
    if args.dry_run or (not args.write and not args.resume):
        for i, s in enumerate(sessions[:15], 1):
            print(
                f"  [{i}] {s['session_id'][:40]} msgs={len(s['messages'])} "
                f"chars={len(s['window_text'])} agent={s['agent']}"
            )
        if len(sessions) > 15:
            print(f"  ... +{len(sessions) - 15} more")
        print("[l2] dry-run only; use --write to extract")
        return 0

    if args.write:
        run_id = start_l2_run(sessions, model=args.model, db_path=args.db)
        print(f"[l2] started run_id={run_id}")
    else:
        run_id = args.resume
        print(f"[l2] resume run_id={run_id}")

    stats = process_l2_run(
        run_id,
        model=args.model,
        db_path=args.db,
        canonical_db=args.canonical_db,
        workers=args.workers,
        min_request_interval=args.min_request_interval,
        max_jobs=args.max_jobs,
        min_user_msgs=min_user,
    )
    write_report(run_id, stats, args.report)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
