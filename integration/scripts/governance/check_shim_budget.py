"""Resolve the compatibility surface and enforce baseline-only-down."""
from __future__ import annotations

import argparse
import ast
import json
import re
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "tools" / "compat" / "v1_1"
MANIFEST = ROOT / "governance" / "manifests" / "entrypoints.yaml"
TARGET = re.compile(r"Compatibility shim ->\s*([A-Za-z0-9_.]+)")


def discover_shims() -> list[dict[str, object]]:
    result = []
    for path in sorted(SCRIPTS.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        match = TARGET.search(text[:500])
        if not match:
            continue
        tree = ast.parse(text)
        imported = [node.args[0].value for node in ast.walk(tree)
                    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "import_module" and node.args
                    and isinstance(node.args[0], ast.Constant)]
        target = imported[0] if imported else match.group(1)
        target_path = importlib.util.find_spec(target)
        imports_target = bool(imported)
        result.append({"path": path.relative_to(ROOT).as_posix(), "target": target,
                       "target_exists": target_path is not None, "static_parity": imports_target,
                       "consumer": "legacy CLI callers (unknown until telemetry)",
                       "owner": target.split(".", 1)[0], "deprecated": True,
                       "remove_after": "human-approved cohort only"})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    shims = discover_shims()
    tools_manifest = json.loads((ROOT / "governance/manifests/source/tools.json").read_text(encoding="utf-8"))
    tools = tools_manifest["entries"]
    errors = []
    if len(shims) > manifest["shim_registry"]["expected_count"]:
        errors.append(f"shim budget increased: {len(shims)}")
    if len(shims) != manifest["shim_registry"]["expected_count"]:
        errors.append(f"shim baseline drift: expected 86, found {len(shims)}")
    if len(tools) != manifest["tool_registry"]["expected_count"]:
        errors.append(f"tool baseline drift: expected 22, found {len(tools)}")
    errors.extend(f"invalid target/parity: {s['path']}" for s in shims if not s["target_exists"] or not s["static_parity"])
    result = {"ok": not errors, "shim_count": len(shims), "tool_count": len(tools),
              "errors": errors, "resolved_shims": shims,
              "retirement_preview": manifest["retirement_cohorts"] if args.preview else []}
    print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else
          f"shim-budget {'PASS' if result['ok'] else 'FAIL'}: {len(shims)} shims, {len(tools)} tools")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
