"""Canonical product sync entry (post Phase 14–21).

Replaces day-to-day use of the legacy integrated ``rag-pipeline`` (steps 1–12).
Primary job: pull local conversation evidence from AgentsView into project DBs.

Usage::

    pk-sync conversations              # dry-run inventory + normalized + canonical
    pk-sync conversations --write      # actually publish DBs
    python -m personal_knowledge.application.sync conversations --write
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from personal_knowledge.core.project_paths import (
    AGENT_CONVERSATIONS_DB,
    AI_CONTEXT_DIR,
    GOOGLE_DB,
    UNIFIED_DB,
)


TURN_SUMMARIES = AI_CONTEXT_DIR / "conversation_summaries.json"


def _record_conversation_versions() -> list[dict]:
    from personal_knowledge.application.serving.versions import file_checksum, record_publication

    checksum = file_checksum(AGENT_CONVERSATIONS_DB)
    canonical = record_publication(
        UNIFIED_DB,
        registry_id="d.canonical_conversation",
        version=checksum,
        checksum=checksum,
        location_kind="sqlite_store",
        location_ref=str(AGENT_CONVERSATIONS_DB),
        source_key="agentsview",
        watermark_value=checksum,
    )
    message = record_publication(
        UNIFIED_DB,
        registry_id="d.canonical_message",
        version=checksum,
        checksum=checksum,
        location_kind="sqlite_view",
        location_ref=f"{AGENT_CONVERSATIONS_DB}#canonical_messages",
        source_key="canonical_conversation",
        watermark_value=checksum,
        evidence_version_id=canonical["artifact_version_id"],
    )
    return [canonical, message]


def _cmd_conversations(write: bool) -> int:
    from personal_knowledge.application.run_pipeline import run_agentsview_stage

    ok = run_agentsview_stage(write=write)
    if not ok:
        return 1
    publications = _record_conversation_versions() if write else []
    mode = "write" if write else "dry-run"
    print(f"\n[done] pk-sync conversations ({mode}) finished.")
    print("  SSOT: data/canonical/agent/structured/db/agent_conversations.sqlite")
    print("  Next (optional): pk-ku inspect → prepare → extract — not part of this command.")
    if publications:
        print(f"  Versions: {sum(int(x['created']) for x in publications)} new / {len(publications)} recorded")
    return 0


def _cmd_turns(write: bool) -> int:
    from personal_knowledge.application.conversation.build_conversation_vector_store import (
        COLLECTION_NAME,
        build,
    )
    from personal_knowledge.application.serving.versions import file_checksum, record_publication

    stats = build(write=write)
    publications: list[dict] = []
    if write:
        if not TURN_SUMMARIES.exists():
            print(f"[error] turn publication missing: {TURN_SUMMARIES}", file=sys.stderr)
            return 1
        if not stats.get("sample_search_ok"):
            print("[error] turn publication verification failed; versions not advanced", file=sys.stderr)
            return 1
        checksum = file_checksum(TURN_SUMMARIES)
        summary = record_publication(
            UNIFIED_DB,
            registry_id="s.turn_summary",
            version=checksum,
            checksum=checksum,
            location_kind="json_artifact",
            location_ref=str(TURN_SUMMARIES),
            source_key="canonical_message",
            watermark_value=checksum,
            metadata={"turn_count": stats.get("total_turns", stats.get("units_total", 0))},
        )
        vector = record_publication(
            UNIFIED_DB,
            registry_id="r.turn_vector",
            version=checksum,
            checksum=checksum,
            location_kind="chroma_collection",
            location_ref=COLLECTION_NAME,
            source_key="turn_summary",
            watermark_value=checksum,
            evidence_version_id=summary["artifact_version_id"],
            metadata={"count": stats.get("final_collection_count", 0)},
        )
        publications = [summary, vector]
    print(json.dumps({"command": "turns", "mode": "write" if write else "dry-run", "stats": stats, "publications": publications}, ensure_ascii=False, indent=2))
    return 0


def _cmd_google(write: bool, db_path: Path) -> int:
    from personal_knowledge.application.build_google_light_assertions import build as build_assertions
    from personal_knowledge.application.build_google_normalized_events import build as build_normalized
    from personal_knowledge.application.serving.versions import record_publication

    normalized = build_normalized(db_path, write=write)
    assertions, _ = build_assertions(db_path, write=write)
    publications: list[dict] = []
    if write:
        if not assertions.gate_passed or not assertions.promoted:
            print("[error] Google privacy/lifecycle gate failed; versions not advanced", file=sys.stderr)
            return 1
        norm = record_publication(
            UNIFIED_DB,
            registry_id="d.google_normalized",
            version=normalized.dataset_hash,
            checksum=normalized.dataset_hash,
            location_kind="sqlite_store",
            location_ref=f"{db_path}#normalized_events",
            source_key="google_activities",
            watermark_value=normalized.input_hash,
            producer_run_id=normalized.run_id,
            metadata={"count": normalized.after_count},
        )
        assertion = record_publication(
            UNIFIED_DB,
            registry_id="s.google_assertion",
            version=assertions.dataset_hash,
            checksum=assertions.dataset_hash,
            location_kind="sqlite_table",
            location_ref=f"{db_path}#google_light_assertions",
            source_key="google_normalized",
            watermark_value=assertions.input_hash,
            producer_run_id=assertions.run_id,
            evidence_version_id=norm["artifact_version_id"],
            metadata={"count": assertions.assertions},
        )
        publications = [norm, assertion]
    print(json.dumps({"command": "google", "mode": "write" if write else "dry-run", "normalized": normalized.to_dict(), "assertions": assertions.to_dict(), "publications": publications}, ensure_ascii=False, indent=2))
    return 0


def _cmd_status(json_output: bool) -> int:
    from personal_knowledge.application.knowledge.doctor_ku import _default_collection_inspector
    from personal_knowledge.application.serving.versions import file_checksum, json_checksum, publication_status

    report = publication_status(UNIFIED_DB)
    current: dict[str, str] = {}
    for registry_id, path in {
        "d.canonical_conversation": AGENT_CONVERSATIONS_DB,
        "d.canonical_message": AGENT_CONVERSATIONS_DB,
        "s.turn_summary": TURN_SUMMARIES,
    }.items():
        if path.exists():
            current[registry_id] = file_checksum(path)
    for registry_id, checksum in current.items():
        item = (report.get("artifacts") or {}).get(registry_id) or {}
        item["current_checksum"] = checksum
        item["drift"] = bool(item.get("checksum") and item["checksum"] != checksum)
    if TURN_SUMMARIES.exists():
        turn_source = file_checksum(TURN_SUMMARIES)
        item = (report.get("artifacts") or {}).get("r.turn_vector") or {}
        item["current_source_checksum"] = turn_source
        item["drift"] = bool(item.get("watermark_value") and item["watermark_value"] != turn_source)
    if GOOGLE_DB.exists():
        con = sqlite3.connect(f"file:{GOOGLE_DB.resolve().as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            runs = {str(row["run_type"]): dict(row) for row in con.execute("SELECT run_type,input_hash,dataset_hash FROM google_structure_runs WHERE status='current'")}
        except sqlite3.Error:
            runs = {}
        con.close()
        for registry_id, run_type in (("d.google_normalized", "normalized_events"), ("s.google_assertion", "light_assertions")):
            item = (report.get("artifacts") or {}).get(registry_id) or {}
            run = runs.get(run_type) or {}
            item["current_checksum"] = run.get("dataset_hash")
            item["current_source_checksum"] = run.get("input_hash")
            item["drift"] = bool(
                item.get("checksum") and (
                    item["checksum"] != run.get("dataset_hash")
                    or item.get("watermark_value") != run.get("input_hash")
                )
            )
    if UNIFIED_DB.exists():
        con = sqlite3.connect(f"file:{UNIFIED_DB.resolve().as_posix()}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        try:
            canonical_ids = [str(row[0]) for row in con.execute("SELECT canonical_unit_id FROM canonical_knowledge_units WHERE status='current' ORDER BY canonical_unit_id")]
            index = con.execute("SELECT collection_name,checksum FROM knowledge_index_versions WHERE status='active' ORDER BY activated_at DESC LIMIT 1").fetchone()
        except sqlite3.Error:
            canonical_ids, index = [], None
        con.close()
        canonical = (report.get("artifacts") or {}).get("s.knowledge_unit") or {}
        canonical_current = json_checksum(canonical_ids) if canonical_ids else ""
        canonical["current_checksum"] = canonical_current
        canonical["drift"] = bool(canonical.get("checksum") and canonical["checksum"] != canonical_current)
        retrieval = (report.get("artifacts") or {}).get("r.knowledge_index") or {}
        if index is not None:
            try:
                actual = dict(_default_collection_inspector(str(index["collection_name"])))
            except Exception as exc:  # noqa: BLE001
                actual = {"exists": False, "error": str(exc), "checksum": ""}
            retrieval["current_checksum"] = actual.get("checksum")
            retrieval["current_collection"] = str(index["collection_name"])
            retrieval["drift"] = bool(
                retrieval.get("checksum") and (
                    retrieval["checksum"] != actual.get("checksum")
                    or retrieval.get("location_ref") != str(index["collection_name"])
                )
            )
    drift = sorted(aid for aid, item in (report.get("artifacts") or {}).items() if item.get("drift"))
    report["drift"] = drift
    report["ok"] = bool(report.get("ok")) and not drift
    report["sources"] = {"conversation": str(AGENT_CONVERSATIONS_DB), "turns": str(TURN_SUMMARIES), "google": str(GOOGLE_DB), "knowledge": str(UNIFIED_DB)}
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"pk-sync status: {'OK' if report.get('ok') else 'NOT READY'}")
        for aid, item in (report.get("artifacts") or {}).items():
            print(f"  {aid}: {item.get('version') or '-'} drift={item.get('drift', False)}")
    return 0 if report.get("ok") else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pk-sync",
        description=(
            "Product data sync (canonical paths). "
            "Does NOT run legacy integrated steps 1–12 (personal_events / memory batch)."
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    conv = sub.add_parser(
        "conversations",
        help="AgentsView → normalized → canonical conversation SSOT",
    )
    conv.add_argument(
        "--write",
        action="store_true",
        help="Publish normalized + canonical DBs (default is dry-run)",
    )

    turns = sub.add_parser("turns", help="Turn summaries → conversation_turns vector publication")
    turns.add_argument("--write", action="store_true", help="Publish after build verification (default dry-run)")
    turns.add_argument("--dry-run", action="store_true")

    google = sub.add_parser("google", help="Google normalized events + privacy-gated assertions")
    google.add_argument("--write", action="store_true", help="Publish after privacy gate (default dry-run)")
    google.add_argument("--dry-run", action="store_true")
    google.add_argument("--db", type=Path, default=GOOGLE_DB)

    status = sub.add_parser("status", help="Read-only publication version/watermark status")
    status.add_argument("--json", action="store_true", help="Emit JSON")
    conv.add_argument(
        "--dry-run",
        action="store_true",
        help="Explicit dry-run (default when --write is absent)",
    )

    sub.add_parser(
        "help-legacy",
        help="Show how to invoke the retired integrated pipeline if ever needed",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "help-legacy":
        print(
            "Legacy integrated pipeline (personal_system / memory / PE vectors) is retired\n"
            "from product use. Modules remain in application/* for forensics only.\n\n"
            "Emergency re-run (not recommended):\n"
            "  set PK_ALLOW_LEGACY_PIPELINE=1\n"
            "  python -m personal_knowledge.application.run_pipeline --legacy-integrated --dry-run\n"
        )
        return 0

    if args.command == "conversations":
        write = bool(args.write)
        return _cmd_conversations(write=write)

    if args.command == "turns":
        return _cmd_turns(write=bool(args.write))

    if args.command == "google":
        return _cmd_google(write=bool(args.write), db_path=args.db)

    if args.command == "status":
        return _cmd_status(json_output=bool(args.json))

    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
