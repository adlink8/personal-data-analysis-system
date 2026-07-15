"""Phase 10 Wave 2: deterministic gate for memory relation candidates."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any

from personal_knowledge.domains.memory.build_memory_relation_candidates import ALLOWED_RELATION_TYPES, DB_PATH


ROOT = Path(__file__).resolve().parents[4]
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "memory_relation_eval_report.json"
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "memory_relation_eval_report.md"

REVIEW_MIN_CONF = 0.55
ACCEPT_MIN_CONF = 0.80

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS memory_relation_judgments (
    candidate_id TEXT PRIMARY KEY,
    package_id TEXT NOT NULL,
    source_memory_id TEXT NOT NULL,
    target_memory_id TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    source_refs_json TEXT NOT NULL,
    risk_flags_json TEXT NOT NULL,
    candidate_reason TEXT NOT NULL,
    gate_status TEXT NOT NULL,
    gate_reasons_json TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    llm_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mrj_gate_status ON memory_relation_judgments(gate_status);
CREATE INDEX IF NOT EXISTS idx_mrj_relation_type ON memory_relation_judgments(relation_type);

CREATE TABLE IF NOT EXISTS memory_relation_review_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL,
    pair_key TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    relation_type TEXT NOT NULL,
    confidence REAL NOT NULL,
    evidence_refs_json TEXT NOT NULL,
    risk_flags_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_mrrq_candidate_id ON memory_relation_review_queue(candidate_id);
CREATE INDEX IF NOT EXISTS idx_mrrq_pair_key ON memory_relation_review_queue(pair_key);
"""


def json_loads_list(raw: object) -> list[Any]:
    if isinstance(raw, list):
        return raw
    if raw is None:
        return []
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(parsed, list):
        return parsed
    return [parsed]


def canonical_pair(left: str, right: str) -> tuple[str, str]:
    return (left, right) if left <= right else (right, left)


def load_candidate_rows(con: sqlite3.Connection) -> list[dict[str, Any]]:
    con.row_factory = sqlite3.Row
    rows = con.execute(
        """
        SELECT candidate_id, package_id, source_memory_id, target_memory_id, relation_type,
               confidence, candidate_reason, evidence_refs_json, source_refs_json,
               allowed_refs_json, risk_flags_json, llm_status, model, prompt_version, created_at
        FROM memory_relation_candidates
        ORDER BY candidate_id
        """
    ).fetchall()
    return [dict(row) for row in rows]


