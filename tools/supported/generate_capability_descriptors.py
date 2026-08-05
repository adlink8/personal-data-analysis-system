"""Generate deterministic REST/MCP/Pi capability descriptors."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from personal_knowledge.services.capability_registry import DEFAULT_REGISTRY_PATH, descriptor_snapshot, load_registry

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "governance" / "manifests" / "capabilities" / "generated"


def render(registry: dict, profile: str) -> dict:
    base = descriptor_snapshot(registry, profile)
    return {"schema": "project-capability-descriptor-bundle-v1", "profile": profile, "registry_checksum": base["registry_checksum"], "rest": base, "mcp": base, "pi": base}


def generate(registry_path: Path = DEFAULT_REGISTRY_PATH, output_dir: Path = DEFAULT_OUTPUT) -> list[Path]:
    registry = load_registry(registry_path)
    output_dir.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for profile in ("production", "operator", "test"):
        path = output_dir / f"project-capability-descriptors.{profile}.json"
        path.write_text(json.dumps(render(registry, profile), ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        paths.append(path)
    return paths


def check(registry_path: Path = DEFAULT_REGISTRY_PATH, output_dir: Path = DEFAULT_OUTPUT) -> bool:
    registry = load_registry(registry_path)
    expected = {path.name: json.dumps(render(registry, profile), ensure_ascii=False, sort_keys=True, indent=2) + "\n" for profile, path in (("production", output_dir / "project-capability-descriptors.production.json"), ("operator", output_dir / "project-capability-descriptors.operator.json"), ("test", output_dir / "project-capability-descriptors.test.json"))}
    return all(path.exists() and path.read_text(encoding="utf-8") == content for name, content in expected.items() for path in [output_dir / name])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY_PATH)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if args.write:
        paths = generate(args.registry, args.output_dir)
        print(json.dumps({"ok": True, "written": [str(path) for path in paths]}, ensure_ascii=False))
        return 0
    if args.check:
        ok = check(args.registry, args.output_dir)
        print(json.dumps({"ok": ok, "output_dir": str(args.output_dir)}, ensure_ascii=False))
        return 0 if ok else 1
    parser.error("choose --write or --check")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
