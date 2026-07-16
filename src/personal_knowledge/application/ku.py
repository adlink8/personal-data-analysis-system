"""Product KU CLI (post Phase 14–21).

Stable operator surface for incremental knowledge units. Prefer this entry over
calling long module paths or editing code to change extract policy.

Usage::

    pk-ku inspect
    pk-ku prepare --model gemini-3.5-flash --provider vertex_google \\
        --endpoint https://aiplatform.googleapis.com --auth-mode gcloud
    pk-ku extract --run <fresh_run_id> --model gemini-3.5-flash --max-items 50
    pk-ku status --run <run_id>
    pk-ku canonical --run <run_id> --write
    pk-ku publish --run <run_id> --write          # staging → current (additive)
    pk-ku vector [--write]                        # candidate Chroma index
    pk-ku extract-gate --run <run_id>
    pk-ku canary --candidate-override <collection> --report path.json
    pk-ku canary --report path.json --strict
    pk-ku promote --list
    pk-ku promote --collection <name> --require-eval-pass --eval-summary … --eval-gate …
    pk-ku watermark                 # show committed vs current source checksum
    pk-ku watermark --advance --from-canonical --write   # after successful promote

Hard rule: daily path is inspect → prepare → extract(resume delta run).
Full inventory + prod --start is NOT exposed here (planned backfill only via
underlying modules with explicit human intent).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _default_artifact() -> Path:
    return Path("var/reports/analysis/ai_context/knowledge_incremental_delta.json")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pk-ku",
        description=(
            "Knowledge Unit product CLI (incremental only). "
            "Policy knobs live on subcommands — do not change code for daily ops."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Daily order:\n"
            "  1) pk-sync conversations [--write]\n"
            "  2) pk-ku inspect\n"
            "  3) pk-ku prepare --model … --provider … --endpoint … --auth-mode …\n"
            "  4) pk-ku extract --run ir_* --max-items N\n"
            "  5) pk-ku extract-gate / canonical / publish / vector\n"
            "  6) pk-ku canary --candidate-override … --report …\n"
            "  7) pk-ku promote --collection … --require-eval-pass …\n"
            "  8) pk-ku watermark --advance --from-canonical --write\n"
            "\n"
            "Full inventory backfill is intentionally NOT a pk-ku subcommand.\n"
            "See docs/runbooks/ku-incremental.md"
        ),
    )
    sub = p.add_subparsers(dest="command", required=True)

    # --- inspect ---
    ins = sub.add_parser("inspect", help="Free delta report (no LLM, no writes)")
    ins.add_argument("--db", type=Path, default=None)
    ins.add_argument("--canonical-db", type=Path, default=None)
    ins.add_argument("--source-checksum", default="", help="Optional last source checksum")

    # --- prepare ---
    prep = sub.add_parser(
        "prepare",
        help="Freeze delta inventory + extract queue (no LLM). Policy via flags.",
    )
    prep.add_argument("--model", required=True, help="Model ID (required, fail-closed)")
    prep.add_argument("--provider", default="", help="vertex_google / openai / …")
    prep.add_argument("--endpoint", default="", help="LLM endpoint URL")
    prep.add_argument("--auth-mode", default="", help="gcloud / api_key")
    prep.add_argument(
        "--artifact",
        type=Path,
        default=None,
        help=f"JSON artifact path (default {_default_artifact()})",
    )
    prep.add_argument("--db", type=Path, default=None)
    prep.add_argument("--canonical-db", type=Path, default=None)
    prep.add_argument(
        "--extract-new-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Queue only change_type=new (default true)",
    )
    prep.add_argument(
        "--extract-since-watermark",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Floor session date at watermark day (default true)",
    )
    prep.add_argument(
        "--since",
        default="",
        metavar="YYYY-MM-DD",
        help="Explicit session floor; overrides watermark floor",
    )
    prep.add_argument(
        "--skip-succeeded",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Drop refs already succeeded (default true)",
    )
    prep.add_argument(
        "--roles",
        default="",
        help="Comma roles e.g. user or user,assistant (default all eligible)",
    )
    prep.add_argument(
        "--baseline-inventory",
        default="",
        metavar="ID",
        help="Force before inventory_id",
    )
    prep.add_argument(
        "--max-extract-items",
        type=int,
        default=None,
        metavar="N",
        help="Cap seeded queue after filters (newest first)",
    )

    # --- extract (paid) ---
    ext = sub.add_parser(
        "extract",
        help="Paid LLM extract: resume an incremental run from prepare (not full inventory)",
    )
    ext.add_argument("--run", required=True, metavar="RUN_ID", help="fresh_run_id from prepare")
    ext.add_argument("--model", default="gemini-3.5-flash")
    ext.add_argument("--max-items", type=int, default=None, help="Process at most N items this call")
    ext.add_argument("--workers", type=int, default=None)
    ext.add_argument("--min-request-interval", type=float, default=None)
    ext.add_argument("--batch-size", type=int, default=50)
    ext.add_argument("--db", type=Path, default=None)

    # --- status ---
    st = sub.add_parser("status", help="Show item ledger stats for a run")
    st.add_argument("--run", required=True, metavar="RUN_ID")
    st.add_argument("--db", type=Path, default=None)

    # --- canonical ---
    can = sub.add_parser("canonical", help="Build canonical units from an extraction run")
    can.add_argument("--run", required=True, metavar="RUN_ID")
    can.add_argument("--write", action="store_true", help="Persist (default dry-run)")
    can.add_argument("--db", type=Path, default=None)

    # --- publish (additive staging → current) ---
    pub = sub.add_parser(
        "publish",
        help="Promote this incremental run's staging units/canonical → current (no demote)",
    )
    pub.add_argument("--run", required=True, metavar="RUN_ID")
    pub.add_argument("--write", action="store_true")
    pub.add_argument("--db", type=Path, default=None)

    # --- vector candidate ---
    vec = sub.add_parser("vector", help="Build candidate KU vector store (does not touch active)")
    vec.add_argument("--write", action="store_true")
    vec.add_argument("--db", type=Path, default=None)

    # --- extraction gate ---
    eg = sub.add_parser("extract-gate", help="Strict extraction gate for a run (writes gate row)")
    eg.add_argument("--run", required=True, metavar="RUN_ID")
    eg.add_argument("--min-yield", type=float, default=None)
    eg.add_argument("--db", type=Path, default=None)

    # --- canary ---
    canary = sub.add_parser(
        "canary",
        help="Run / check / strict-gate knowledge canary (does not touch active by default)",
    )
    canary.add_argument(
        "--candidate-override",
        default="",
        help="Candidate collection name (preferred; leaves active unchanged)",
    )
    canary.add_argument("--queries", type=int, default=30, help="Query count (default 30)")
    canary.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Report JSON path (required for --strict / --check-label-completeness)",
    )
    canary.add_argument(
        "--check-label-completeness",
        action="store_true",
        help="Only check labels on an existing report",
    )
    canary.add_argument(
        "--strict",
        action="store_true",
        help="Compute PASS/FAIL gate (requires fully labeled report)",
    )

    # --- promote ---
    prom = sub.add_parser("promote", help="List or promote candidate index (active last)")
    prom.add_argument("--list", action="store_true", help="List index versions")
    prom.add_argument("--collection", default="", help="Candidate collection to promote")
    prom.add_argument("--require-eval-pass", action="store_true")
    prom.add_argument("--eval-summary", type=Path, default=None)
    prom.add_argument("--eval-gate", type=Path, default=None)

    # --- watermark ---
    wm = sub.add_parser(
        "watermark",
        help="Show or advance knowledge_source_watermark (after successful promote)",
    )
    wm.add_argument(
        "--advance",
        action="store_true",
        help="Advance committed watermark (requires --write + checksum source)",
    )
    wm.add_argument(
        "--from-canonical",
        action="store_true",
        help="Use compute_source_checksum(canonical_db) as new watermark",
    )
    wm.add_argument(
        "--checksum",
        default="",
        help="Explicit checksum to commit (alternative to --from-canonical)",
    )
    wm.add_argument(
        "--write",
        action="store_true",
        help="Persist advance (default dry-run / show only)",
    )
    wm.add_argument("--db", type=Path, default=None)
    wm.add_argument("--canonical-db", type=Path, default=None)

    # --- workflow help ---
    sub.add_parser("workflow", help="Print canonical daily KU workflow + forbidden paths")

    return p


def _cmd_workflow() -> int:
    print(
        """pk-ku daily workflow (incremental only)
