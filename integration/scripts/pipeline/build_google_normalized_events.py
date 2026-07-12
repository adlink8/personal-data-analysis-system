"""Phase 16: fill Google normalized_events from activities (idempotent).

Does NOT run dialogue knowledge-unit extraction.

Usage::

    python integration/scripts/pipeline/build_google_normalized_events.py --dry-run
    python integration/scripts/pipeline/build_google_normalized_events.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from core.project_paths import ROOT  # noqa: E402

GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
BATCH_PREFIX = "phase16_norm"


@dataclass
class NormStats:
    activities_total: int = 0
    written: int = 0
    skipped_empty: int = 0
    before_count: int = 0
    after_count: int = 0
    batch_id: str = ""
    dry_run: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


ENSURE_SQL = """
CREATE TABLE IF NOT EXISTS normalized_events (
    event_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    service TEXT NOT NULL,
    event_time TEXT,
    title TEXT,
    url TEXT,
    domain TEXT,
    content TEXT,
    raw_json TEXT,
    record_hash TEXT NOT NULL,
    batch_id TEXT NOT NULL,
    source_file_id TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_norm_service ON normalized_events(service);
CREATE INDEX IF NOT EXISTS idx_norm_time ON normalized_events(event_time);
CREATE INDEX IF NOT EXISTS idx_norm_hash ON normalized_events(record_hash);
"""


def _event_id(service: str, event_at: str, title: str, url: str, aid: int) -> str:
    raw = f"{service}|{event_at or ''}|{title or ''}|{url or ''}|{aid}"
    return "g|" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _record_hash(service: str, event_at: str, title: str, content: str, url: str) -> str:
    raw = f"{service}|{event_at or ''}|{title or ''}|{content or ''}|{url or ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build(db_path: Path = GOOGLE_DB, write: bool = False) -> NormStats:
    stats = NormStats(dry_run=not write)
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    batch_id = f"{BATCH_PREFIX}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    stats.batch_id = batch_id

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(ENSURE_SQL)
    stats.before_count = con.execute("SELECT COUNT(*) FROM normalized_events").fetchone()[0]
    rows = con.execute(
        "SELECT id, service, event_at, month, action, category, title_or_query, "
        "channel_or_source, domain, url, raw_excerpt, source_dataset "
        "FROM activities ORDER BY id"
    ).fetchall()
    stats.activities_total = len(rows)

    payload = []
    for r in rows:
        title = (r["title_or_query"] or "").strip()
        content = (r["raw_excerpt"] or title or "").strip()
        if len(content) < 2 and not title:
            stats.skipped_empty += 1
            continue
        aid = int(r["id"])
        service = r["service"] or "unknown"
        event_at = r["event_at"] or ""
        url = r["url"] or ""
        domain = r["domain"] or ""
        eid = _event_id(service, event_at, title, url, aid)
        rh = _record_hash(service, event_at, title, content, url)
        raw_obj = {
            "activity_id": aid,
            "month": r["month"],
            "action": r["action"],
            "category": r["category"],
            "channel_or_source": r["channel_or_source"],
            "source_dataset": r["source_dataset"],
        }
        payload.append(
            (
                eid,
                "Google",
                service,
                event_at,
                title[:500],
                url[:1000],
                domain[:300],
                content[:4000],
                json.dumps(raw_obj, ensure_ascii=False),
                rh,
                batch_id,
                str(aid),
            )
        )

    stats.written = len(payload)
    if write and payload:
        con.executemany(
            "INSERT OR REPLACE INTO normalized_events "
            "(event_id, source, service, event_time, title, url, domain, content, "
            "raw_json, record_hash, batch_id, source_file_id) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            payload,
        )
        con.commit()
    stats.after_count = (
        con.execute("SELECT COUNT(*) FROM normalized_events").fetchone()[0]
        if write
        else stats.before_count  # dry-run: logical after would be written count if replace all
    )
    if not write:
        stats.after_count = len(payload)  # expected full rebuild size under replace
    con.close()
    return stats


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 16: Google normalized_events")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write", action="store_true")
    p.add_argument("--db", type=Path, default=GOOGLE_DB)
    args = p.parse_args(argv)
    if not args.write:
        args.dry_run = True
    if args.write and args.dry_run:
        # write wins if both
        args.dry_run = False
    stats = build(args.db, write=args.write)
    print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
