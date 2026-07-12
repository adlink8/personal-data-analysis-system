"""Phase 16: aggregate Google light assertions (NOT dialogue knowledge units).

Privacy:
  - restricted: payment/finance categories, Maps service → no interest assertions
  - aggregate_ok: Search / YouTube / Gemini / AI Mode theme & frequency signals

Usage::

    python integration/scripts/pipeline/build_google_light_assertions.py --dry-run
    python integration/scripts/pipeline/build_google_light_assertions.py --write
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from core.project_paths import ROOT, AI_CONTEXT_DIR  # noqa: E402

GOOGLE_DB = ROOT / "Google" / "structured" / "db" / "google_data.sqlite"
REPORT_PATH = AI_CONTEXT_DIR / "google_light_structure_report.json"

RESTRICTED_CATEGORY_SUBSTR = ("支付", "金融", "卡")
RESTRICTED_SERVICES = {"Maps", "地图"}
MIN_TOPIC = 5
MIN_CHANNEL = 3
MIN_DOMAIN = 3


@dataclass
class AssertStats:
    activities_scanned: int = 0
    eligible_for_assert: int = 0
    restricted_skipped: int = 0
    assertions: int = 0
    by_type: dict = field(default_factory=dict)
    dry_run: bool = True
    normalized_events: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


SCHEMA = """
CREATE TABLE IF NOT EXISTS google_light_assertions (
    assertion_id TEXT PRIMARY KEY,
    assertion_type TEXT NOT NULL,
    subject TEXT NOT NULL,
    claim TEXT NOT NULL,
    evidence_count INTEGER NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    services_json TEXT,
    categories_json TEXT,
    privacy_tier TEXT NOT NULL DEFAULT 'aggregate_ok',
    status TEXT NOT NULL DEFAULT 'current',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_gla_type ON google_light_assertions(assertion_type);
CREATE INDEX IF NOT EXISTS idx_gla_status ON google_light_assertions(status);
"""


def _is_restricted(service: str, category: str) -> bool:
    svc = service or ""
    cat = category or ""
    if svc in RESTRICTED_SERVICES or "地图" in svc:
        return True
    for s in RESTRICTED_CATEGORY_SUBSTR:
        if s in cat:
            return True
    return False


def _aid(kind: str, subject: str) -> str:
    h = hashlib.sha256(f"{kind}|{subject}".encode("utf-8")).hexdigest()[:20]
    return f"gla|{kind}|{h}"


def _event_id_for_activity(con: sqlite3.Connection, activity_id: int) -> str | None:
    row = con.execute(
        "SELECT event_id FROM normalized_events WHERE source_file_id=?",
        (str(activity_id),),
    ).fetchone()
    return row[0] if row else None


def build(db_path: Path = GOOGLE_DB, write: bool = False) -> tuple[AssertStats, list[dict]]:
    stats = AssertStats(dry_run=not write)
    if not db_path.exists():
        raise FileNotFoundError(db_path)

    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        stats.normalized_events = con.execute(
            "SELECT COUNT(*) FROM normalized_events"
        ).fetchone()[0]
    except Exception:
        stats.normalized_events = 0

    rows = con.execute(
        "SELECT id, service, category, title_or_query, channel_or_source, domain "
        "FROM activities"
    ).fetchall()
    stats.activities_scanned = len(rows)

    topic_refs: dict[str, list[str]] = defaultdict(list)
    service_refs: dict[str, list[str]] = defaultdict(list)
    channel_refs: dict[str, list[str]] = defaultdict(list)
    domain_refs: dict[str, list[str]] = defaultdict(list)
    topic_services: dict[str, set[str]] = defaultdict(set)

    for r in rows:
        service = r["service"] or ""
        category = r["category"] or ""
        if _is_restricted(service, category):
            stats.restricted_skipped += 1
            continue
        stats.eligible_for_assert += 1
        eid = _event_id_for_activity(con, int(r["id"]))
        if not eid:
            # fallback deterministic id without requiring norm table
            raw = f"{service}|{r['title_or_query'] or ''}|{r['id']}"
            eid = "g|" + hashlib.sha256(raw.encode()).hexdigest()[:24]

        if category:
            topic_refs[category].append(eid)
            topic_services[category].add(service)
        if service:
            service_refs[service].append(eid)
        ch = (r["channel_or_source"] or "").strip()
        if service == "YouTube" and ch:
            channel_refs[ch].append(eid)
        dom = (r["domain"] or "").strip().lower()
        if dom and dom not in ("google.com", "youtube.com", "www.google.com"):
            domain_refs[dom].append(eid)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assertions: list[dict] = []

    def add(atype: str, subject: str, claim: str, refs: list[str], services=None, cats=None, tier="aggregate_ok"):
        # cap evidence refs stored
        refs_u = list(dict.fromkeys(refs))[:50]
        assertions.append(
            {
                "assertion_id": _aid(atype, subject),
                "assertion_type": atype,
                "subject": subject[:200],
                "claim": claim[:500],
                "evidence_count": len(refs),
                "evidence_refs_json": json.dumps(refs_u, ensure_ascii=False),
                "services_json": json.dumps(sorted(services or []), ensure_ascii=False),
                "categories_json": json.dumps(sorted(cats or []), ensure_ascii=False),
                "privacy_tier": tier,
                "status": "current",
                "created_at": now,
            }
        )

    for cat, refs in sorted(topic_refs.items(), key=lambda x: -len(x[1])):
        if len(refs) < MIN_TOPIC:
            continue
        add(
            "interest_topic",
            cat,
            f"用户在 Google 活动中频繁涉及主题「{cat}」（约 {len(refs)} 次，聚合信号，非对话断言）",
            refs,
            services=topic_services.get(cat),
            cats=[cat],
        )

    for svc, refs in sorted(service_refs.items(), key=lambda x: -len(x[1])):
        if len(refs) < MIN_TOPIC:
            continue
        add(
            "frequent_service",
            svc,
            f"用户常用 Google 服务「{svc}」（约 {len(refs)} 条活动）",
            refs,
            services=[svc],
        )

    for ch, refs in sorted(channel_refs.items(), key=lambda x: -len(x[1])):
        if len(refs) < MIN_CHANNEL:
            continue
        add(
            "frequent_channel",
            ch,
            f"用户在 YouTube 上多次观看/互动频道「{ch}」（约 {len(refs)} 次）",
            refs,
            services=["YouTube"],
        )

    for dom, refs in sorted(domain_refs.items(), key=lambda x: -len(x[1])):
        if len(refs) < MIN_DOMAIN:
            continue
        add(
            "domain_affinity",
            dom,
            f"用户活动中反复出现域名「{dom}」（约 {len(refs)} 次）",
            refs,
        )

    stats.assertions = len(assertions)
    stats.by_type = {}
    for a in assertions:
        stats.by_type[a["assertion_type"]] = stats.by_type.get(a["assertion_type"], 0) + 1

    if write:
        con.execute("DELETE FROM google_light_assertions WHERE status='current'")
        con.executemany(
            "INSERT OR REPLACE INTO google_light_assertions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                (
                    a["assertion_id"],
                    a["assertion_type"],
                    a["subject"],
                    a["claim"],
                    a["evidence_count"],
                    a["evidence_refs_json"],
                    a["services_json"],
                    a["categories_json"],
                    a["privacy_tier"],
                    a["status"],
                    a["created_at"],
                )
                for a in assertions
            ],
        )
        con.commit()
    con.close()
    return stats, assertions


def write_report(stats: AssertStats, assertions: list[dict], path: Path = REPORT_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # privacy-safe: no raw activity titles in report top-level samples beyond subject/claim
    sample = [
        {
            "assertion_type": a["assertion_type"],
            "subject": a["subject"],
            "evidence_count": a["evidence_count"],
            "privacy_tier": a["privacy_tier"],
        }
        for a in sorted(assertions, key=lambda x: -x["evidence_count"])[:20]
    ]
    doc = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "phase": 16,
        "stats": stats.to_dict(),
        "top_assertions": sample,
        "notes": [
            "Light assertions are aggregate signals, not dialogue knowledge units.",
            "event_id namespace uses g| prefix; dialogue uses cm|.",
            "Maps and payment categories excluded from assertions.",
        ],
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Phase 16: Google light assertions")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--write", action="store_true")
    p.add_argument("--db", type=Path, default=GOOGLE_DB)
    p.add_argument("--report", type=Path, default=REPORT_PATH)
    args = p.parse_args(argv)
    write = bool(args.write)
    stats, assertions = build(args.db, write=write)
    write_report(stats, assertions, args.report)
    print(json.dumps(stats.to_dict(), ensure_ascii=False, indent=2))
    print(f"report: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