=====================================
1. pk-sync conversations [--write]     # dialogue SSOT if chats grew
2. pk-ku inspect                       # free; record new_refs / source_changed
3. pk-ku prepare --model … --provider … --endpoint … --auth-mode …
     Policy flags (no code edits):
       --extract-new-only / --no-extract-new-only
       --extract-since-watermark / --no-extract-since-watermark
       --since YYYY-MM-DD
       --roles user[,assistant]
       --skip-succeeded / --no-skip-succeeded
       --baseline-inventory ID
       --max-extract-items N
     Read extract_item_count + fresh_run_id from JSON. If inspect has delta but
     prepare no_op → STOP (prepare defect). Do NOT invent full inventory path.
4. pk-ku extract --run <fresh_run_id> --max-items N --workers 4
5. pk-ku extract-gate --run <run_id> [--min-yield 0.7]
6. pk-ku canonical --run <run_id> --write
7. pk-ku publish --run <run_id> --write   # additive staging→current (not full demote)
8. pk-ku vector --write                   # candidate index only
9. pk-ku canary --candidate-override <coll> --report path.json
   # after human labels:
   pk-ku canary --report path.json --check-label-completeness
   pk-ku canary --report path.json --strict
10. pk-ku promote --collection <cand> --require-eval-pass --eval-summary … --eval-gate …
11. pk-ku watermark --advance --from-canonical --write   # only after promote OK

