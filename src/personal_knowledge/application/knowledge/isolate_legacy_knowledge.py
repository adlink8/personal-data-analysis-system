"""CLI for planning, applying, and exactly rolling back legacy KU isolation."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from personal_knowledge.application.knowledge.legacy_isolation import (
    IsolationError,
    apply_isolation,
    plan_isolation,
    rollback_isolation,
)
from personal_knowledge.core.project_paths import (
    AGENTSVIEW_DB,
    AGENTSVIEW_NORMALIZED_DB,
    AGENT_CONVERSATIONS_DB,
    ARCHIVE_DIR,
    GOOGLE_DB,
    KNOWLEDGE_ACTIVE_POINTER,
    UNIFIED_DB,
)


def _source_paths() -> dict[str, Path]:
    return {
        "agentsview_live": AGENTSVIEW_DB,
        "agentsview_normalized": AGENTSVIEW_NORMALIZED_DB,
        "canonical_conversations": AGENT_CONVERSATIONS_DB,
        "google": GOOGLE_DB,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="isolate-legacy-knowledge",
        description="Quarantine all legacy derived KU state without deleting source data or old Chroma collections.",
    )
    parser.add_argument("--db", type=Path, default=UNIFIED_DB)
    parser.add_argument("--pointer", type=Path, default=KNOWLEDGE_ACTIVE_POINTER)
    parser.add_argument(
        "--quarantine-root",
        type=Path,
        default=ARCHIVE_DIR / "quarantine" / "knowledge_generations",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    plan = subparsers.add_parser("plan", help="Read-only plan and safety preflight")
    plan.add_argument("--generation-id")
    plan.add_argument("--json", action="store_true")
    apply = subparsers.add_parser("apply", help="Backup, isolate, and activate an empty generation")
    apply.add_argument("--generation-id")
    apply.add_argument("--write", action="store_true")
    apply.add_argument("--i-know", action="store_true")
    apply.add_argument("--json", action="store_true")
    rollback = subparsers.add_parser("rollback", help="Restore one exact verified quarantine manifest")
    rollback.add_argument("--manifest", type=Path, required=True)
    rollback.add_argument("--write", action="store_true")
    rollback.add_argument("--i-know", action="store_true")
    rollback.add_argument("--json", action="store_true")
    return parser


def _emit(result: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        for key, value in result.items():
            print(f"{key}: {value}")


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "plan":
            result = plan_isolation(
                db_path=args.db,
                pointer_path=args.pointer,
                quarantine_root=args.quarantine_root,
                source_paths=_source_paths(),
                generation_id=args.generation_id,
            )
        elif args.command == "apply":
            if not args.write or not args.i_know:
                raise IsolationError("apply requires both --write and --i-know")
            result = apply_isolation(
                db_path=args.db,
                pointer_path=args.pointer,
                quarantine_root=args.quarantine_root,
                source_paths=_source_paths(),
                generation_id=args.generation_id,
            )
        else:
            if not args.write or not args.i_know:
                raise IsolationError("rollback requires both --write and --i-know")
            result = rollback_isolation(
                manifest_path=args.manifest,
                db_path=args.db,
                pointer_path=args.pointer,
            )
        _emit(result, args.json)
        return 0
    except IsolationError as exc:
        error = {"ok": False, "error": str(exc), "paid_calls": 0}
        if getattr(args, "json", False):
            print(json.dumps(error, ensure_ascii=False, indent=2))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

