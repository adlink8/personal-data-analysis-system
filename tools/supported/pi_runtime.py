from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_runtime_activation import RuntimeActivation, ActivationError

def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("command", choices=["inspect", "prepare", "confirm", "downgrade"], default="inspect", nargs="?"); parser.add_argument("--database", default="var/db/pi_runtime_activation.sqlite"); parser.add_argument("--target", default="legacy"); parser.add_argument("--evidence-checksum", default=""); parser.add_argument("--readiness-evidence", default=""); parser.add_argument("--preview", default=""); parser.add_argument("--phrase", default=""); parser.add_argument("--idempotency-key", default=""); args = parser.parse_args()
    runtime = RuntimeActivation(args.database)
    try:
        if args.command == "inspect": result = runtime.current()
        elif args.command == "prepare": result = runtime.prepare(args.target, evidence_checksum=args.evidence_checksum, readiness=bool(args.readiness_evidence), readiness_evidence_path=args.readiness_evidence or None)
        elif args.command == "downgrade": result = runtime.downgrade("manual_stop")
        else: result = runtime.confirm(json.loads(args.preview), confirmation_phrase=args.phrase, idempotency_key=args.idempotency_key)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True)); return 0
    except (ActivationError, ValueError) as exc: print(json.dumps({"ok":False,"error":str(exc)})); return 2
    finally: runtime.close()

if __name__ == "__main__": raise SystemExit(main())
