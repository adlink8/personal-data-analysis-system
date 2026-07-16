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
import sys


def _cmd_conversations(write: bool) -> int:
    from personal_knowledge.application.run_pipeline import run_agentsview_stage

    ok = run_agentsview_stage(write=write)
    if not ok:
        return 1
    mode = "write" if write else "dry-run"
    print(f"\n[done] pk-sync conversations ({mode}) finished.")
    print("  SSOT: data/canonical/agent/structured/db/agent_conversations.sqlite")
    print("  Next (optional): knowledge unit refresh / promote — not part of this command.")
    return 0


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

    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