Forbidden as daily ops:
  - build_knowledge_inventory --write + prod --start on full inventory
  - resume mistaken full-inventory run until pending=0
  - promote mid-run / without eval when gate required
  - advance watermark before promote
  - rag-pipeline for knowledge

Docs: docs/runbooks/ku-incremental.md
"""
    )
    return 0


def _cmd_inspect(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.refresh_knowledge_units import main as refresh_main

    argv: list[str] = ["--inspect"]
    if args.source_checksum:
        argv.extend(["--source-checksum", args.source_checksum])
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    if args.canonical_db is not None:
        argv.extend(["--canonical-db", str(args.canonical_db)])
    return int(refresh_main(argv) or 0)


def _cmd_prepare(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.refresh_knowledge_units import main as refresh_main

    artifact = args.artifact or _default_artifact()
    argv: list[str] = [
        "--prepare",
        "--model",
        args.model,
        "--provider",
        args.provider,
        "--endpoint",
        args.endpoint,
        "--auth-mode",
        args.auth_mode,
        "--artifact",
        str(artifact),
    ]
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    if args.canonical_db is not None:
        argv.extend(["--canonical-db", str(args.canonical_db)])
    if args.extract_new_only:
        argv.append("--extract-new-only")
    else:
        argv.append("--no-extract-new-only")
    if args.extract_since_watermark:
        argv.append("--extract-since-watermark")
    else:
        argv.append("--no-extract-since-watermark")
    if args.since:
        argv.extend(["--since", args.since])
    if args.skip_succeeded:
        argv.append("--skip-succeeded")
    else:
        argv.append("--no-skip-succeeded")
    if args.roles:
        argv.extend(["--roles", args.roles])
    if args.baseline_inventory:
        argv.extend(["--baseline-inventory", args.baseline_inventory])
    if args.max_extract_items is not None:
        argv.extend(["--max-extract-items", str(args.max_extract_items)])
    return int(refresh_main(argv) or 0)


def _cmd_extract(args: argparse.Namespace) -> int:
    import os

    # Guard before heavy imports: incremental prepare mints ir_* run ids.
    run_id = (args.run or "").strip()
    if not run_id:
        print("[error] --run is required", file=sys.stderr)
        return 2
    allow_non_inc = os.environ.get("PK_KU_ALLOW_NON_INCREMENTAL_RUN", "").strip() in {
        "1",
        "true",
        "TRUE",
        "yes",
        "YES",
    }
    if not run_id.startswith("ir_") and not allow_non_inc:
        print(
            f"[warn] run_id={run_id!r} does not look like an incremental prepare id (ir_*).\n"
            "  Daily extract should use fresh_run_id from `pk-ku prepare`.\n"
            "  To force (forensics): set PK_KU_ALLOW_NON_INCREMENTAL_RUN=1",
            file=sys.stderr,
        )
        return 2

    from personal_knowledge.application.knowledge.build_knowledge_units_prod import (
        DEFAULT_MIN_REQUEST_INTERVAL,
        DEFAULT_WORKERS,
        main as prod_main,
    )

    argv: list[str] = ["--resume", run_id, "--model", args.model]
    if args.max_items is not None:
        argv.extend(["--max-items", str(args.max_items)])
    workers = args.workers if args.workers is not None else DEFAULT_WORKERS
    argv.extend(["--workers", str(workers)])
    interval = (
        args.min_request_interval
        if args.min_request_interval is not None
        else DEFAULT_MIN_REQUEST_INTERVAL
    )
    argv.extend(["--min-request-interval", str(interval)])
    argv.extend(["--batch-size", str(args.batch_size)])
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(prod_main(argv) or 0)


def _cmd_status(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.build_knowledge_units_prod import main as prod_main

    argv: list[str] = ["--status", args.run]
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(prod_main(argv) or 0)


def _cmd_canonical(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.build_canonical_knowledge_units import (
        main as canonical_main,
    )

    argv: list[str] = ["--run", args.run]
    if args.write:
        argv.append("--write")
    else:
        argv.append("--dry-run")
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(canonical_main(argv) or 0)


def _cmd_publish(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.publish_incremental_run import main as pub_main

    argv: list[str] = ["--run", args.run]
    if args.write:
        argv.append("--write")
    else:
        argv.append("--dry-run")
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(pub_main(argv) or 0)


def _cmd_vector(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.build_knowledge_unit_vector_store import (
        main as vector_main,
    )

    argv: list[str] = []
    if args.write:
        argv.append("--write")
    else:
        argv.append("--dry-run")
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(vector_main(argv) or 0)


def _cmd_extract_gate(args: argparse.Namespace) -> int:
    from personal_knowledge.evaluation.knowledge.evaluate_knowledge_unit_extraction import (
        main as gate_main,
    )

    argv: list[str] = ["--run", args.run]
    if args.min_yield is not None:
        argv.extend(["--min-yield", str(args.min_yield)])
    if args.db is not None:
        argv.extend(["--db", str(args.db)])
    return int(gate_main(argv) or 0)


def _cmd_canary(args: argparse.Namespace) -> int:
    from personal_knowledge.evaluation.knowledge.evaluate_knowledge_canary import (
        main as canary_main,
    )

    argv: list[str] = []
    if args.candidate_override:
        argv.extend(["--candidate-override", args.candidate_override])
    if args.queries is not None:
        argv.extend(["--queries", str(args.queries)])
    if args.report is not None:
        argv.extend(["--report", str(args.report)])
    if args.check_label_completeness:
        argv.append("--check-label-completeness")
    if args.strict:
        argv.append("--strict")
    return int(canary_main(argv) or 0)


def _cmd_promote(args: argparse.Namespace) -> int:
    from personal_knowledge.application.knowledge.promote_knowledge_index import (
        promote_main,
    )

    argv: list[str] = []
    if args.list:
        argv.append("--list")
    if args.collection:
        argv.extend(["--promote", args.collection])
    if args.require_eval_pass:
        argv.append("--require-eval-pass")
    if args.eval_summary is not None:
        argv.extend(["--eval-summary", str(args.eval_summary)])
    if args.eval_gate is not None:
        argv.extend(["--eval-gate", str(args.eval_gate)])
    if not argv:
        print(
            "usage: pk-ku promote --list | --collection NAME [--require-eval-pass …]",
            file=sys.stderr,
        )
        return 2
    return int(promote_main(argv) or 0)


def _cmd_watermark(args: argparse.Namespace) -> int:
    """Show or advance source watermark. Advance is opt-in and fail-closed."""
    import json
    import sqlite3

    from personal_knowledge.application.knowledge.refresh_knowledge_units import (
        advance_watermark,
        compute_source_checksum,
        get_committed_watermark,
    )
    from personal_knowledge.core.project_paths import (
        AGENT_CONVERSATIONS_DB,
        UNIFIED_DB,
    )

    db_path = args.db or UNIFIED_DB
    canonical_db = args.canonical_db or AGENT_CONVERSATIONS_DB
    committed = get_committed_watermark(db_path)
    current = compute_source_checksum(canonical_db) if canonical_db.exists() else ""
    wm_updated = ""
    try:
        con = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True)
        row = con.execute(
            "SELECT updated_at FROM knowledge_source_watermark WHERE key='committed'"
        ).fetchone()
        wm_updated = row[0] if row else ""
        con.close()
    except sqlite3.Error:
        pass

    if not args.advance:
        doc = {
            "committed": committed,
            "committed_updated_at": wm_updated,
            "current_source_checksum": current,
            "source_matches_watermark": bool(committed and current and committed == current),
            "write": False,
        }
        print(json.dumps(doc, ensure_ascii=False, indent=2))
        return 0

    # advance path
    if args.from_canonical and args.checksum:
        print("[error] use only one of --from-canonical or --checksum", file=sys.stderr)
        return 2
    if args.from_canonical:
        new_cs = current
        if not new_cs:
            print("[error] cannot compute source checksum (canonical missing?)", file=sys.stderr)
            return 2
    elif args.checksum:
        new_cs = args.checksum.strip()
    else:
        print(
            "[error] --advance requires --from-canonical or --checksum",
            file=sys.stderr,
        )
        return 2

    preview = {
        "action": "advance",
        "before": committed,
        "after": new_cs,
        "changed": committed != new_cs,
        "write": bool(args.write),
    }
    if not args.write:
        preview["note"] = "dry-run only; pass --write to persist"
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    result = advance_watermark(db_path, new_cs)
    print(json.dumps({**preview, **result, "write": True}, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "workflow":
        return _cmd_workflow()
    if args.command == "inspect":
        return _cmd_inspect(args)
    if args.command == "prepare":
        return _cmd_prepare(args)
    if args.command == "extract":
        return _cmd_extract(args)
    if args.command == "status":
        return _cmd_status(args)
    if args.command == "canonical":
        return _cmd_canonical(args)
    if args.command == "publish":
        return _cmd_publish(args)
    if args.command == "vector":
        return _cmd_vector(args)
    if args.command == "extract-gate":
        return _cmd_extract_gate(args)
    if args.command == "canary":
        return _cmd_canary(args)
    if args.command == "promote":
        return _cmd_promote(args)
    if args.command == "watermark":
        return _cmd_watermark(args)

    print(f"unknown command: {args.command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
