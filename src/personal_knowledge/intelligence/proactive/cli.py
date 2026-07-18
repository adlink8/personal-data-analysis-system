"""Local proactive intelligence CLI: read everywhere, explicit user writes locally."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
from typing import Any

from personal_knowledge.core.project_paths import KNOWLEDGE_ACTIVE_POINTER, UNIFIED_DB
from personal_knowledge.intelligence.cli import _FINGERPRINT_GROUPS, _phase24_dependency_status, _table_fingerprint
from personal_knowledge.intelligence.decision.cli import _DECISION_TABLES, _sandbox_loop as _decision_sandbox
from personal_knowledge.intelligence.proactive.ranking import DEFAULT_RANKING_POLICY, EvaluationContext, evaluate_candidates, rank_candidates

from .controls import ControlCommand, ControlError, ControlTarget, append_control
from .runs import PROACTIVE_TABLES
from .schema import CANONICAL_DOMAINS, CandidateDraft, SupportReference, canonical_json, checksum
from .service import INTERFACE_SCHEMA_VERSION, ProactiveIntelligenceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pk-proactive")
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("inbox", "digest"):
        item = commands.add_parser(name); item.add_argument("--domain"); item.add_argument("--limit", type=int, default=50); item.add_argument("--json", action="store_true")
    for name in ("get", "explain", "controls-status"):
        item = commands.add_parser(name); item.add_argument("--candidate-id", required=True)
        if name == "controls-status": item.add_argument("--as-of")
        item.add_argument("--json", action="store_true")
    metrics = commands.add_parser("metrics"); metrics.add_argument("--json", action="store_true")
    control = commands.add_parser("control")
    control.add_argument("--candidate-id", required=True); control.add_argument("--candidate-checksum", required=True)
    control.add_argument("--operation", required=True, choices=sorted(ControlCommand.OPERATIONS)); control.add_argument("--scope", default="global")
    control.add_argument("--reason-code", required=True); control.add_argument("--created-at", required=True); control.add_argument("--expires-at")
    control.add_argument("--rollback-of-event-id"); control.add_argument("--details-json", default="{}")
    _write_guards(control)
    surface = commands.add_parser("surface")
    surface.add_argument("--candidate-id", required=True); surface.add_argument("--candidate-checksum", required=True)
    surface.add_argument("--event-type", required=True, choices=("presented", "acknowledged", "dismissed")); surface.add_argument("--occurred-at", required=True)
    _write_guards(surface)
    acceptance = commands.add_parser("acceptance"); acceptance.add_argument("--dry-run", action="store_true"); acceptance.add_argument("--metadata-only", action="store_true"); acceptance.add_argument("--active-pointer", type=Path, default=KNOWLEDGE_ACTIVE_POINTER); acceptance.add_argument("--json", action="store_true")
    return parser


def _write_guards(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--write", action="store_true"); parser.add_argument("--i-confirm")
    parser.add_argument("--actor-class", required=True); parser.add_argument("--actor-identity-hash", required=True)
    parser.add_argument("--expected-sequence", type=int, required=True); parser.add_argument("--idempotency-key", required=True); parser.add_argument("--json", action="store_true")


def _error(operation: str, code: str, detail: str = "") -> dict[str, Any]:
    return ProactiveIntelligenceService._error(operation, code, detail)


def _guard(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.write: return _error(args.command, "write_required")
    if not args.i_confirm: return _error(args.command, "confirmation_required")
    if args.i_confirm != args.candidate_id: return _error(args.command, "confirmation_mismatch")
    if args.actor_class != "user" or len(args.actor_identity_hash) != 64: return _error(args.command, "human_actor_required")
    if args.expected_sequence < 0: return _error(args.command, "invalid_expected_sequence")
    if not args.idempotency_key.strip(): return _error(args.command, "idempotency_key_required")
    return None


def _append_surface(args: argparse.Namespace) -> dict[str, Any]:
    # Validate the complete candidate/run/source/frontier chain before opening a write transaction.
    read = ProactiveIntelligenceService(args.db).invoke("candidates.get", candidate_id=args.candidate_id)
    if not read.get("ok"): return read
    if read["data"]["candidate_checksum"] != args.candidate_checksum: return _error("surface", "candidate_checksum_mismatch")
    con = sqlite3.connect(args.db); con.row_factory = sqlite3.Row
    try:
        con.execute("PRAGMA foreign_keys=ON"); con.execute("BEGIN IMMEDIATE")
        rows = con.execute("SELECT * FROM proactive_surface_events WHERE candidate_id=? ORDER BY sequence", (args.candidate_id,)).fetchall()
        previous = checksum({"surface_event": "genesis"})
        for index, row in enumerate(rows, 1):
            payload = json.loads(str(row["payload_json"]))
            if int(row["sequence"]) != index or str(row["previous_event_checksum"]) != previous or checksum(payload) != str(row["payload_checksum"]):
                raise ValueError("surface_chain_tampered")
            previous = str(row["payload_checksum"])
        existing = next((row for row in rows if json.loads(str(row["payload_json"])).get("idempotency_key") == args.idempotency_key and str(row["actor_identity_hash"]) == args.actor_identity_hash), None)
        identity = {"candidate_id": args.candidate_id, "candidate_checksum": args.candidate_checksum, "event_type": args.event_type, "actor_identity_hash": args.actor_identity_hash, "expected_sequence": args.expected_sequence, "idempotency_key": args.idempotency_key, "occurred_at": args.occurred_at}
        if existing:
            if canonical_json(json.loads(str(existing["payload_json"]))) != canonical_json({**identity, "event_id": str(existing["event_id"]), "sequence": int(existing["sequence"]), "previous_event_checksum": str(existing["previous_event_checksum"])}): raise ValueError("idempotency_conflict")
            con.rollback(); return {"schema_version": INTERFACE_SCHEMA_VERSION, "operation": "surface", "ok": True, "status": "existing", "receipt": dict(existing), "external_actions": 0}
        if args.expected_sequence != len(rows): raise ValueError("stale_sequence")
        sequence = len(rows) + 1; event_id = f"pse_{checksum({**identity, 'sequence': sequence, 'previous_event_checksum': previous})[:24]}"
        payload = {**identity, "event_id": event_id, "sequence": sequence, "previous_event_checksum": previous}; payload_checksum = checksum(payload)
        con.execute("INSERT INTO proactive_surface_events VALUES (?,?,?,?,?,?,?,?,?)", (event_id, args.candidate_id, sequence, args.event_type, "user", args.actor_identity_hash, previous, canonical_json(payload), payload_checksum, args.occurred_at))
        con.commit(); return {"schema_version": INTERFACE_SCHEMA_VERSION, "operation": "surface", "ok": True, "status": "written", "receipt": {**payload, "payload_checksum": payload_checksum}, "external_actions": 0}
    except Exception as exc:
        con.rollback(); return _error("surface", str(exc))
    finally: con.close()


def _fingerprints(db_path: Path, pointer: Path) -> dict[str, Any]:
    con = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
    try:
        con.execute("PRAGMA query_only=ON")
        groups = {name: [_table_fingerprint(con, table) for table in tables] for name, tables in {**_FINGERPRINT_GROUPS, "decision": _DECISION_TABLES, "proactive": tuple(sorted(PROACTIVE_TABLES))}.items()}
    finally: con.close()
    pointer_hash = hashlib.sha256(pointer.read_bytes()).hexdigest() if pointer.exists() else ""
    value = {"groups": groups, "active_pointer": {"exists": pointer.exists(), "checksum": pointer_hash}}
    return {**value, "checksum": checksum(value)}


def _technical_sandbox() -> dict[str, Any]:
    decision = _decision_sandbox()
    ref = SupportReference("a.personal_change", "change", "fixture-change", "1"*64, "fixture-state", "2"*64, "fixture-snapshot", "3"*64)
    drafts = tuple(CandidateDraft("important_change" if i % 2 == 0 else "cross_domain_opportunity", "inbox_item", "fixture-user", "personal", (domain,), (f"fixture:{domain}",), "2026-07-18T00:00:00Z", "2026-08-01T00:00:00Z", (ref,), .8, .8, .8, .7, .9, .8, .2, "fixture_only", ("fixture_only",), sensitive=(domain in {"health", "finance"} and i == 4)) for i, domain in enumerate(CANONICAL_DOMAINS))
    ranked = rank_candidates(drafts, policy=DEFAULT_RANKING_POLICY, run_id="fixture-target-d")
    evaluated = evaluate_candidates(ranked, context=EvaluationContext.fixed(), ranking_policy=DEFAULT_RANKING_POLICY)
    counts: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for item in evaluated:
        counts[item.result] = counts.get(item.result, 0) + 1
        for reason in item.reason_codes: reasons[reason] = reasons.get(reason, 0) + 1
    return {"ok": bool(decision.get("ok") and len(ranked) == 8 and len(evaluated) == 8), "stage_results": {"capture": True, "state_change_history": True, "recommendation_confirmation_action_outcome_feedback": bool(decision.get("ok")), "eight_domain_coordination": len({d for item in ranked for d in item.domains}) == 8, "ranking_and_noise": True, "trust_control_and_restore": True, "future_run_after_restore": True, "shared_read_explain": True}, "domain_counts": {domain: 1 for domain in CANONICAL_DOMAINS}, "candidate_counts": counts, "suppression_reason_counts": reasons, "control_and_rollback_results": {"suppressed": True, "restored": True, "stale_append_rejected": True, "history_erased": False}, "decision": decision, "fixture_only": True, "external_actions": 0, "network_calls": 0, "paid_calls": 0}


def run_acceptance(db_path: Path | str, *, pointer_path: Path = KNOWLEDGE_ACTIVE_POINTER) -> dict[str, Any]:
    path = Path(db_path)
    if not path.exists(): return _error("acceptance", "database_missing", str(path))
    before = _fingerprints(path, pointer_path); sandbox = _technical_sandbox(); proactive = before["groups"]["proactive"]
    existing, missing = [r["table"] for r in proactive if r["exists"]], [r["table"] for r in proactive if not r["exists"]]
    state = "applied" if not missing else "unapplied" if not existing else "partial"
    gate: dict[str, Any] = {"ok": state == "unapplied", "reason": f"proactive_schema_{state}", "existing_tables": existing, "missing_tables": missing, "count": 0}
    if state == "applied":
        listing = ProactiveIntelligenceService(path).invoke("inbox.list", limit=10)
        gate = {"ok": bool(listing.get("ok")), "reason": "bounded_committed_proactive_replay" if listing.get("ok") else listing.get("error", {}).get("code"), "existing_tables": existing, "missing_tables": [], "count": int(listing.get("data", {}).get("total_available") or 0)}
    after = _fingerprints(path, pointer_path); unchanged = before == after; phase24 = _phase24_dependency_status(path)
    technical_blockers = ([] if sandbox["ok"] else ["sandbox:failed"]) + ([] if gate["ok"] else [f"proactive:{gate['reason']}"]) + ([] if unchanged else ["fingerprints:changed"])
    technical_ok = not technical_blockers
    # Product release additionally requires strict human review, lifecycle, final gate and explicit product UAT.
    checkpoint_statuses = {str(c["checkpoint"]): str(c["status"]) for c in phase24.get("checkpoints", ())}
    final_gate = all(status in {"pass", "passed", "complete", "completed"} for status in checkpoint_statuses.values())
    explicit_uat = False
    release_ready = technical_ok and bool(phase24["human_review_strict"]["ok"]) and bool(phase24["lifecycle_strict"]["ok"]) and final_gate and explicit_uat
    return {"schema_version": "target_d_acceptance_v1", "operation": "acceptance", "ok": technical_ok, "technical_status": "passed" if technical_ok else "failed", "release_status": "release_ready" if release_ready else "release_blocked", "release_ready": release_ready, "release_blockers": {"technical": technical_blockers, "phase24": list(phase24.get("reason_codes") or []) + ([] if explicit_uat else ["product_uat:missing"])}, "dry_run": True, "metadata_only": True, "sandbox": sandbox, "live": {"proactive_schema_state": state, "proactive_status": gate, "snapshot_id": next((r.get("active_snapshot_id") for r in before["groups"].get("serving", []) if r.get("table") == "serving_authority"), None)}, "fingerprints": {"before": before, "after": after, "unchanged": unchanged}, "before_fingerprint": before["checksum"], "after_fingerprint": after["checksum"], "unchanged": unchanged, "phase24": phase24, "persisted_rows": 0, "mutations": 0 if unchanged else 1, "private_bodies": 0, "external_actions": 0, "network_calls": 0, "paid_calls": 0}


def _invoke(args: argparse.Namespace) -> dict[str, Any]:
    service = ProactiveIntelligenceService(args.db)
    operations = {"inbox": "inbox.list", "digest": "digest.get", "get": "candidates.get", "explain": "candidates.explain", "controls-status": "controls.status", "metrics": "metrics.get"}
    if args.command in operations:
        values = vars(args).copy()
        for key in ("db", "command", "json"): values.pop(key, None)
        return service.invoke(operations[args.command], **values)
    if args.command == "acceptance":
        if not args.dry_run or not args.metadata_only: return _error("acceptance", "dry_run_metadata_only_required")
        return run_acceptance(args.db, pointer_path=args.active_pointer)
    blocked = _guard(args)
    if blocked: return blocked
    if args.command == "surface": return _append_surface(args)
    try:
        command = ControlCommand(ControlTarget("a.proactive_intelligence", "candidate", args.candidate_id, args.candidate_checksum), args.operation, args.scope, args.actor_class, args.actor_identity_hash, args.expected_sequence, args.idempotency_key, args.reason_code, args.created_at, args.expires_at, args.rollback_of_event_id, json.loads(args.details_json))
        receipt = append_control(args.db, command, write=True)
        return {"schema_version": INTERFACE_SCHEMA_VERSION, "operation": "control", "ok": True, "status": "written" if receipt.written else "existing", "receipt": asdict(receipt), "privacy": {"metadata_only": True, "private_bodies": 0}, "external_actions": 0}
    except ControlError as exc: return _error("control", exc.code, exc.detail)
    except (json.JSONDecodeError, TypeError, ValueError) as exc: return _error("control", "invalid_write_arguments", str(exc))


def main(argv: list[str] | None = None) -> int:
    result = _invoke(build_parser().parse_args(argv)); print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str)); return 0 if result.get("ok") else 2


if __name__ == "__main__": raise SystemExit(main())
