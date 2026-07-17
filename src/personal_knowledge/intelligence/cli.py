"""JSON CLI for read-only personal-state intelligence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from personal_knowledge.core.project_paths import UNIFIED_DB

from .service import IntelligenceService


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="personal-state-intelligence")
    parser.add_argument("--db", type=Path, default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    state = sub.add_parser("state")
    state_sub = state.add_subparsers(dest="state_command", required=True)
    for name in ("current", "history"):
        item = state_sub.add_parser(name)
        _context_args(item)
        item.add_argument("--limit", type=int, default=50)
    explain = state_sub.add_parser("explain")
    _context_args(explain)
    for field in ("assertion-kind", "subject", "domain", "scope", "predicate"):
        explain.add_argument(f"--{field}", required=True)

    changes = sub.add_parser("changes")
    changes_sub = changes.add_subparsers(dest="changes_command", required=True)
    recent = changes_sub.add_parser("recent")
    _context_args(recent)
    recent.add_argument("--window-start")
    recent.add_argument("--limit", type=int, default=50)

    build = sub.add_parser("build", help="Plan a future analysis run; dry-run only in Phase 25")
    build.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    build.add_argument("--write", action="store_true", help="Reserved; rejected in Phase 25")
    build.add_argument("--json", action="store_true")
    return parser


def _context_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--snapshot-id")
    parser.add_argument("--run-id")
    parser.add_argument("--as-of")
    parser.add_argument("--json", action="store_true")


def _invoke(args: argparse.Namespace) -> dict[str, Any]:
    if args.command == "build":
        if args.write or not args.dry_run:
            return {
                "schema_version": "personal_state_interface_v1",
                "operation": "build",
                "ok": False,
                "status": "error",
                "error": {"code": "write_not_available", "detail": "Phase 25 is dry-run only"},
                "privacy": {"metadata_only": True, "private_bodies": 0},
            }
        return {
            "schema_version": "personal_state_interface_v1",
            "operation": "build",
            "ok": True,
            "status": "empty",
            "dry_run": True,
            "written": False,
            "privacy": {"metadata_only": True, "private_bodies": 0},
        }
    service = IntelligenceService(args.db or UNIFIED_DB)
    common = {
        "snapshot_id": args.snapshot_id,
        "run_id": args.run_id,
        "as_of": args.as_of,
    }
    if args.command == "state" and args.state_command == "current":
        return service.invoke("state.current", **common, limit=args.limit)
    if args.command == "state" and args.state_command == "history":
        return service.invoke("state.history", **common, limit=args.limit)
    if args.command == "state" and args.state_command == "explain":
        return service.invoke(
            "state.explain",
            **common,
            assertion_kind=args.assertion_kind,
            subject=args.subject,
            domain=args.domain,
            scope=args.scope,
            predicate=args.predicate,
        )
    if args.command == "changes" and args.changes_command == "recent":
        return service.invoke(
            "changes.recent", **common, window_start=args.window_start, limit=args.limit
        )
    raise AssertionError("unreachable parser state")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = _invoke(args)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
