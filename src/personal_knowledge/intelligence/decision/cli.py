"""Local CLI for decision reads and explicitly confirmed append-only writes."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from typing import Any

from personal_knowledge.core.project_paths import UNIFIED_DB

from .service import DecisionFeedbackService, INTERFACE_SCHEMA_VERSION
from .state_machine import (
    DecisionStateError,
    record_action,
    record_confirmation,
    record_outcome,
)


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pk-decision")
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    commands = parser.add_subparsers(dest="command", required=True)

    recommendations = commands.add_parser("recommendations")
    reads = recommendations.add_subparsers(dest="read_command", required=True)
    listing = reads.add_parser("list")
    listing.add_argument("--domain")
    listing.add_argument("--limit", type=int, default=50)
    _common(listing)
    for name in ("get", "history", "outcomes", "effectiveness"):
        item = reads.add_parser(name)
        item.add_argument("--recommendation-id", required=True)
        if name != "get":
            item.add_argument("--limit", type=int, default=50)
        _common(item)

    for name in ("confirm", "action", "outcome"):
        write = commands.add_parser(name)
        write.add_argument("--recommendation-id", required=True)
        write.add_argument("--recommendation-checksum", required=True)
        write.add_argument("--write", action="store_true")
        write.add_argument("--i-confirm")
        write.add_argument("--actor-class", required=True)
        write.add_argument("--actor-identity-hash", required=True)
        write.add_argument("--expected-sequence", type=int, required=True)
        write.add_argument("--idempotency-key", required=True)
        write.add_argument("--occurred-at", required=True)
        _common(write)
        if name == "confirm":
            write.add_argument("--decision", required=True, choices=("accept", "reject", "defer", "revoke_before_action"))
            write.add_argument("--reason-code", required=True)
        elif name == "action":
            write.add_argument("--action-state", required=True, choices=("planned", "started", "completed", "abandoned", "not_taken"))
            write.add_argument("--source-class", default="user_attested", choices=("user_attested", "user_external_ref"))
            write.add_argument("--reason-code", required=True)
            write.add_argument("--external-ref-checksum")
        else:
            write.add_argument("--action-id", required=True)
            write.add_argument("--action-checksum", required=True)
            write.add_argument("--source-class", required=True, choices=("user_reported", "evidence_measured"))
            write.add_argument("--measurement-definition", required=True)
            write.add_argument("--metric", required=True)
            write.add_argument("--baseline-value", type=float)
            write.add_argument("--target-value", type=float)
            write.add_argument("--observed-value", type=float)
            write.add_argument("--unit", required=True)
            write.add_argument("--direction", required=True, choices=("increase", "decrease", "maintain"))
            write.add_argument("--window-start", required=True)
            write.add_argument("--window-end", required=True)
            write.add_argument("--adherence-status", required=True, choices=("adhered", "non_adherent", "unknown"))
            write.add_argument("--confidence", required=True, type=float)
            write.add_argument("--evidence-ref-json", action="append", default=[])
            write.add_argument("--uncertainty", action="append", default=[])
            write.add_argument("--confounder", action="append", default=[])
            write.add_argument("--concurrent-action", action="append", default=[])

    acceptance = commands.add_parser("acceptance")
    acceptance.add_argument("--dry-run", action="store_true")
    acceptance.add_argument("--metadata-only", action="store_true")
    _common(acceptance)
    return parser


def _error(operation: str, code: str, detail: str = "") -> dict[str, Any]:
    return DecisionFeedbackService._error(operation, code, detail)


def _guard(args: argparse.Namespace) -> dict[str, Any] | None:
    if not args.write:
        return _error(args.command, "write_required")
    if not args.i_confirm:
        return _error(args.command, "confirmation_required")
    if args.i_confirm != args.recommendation_id:
        return _error(args.command, "confirmation_mismatch")
    if args.actor_class != "user" or len(args.actor_identity_hash) != 64:
        return _error(args.command, "human_actor_required")
    if args.expected_sequence < 1:
        return _error(args.command, "invalid_expected_sequence")
    if not args.idempotency_key.strip():
        return _error(args.command, "idempotency_key_required")
    return None


def _receipt(operation: str, value: Any) -> dict[str, Any]:
    return {
        "schema_version": INTERFACE_SCHEMA_VERSION,
        "operation": operation,
        "ok": True,
        "status": "written",
        "receipt": asdict(value),
        "privacy": {"metadata_only": True, "private_bodies": 0},
        "external_actions": 0,
    }


def _invoke(args: argparse.Namespace) -> dict[str, Any]:
    service = DecisionFeedbackService(args.db)
    if args.command == "recommendations":
        operation = f"recommendations.{args.read_command}"
        params = vars(args).copy()
        for key in ("db", "command", "read_command", "json"):
            params.pop(key, None)
        return service.invoke(operation, **params)
    if args.command == "acceptance":
        if not args.dry_run or not args.metadata_only:
            return _error("acceptance", "dry_run_metadata_only_required")
        return _error("acceptance", "not_implemented")
    blocked = _guard(args)
    if blocked:
        return blocked
    try:
        common = dict(
            recommendation_id=args.recommendation_id,
            recommendation_checksum=args.recommendation_checksum,
            actor_class=args.actor_class,
            actor_identity_hash=args.actor_identity_hash,
            expected_sequence=args.expected_sequence,
            idempotency_key=args.idempotency_key,
            occurred_at=args.occurred_at,
        )
        if args.command == "confirm":
            value = record_confirmation(
                args.db, **common, decision=args.decision, reason_code=args.reason_code
            )
        elif args.command == "action":
            value = record_action(
                args.db, **common, action_state=args.action_state,
                source_class=args.source_class, reason_code=args.reason_code,
                external_ref_checksum=args.external_ref_checksum,
            )
        else:
            refs = tuple(json.loads(item) for item in args.evidence_ref_json)
            value = record_outcome(
                args.db, **common, action_id=args.action_id,
                action_checksum=args.action_checksum, source_class=args.source_class,
                measurement_definition=args.measurement_definition, metric=args.metric,
                baseline_value=args.baseline_value, target_value=args.target_value,
                observed_value=args.observed_value, unit=args.unit,
                direction=args.direction, window_start=args.window_start,
                window_end=args.window_end, adherence_status=args.adherence_status,
                evidence_refs=refs, confidence=args.confidence,
                uncertainty=tuple(args.uncertainty), confounders=tuple(args.confounder),
                concurrent_actions=tuple(args.concurrent_action),
            )
        return _receipt(args.command, value)
    except DecisionStateError as exc:
        return _error(args.command, exc.code, exc.detail)
    except (json.JSONDecodeError, TypeError, ValueError) as exc:
        return _error(args.command, "invalid_write_arguments", str(exc))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = _invoke(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())