def classify_candidates(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pair_key = "|".join(canonical_pair(row["source_memory_id"], row["target_memory_id"]))
        row["pair_key"] = pair_key
        by_pair.setdefault(pair_key, []).append(row)

    judgments: list[dict[str, Any]] = []
    review_items: list[dict[str, Any]] = []
    stats = {
        "accepted": 0,
        "review": 0,
        "rejected": 0,
        "by_relation_type": {},
        "reasons": {},
    }

    for pair_key, items in by_pair.items():
        strong_types = {
            row["relation_type"]
            for row in items
            if row["relation_type"] != "no_relation" and float(row["confidence"] or 0.0) >= ACCEPT_MIN_CONF
        }
        pair_conflict = len(strong_types) > 1
        for row in items:
            relation_type = str(row["relation_type"] or "").strip()
            confidence = round(max(0.0, min(1.0, float(row["confidence"] or 0.0))), 4)
            evidence_refs = [str(x) for x in json_loads_list(row["evidence_refs_json"]) if str(x).strip()]
            source_refs = [str(x) for x in json_loads_list(row["source_refs_json"]) if str(x).strip()]
            allowed_refs = {str(x) for x in json_loads_list(row["allowed_refs_json"]) if str(x).strip()}
            risk_flags = [str(x) for x in json_loads_list(row["risk_flags_json"]) if str(x).strip()]
            reasons: list[str] = []

            if row["source_memory_id"] == row["target_memory_id"]:
                gate_status = "rejected"
                reasons.append("self_loop")
            elif relation_type not in (ALLOWED_RELATION_TYPES - {"no_relation"}):
                gate_status = "rejected"
                reasons.append("unknown_relation_type")
            elif confidence < REVIEW_MIN_CONF:
                gate_status = "rejected"
                reasons.append("low_confidence")
            elif not evidence_refs or any(ref not in allowed_refs for ref in evidence_refs):
                gate_status = "rejected"
                reasons.append("unsupported_evidence")
            elif source_refs and any(ref not in allowed_refs for ref in source_refs):
                gate_status = "rejected"
                reasons.append("unsupported_source_refs")
            elif pair_conflict:
                gate_status = "review"
                reasons.append("pair_conflict")
            elif risk_flags:
                gate_status = "review"
                reasons.append("risk_flags_present")
            elif confidence < ACCEPT_MIN_CONF:
                gate_status = "review"
                reasons.append("mid_confidence")
            else:
                gate_status = "accepted"
                reasons.append("accepted")

            judgment = {
                "candidate_id": row["candidate_id"],
                "package_id": row["package_id"],
                "source_memory_id": row["source_memory_id"],
                "target_memory_id": row["target_memory_id"],
                "relation_type": relation_type,
                "confidence": confidence,
                "evidence_refs_json": json.dumps(evidence_refs, ensure_ascii=False),
                "source_refs_json": json.dumps(source_refs, ensure_ascii=False),
                "risk_flags_json": json.dumps(risk_flags, ensure_ascii=False),
                "candidate_reason": row["candidate_reason"],
                "gate_status": gate_status,
                "gate_reasons_json": json.dumps(reasons, ensure_ascii=False),
                "model": row["model"],
                "prompt_version": row["prompt_version"],
                "llm_status": row["llm_status"],
                "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "pair_key": pair_key,
                "review_reason": ",".join(reasons),
            }
            judgments.append(judgment)
            stats[gate_status] += 1
            stats["by_relation_type"][relation_type] = stats["by_relation_type"].get(relation_type, 0) + 1
            for reason in reasons:
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1
            if gate_status == "review":
                review_items.append(
                    {
                        "candidate_id": row["candidate_id"],
                        "pair_key": pair_key,
                        "review_reason": ",".join(reasons),
                        "relation_type": relation_type,
                        "confidence": confidence,
                        "evidence_refs_json": json.dumps(evidence_refs, ensure_ascii=False),
                        "risk_flags_json": json.dumps(risk_flags, ensure_ascii=False),
                    }
                )

    return judgments, review_items, stats


def persist(con: sqlite3.Connection, judgments: list[dict[str, Any]], review_items: list[dict[str, Any]]) -> None:
    con.executescript(SCHEMA_SQL)
    con.execute("DELETE FROM memory_relation_judgments")
    con.execute("DELETE FROM memory_relation_review_queue")
    con.executemany(
        """
        INSERT INTO memory_relation_judgments (
            candidate_id, package_id, source_memory_id, target_memory_id, relation_type,
            confidence, evidence_refs_json, source_refs_json, risk_flags_json, candidate_reason,
            gate_status, gate_reasons_json, model, prompt_version, llm_status, created_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                row["candidate_id"],
                row["package_id"],
                row["source_memory_id"],
                row["target_memory_id"],
                row["relation_type"],
                row["confidence"],
                row["evidence_refs_json"],
                row["source_refs_json"],
                row["risk_flags_json"],
                row["candidate_reason"],
                row["gate_status"],
                row["gate_reasons_json"],
                row["model"],
                row["prompt_version"],
                row["llm_status"],
                row["created_at"],
            )
            for row in judgments
        ],
    )
    con.executemany(
        """
        INSERT INTO memory_relation_review_queue (
            candidate_id, pair_key, review_reason, relation_type,
            confidence, evidence_refs_json, risk_flags_json, created_at
        ) VALUES (?,?,?,?,?,?,?,?)
        """,
        [
            (
                row["candidate_id"],
                row["pair_key"],
                row["review_reason"],
                row["relation_type"],
                row["confidence"],
                row["evidence_refs_json"],
                row["risk_flags_json"],
                time.strftime("%Y-%m-%dT%H:%M:%S"),
            )
            for row in review_items
        ],
    )
    con.commit()


def build_report(judgments: list[dict[str, Any]], review_items: list[dict[str, Any]], stats: dict[str, Any]) -> dict[str, Any]:
    return {
        "total": len(judgments),
        **stats,
        "accepted_examples": [
            {
                "candidate_id": row["candidate_id"],
                "relation_type": row["relation_type"],
                "confidence": row["confidence"],
            }
            for row in judgments
            if row["gate_status"] == "accepted"
        ][:10],
        "review_examples": review_items[:10],
        "rejected_examples": [
            {
                "candidate_id": row["candidate_id"],
                "relation_type": row["relation_type"],
                "reasons": json_loads_list(row["gate_reasons_json"]),
            }
            for row in judgments
            if row["gate_status"] == "rejected"
        ][:10],
    }


def render_md(report: dict[str, Any]) -> str:
    lines = [
        "# Memory Relation Eval Report",
        "",
        f"- total: {report['total']}",
        f"- accepted: {report['accepted']}",
        f"- review: {report['review']}",
        f"- rejected: {report['rejected']}",
        "",
        "## By Relation Type",
        "",
    ]
    for key, value in sorted(report["by_relation_type"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Gate Reasons", ""])
    for key, value in sorted(report["reasons"].items()):
        lines.append(f"- `{key}`: {value}")
    if report["review_examples"]:
        lines.extend(["", "## Review Examples", ""])
        for item in report["review_examples"]:
            lines.append(
                f"- `{item['candidate_id']}` | `{item['relation_type']}` | conf={item['confidence']} | {item['review_reason']}"
            )
    return "\n".join(lines) + "\n"


def run(*, db_path: Path, write: bool) -> dict[str, Any]:
    with closing(sqlite3.connect(db_path)) as con:
        rows = load_candidate_rows(con)
        judgments, review_items, stats = classify_candidates(rows)
        if write:
            persist(con, judgments, review_items)
    report = build_report(judgments, review_items, stats)
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Phase 10 memory relation candidates.")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--db", type=Path, default=DB_PATH)
    args = parser.parse_args(argv)

    if not args.db.exists():
        print(f"[error] 缺少数据库: {args.db}", file=sys.stderr)
        return 1

    report = run(db_path=args.db, write=args.write)
    md = render_md(report)
    print(md)
    if args.write:
        OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        print(f"[write] {OUT_JSON}")
        print(f"[write] {OUT_MD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
