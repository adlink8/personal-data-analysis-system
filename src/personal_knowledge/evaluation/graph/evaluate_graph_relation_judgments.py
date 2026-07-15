"""Wave 9.3: 对 graph_relation_judgments 做 evidence gate，并生成 review queue。"""

from __future__ import annotations

import argparse
import json
import sqlite3
import time
from pathlib import Path

from personal_knowledge.domains.graph.build_graph_relation_candidates import SQLITE_DB, canonical_pair
from personal_knowledge.domains.graph.judge_graph_relations import ALLOWED_RELATIONS

ROOT = Path(__file__).resolve().parents[4]
OUT_JSON = ROOT / "integration" / "analysis" / "ai_context" / "graph_relation_eval_report.json"
OUT_MD = ROOT / "integration" / "analysis" / "ai_context" / "graph_relation_eval_report.md"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS graph_relation_review_queue (
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
CREATE INDEX IF NOT EXISTS idx_grrq_candidate ON graph_relation_review_queue(candidate_id);
CREATE INDEX IF NOT EXISTS idx_grrq_pair ON graph_relation_review_queue(pair_key);
"""

REVIEW_MIN_CONF = 0.55
ACCEPT_MIN_CONF = 0.75


def refs_match(evidence_refs: list[str], source_refs: list[str]) -> bool:
    if not evidence_refs:
        return False
    norm_source = [s.replace("\\", "/") for s in source_refs]
    for ref in evidence_refs:
        nref = ref.replace("\\", "/")
        if any(nref == s or nref in s or s in nref for s in norm_source):
            return True
    return False


def classify_rows(rows: list[dict]) -> tuple[list[dict], dict]:
    by_pair: dict[str, list[dict]] = {}
    for row in rows:
        pair_key = "|".join(canonical_pair(row["source_node_id"], row["target_node_id"]))
        row["pair_key"] = pair_key
        by_pair.setdefault(pair_key, []).append(row)

    review_items = []
    stats = {
        "accepted": 0,
        "rejected": 0,
        "review": 0,
        "by_relation_type": {},
        "reasons": {},
    }

    for pair_key, items in by_pair.items():
        strong_types = {
            r["relation_type"]
            for r in items
            if r["relation_type"] != "no_relation" and float(r["confidence"] or 0.0) >= ACCEPT_MIN_CONF
        }
        pair_conflict = len(strong_types) > 1
        for row in items:
            reasons = []
            relation_type = row["relation_type"]
            confidence = float(row["confidence"] or 0.0)
            evidence_refs = json.loads(row["evidence_refs_json"] or "[]")
            source_refs = json.loads(row["source_refs_json"] or "[]")
            risk_flags = json.loads(row["risk_flags_json"] or "[]")

            if relation_type == "no_relation":
                gate_status = "rejected"
                reasons.append("no_relation")
            elif relation_type not in ALLOWED_RELATIONS:
                gate_status = "rejected"
                reasons.append("invalid_relation_type")
            elif pair_conflict:
                gate_status = "review"
                reasons.append("pair_conflict")
            elif confidence < REVIEW_MIN_CONF:
                gate_status = "rejected"
                reasons.append("low_confidence")
            elif not refs_match(evidence_refs, source_refs):
                gate_status = "review"
                reasons.append("evidence_mismatch")
            elif risk_flags:
                gate_status = "review"
                reasons.append("risk_flags_present")
            elif confidence < ACCEPT_MIN_CONF:
                gate_status = "review"
                reasons.append("mid_confidence")
            else:
                gate_status = "accepted"
                reasons.append("accepted")

            row["gate_status"] = gate_status
            row["gate_reasons"] = reasons
            stats[gate_status] += 1
            stats["by_relation_type"][relation_type] = stats["by_relation_type"].get(relation_type, 0) + 1
            for reason in reasons:
                stats["reasons"][reason] = stats["reasons"].get(reason, 0) + 1

            if gate_status == "review":
                review_items.append({
                    "candidate_id": row["candidate_id"],
                    "pair_key": pair_key,
                    "review_reason": ",".join(reasons),
                    "relation_type": relation_type,
                    "confidence": confidence,
                    "evidence_refs_json": row["evidence_refs_json"],
                    "risk_flags_json": row["risk_flags_json"],
                })
    return review_items, stats


def load_rows() -> list[dict]:
    con = sqlite3.connect(SQLITE_DB)
    con.row_factory = sqlite3.Row
    try:
        sql = (
            "SELECT j.candidate_id, j.relation_type, j.confidence, j.evidence_refs_json, j.reason, "
            "j.risk_flags_json, j.model, j.prompt_version, j.temperature, j.created_at, j.gate_status, "
            "c.source_node_id, c.target_node_id, c.source_session_id, c.target_session_id, c.source_refs_json "
            "FROM graph_relation_judgments j JOIN graph_relation_candidates c ON c.candidate_id = j.candidate_id"
        )
        return [dict(r) for r in con.execute(sql).fetchall()]
    finally:
        con.close()


def persist(rows: list[dict], review_items: list[dict]) -> None:
    con = sqlite3.connect(SQLITE_DB)
    try:
        con.executescript(SCHEMA_SQL)
        con.execute("DELETE FROM graph_relation_review_queue")
        con.executemany(
            "UPDATE graph_relation_judgments SET gate_status=? WHERE candidate_id=?",
            [(r["gate_status"], r["candidate_id"]) for r in rows],
        )
        now = time.strftime("%Y-%m-%dT%H:%M:%S")
        payload = [(
            r["candidate_id"], r["pair_key"], r["review_reason"], r["relation_type"],
            r["confidence"], r["evidence_refs_json"], r["risk_flags_json"], now,
        ) for r in review_items]
        con.executemany(
            "INSERT INTO graph_relation_review_queue "
            "(candidate_id, pair_key, review_reason, relation_type, confidence, evidence_refs_json, risk_flags_json, created_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            payload,
        )
        con.commit()
    finally:
        con.close()


def render_md(report: dict) -> str:
    lines = ["# Graph Relation Eval Report", ""]
    lines.append(f"- total: {report['total']}")
    lines.append(f"- accepted: {report['accepted']}")
    lines.append(f"- rejected: {report['rejected']}")
    lines.append(f"- review: {report['review']}")
    lines.append("")
    lines.append("## By Relation Type")
    lines.append("")
    for k, v in sorted(report["by_relation_type"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("## Gate Reasons")
    lines.append("")
    for k, v in sorted(report["reasons"].items()):
        lines.append(f"- {k}: {v}")
    lines.append("")
    if report.get("review_examples"):
        lines.append("## Review Examples")
        lines.append("")
        for item in report["review_examples"]:
            lines.append(
                f"- {item['candidate_id']} | {item['relation_type']} | conf={item['confidence']} | {item['review_reason']}"
            )
        lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Wave 9.3 evidence gate")
    p.add_argument("--write", action="store_true")
    args = p.parse_args(argv)
    rows = load_rows()
    if not rows:
        print("[warn] 无 graph_relation_judgments 可评估")
        return 0
    review_items, stats = classify_rows(rows)
    report = {
        "total": len(rows),
        **stats,
        "review_examples": review_items[:10],
    }
    md = render_md(report)
    print(md)
    if args.write:
        persist(rows, review_items)
        OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        OUT_MD.write_text(md, encoding="utf-8")
        print(f"[write] {OUT_JSON.relative_to(ROOT)}")
        print(f"[write] {OUT_MD.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
