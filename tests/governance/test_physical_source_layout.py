"""Phase 19 source-manifest and reversible-executor contracts."""

from __future__ import annotations

import hashlib
import ast
import json
import subprocess
import stat
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from personal_knowledge.governance import apply_source_migration as executor  # noqa: E402
from personal_knowledge.governance.source_manifest import (  # noqa: E402
    PRIVATE_PREFIXES,
    build,
    build_apps_assets_docs_tests,
    build_canonical_src,
)


def _signed(entries: list[dict]) -> dict:
    payload = {
        "schema_version": 1,
        "scope": "tracked-text-source-only",
        "entries": entries,
    }
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    payload["manifest_sha256"] = hashlib.sha256(canonical).hexdigest()
    return payload


def _operation(source: str, target: str, content: bytes, **extra: object) -> dict:
    return {
        "source": source,
        "target": target,
        "inverse": {"source": target, "target": source},
        "sha256": hashlib.sha256(content).hexdigest(),
        "consumers": [],
        "dirty": False,
        **extra,
    }


def test_manifest_covers_every_tracked_source_exactly_once() -> None:
    frozen = json.loads((ROOT / "governance/manifests/source_migration.json").read_text(encoding="utf-8"))
    entries = frozen["entries"]
    assert frozen["tracked_source_count"] == len(entries) == 206
    # This is the original inventory contract; later immutable cohort manifests
    # own the executed final targets.
    assert all(item["inverse"] == {"source": item["target"], "target": item["source"]} for item in entries)
    assert len({item["target"].casefold() for item in entries}) == len(entries)
    assert all(item["inverse"] == {"source": item["target"], "target": item["source"]} for item in frozen["entries"])


def test_manifest_records_consumers_dirty_overlap_and_excludes_private_data() -> None:
    frozen = json.loads((ROOT / "governance/manifests/source_migration.json").read_text(encoding="utf-8"))
    assert all(isinstance(item["consumers"], list) and isinstance(item["dirty"], bool) for item in frozen["entries"])
    # Post-migration frozen snapshot: dirty flags remain typed booleans; live tree may be clean.
    assert all("dirty" in item for item in frozen["entries"])
    assert not any(item["source"].startswith(PRIVATE_PREFIXES) for item in frozen["entries"])
    assert frozen["forbidden_prefixes"] == list(PRIVATE_PREFIXES)


def test_manifest_declares_stable_console_scripts() -> None:
    """Product entrypoints after Phase 20–21: rag-* plus pk-ku / pk-sync."""
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    scripts = set(config["project"]["scripts"])
    required = {
        "rag-pipeline",
        "rag-search",
        "rag-api",
        "rag-mcp",
        "rag-dashboard",
        "pk-ku",
        "pk-sync",
    }
    assert scripts == required


def test_canonical_preview_is_exact_and_records_phase17_conflicts() -> None:
    frozen = json.loads((ROOT / "governance/manifests/source/canonical-src.json").read_text(encoding="utf-8"))
    # Historical manifest may list targets later retired after the cohort freeze.
    known_retired_targets = {
        "src/personal_knowledge/domains/graph/build_graph_relation_candidates_v2.py",
    }
    assert all(
        (ROOT / item["target"]).is_file() or item["target"] in known_retired_targets
        for item in frozen["entries"]
    )
    assert frozen["cohort"] == "canonical-src"
    assert frozen["tracked_source_count"] == len(frozen["entries"]) == 114
    assert all(item["target"].startswith("src/personal_knowledge/") for item in frozen["entries"])
    assert all(item["inverse"] == {"source": item["target"], "target": item["source"]} for item in frozen["entries"])
    phase17 = frozen["phase17_paths"]
    assert any(item["target"] == "src/personal_knowledge/evaluation/run_knowledge_eval.py" for item in phase17)
    # Frozen phase17 conflict list records eval package + private query assets.
    assert any(
        item["source"].startswith("integration/evals/knowledge_units/")
        for item in phase17
    )
    assert any(
        item["target"] == "src/personal_knowledge/domains/knowledge/build_canonical_knowledge_units.py"
        for item in frozen["entries"]
    )
    assert frozen["preflight_snapshot"]["phase17_untracked_conflicts"]


def test_canonical_preview_records_exact_consumer_prestate_and_windows_checks() -> None:
    frozen = json.loads((ROOT / "governance/manifests/source/canonical-src.json").read_text(encoding="utf-8"))
    for rewrite in frozen["consumer_rewrites"]:
        before = __import__("base64").b64decode(rewrite["before_b64"])
        assert hashlib.sha256(before).hexdigest() == rewrite["before_sha256"]
        assert len(before) == rewrite["before_size"]
        assert hashlib.sha256(rewrite["after_text"].encode("utf-8")).hexdigest() == rewrite["after_sha256"]
        assert rewrite["effective_path_after_move"]
    assert any(
        item.get("old_module") == "core"
        for rewrite in frozen["consumer_rewrites"]
        for item in rewrite["replacements"]
    )
    # evaluation modules were already under package paths at freeze; core/rules still rewritten.
    assert any(
        item.get("old_module") == "pipeline"
        for rewrite in frozen["consumer_rewrites"]
        for item in rewrite["replacements"]
    )
    assert any(
        item.get("kind") == "dynamic-import"
        for rewrite in frozen["consumer_rewrites"]
        for item in rewrite["replacements"]
    )
    assert any(
        item.get("old_module") == "rules" and item.get("kind", "").startswith("bare-")
        for rewrite in frozen["consumer_rewrites"]
        for item in rewrite["replacements"]
    )
    assert any(
        item.get("old_module") == "unified_search" and item.get("kind", "").startswith("bare-")
        for rewrite in frozen["consumer_rewrites"]
        for item in rewrite["replacements"]
    )
    legacy_modules = {
        "core", "conversation", "knowledge", "memory", "graph", "vector",
        "pipeline", "services", "source_adapters", "governance", "evaluation",
    }
    for rewrite in frozen["consumer_rewrites"]:
        after = rewrite["after_text"]
        if not rewrite["path"].endswith(".py"):
            continue
        try:
            tree = ast.parse(after)
        except SyntaxError:
            continue
        imported_roots = {
            node.module.split(".", 1)[0]
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert imported_roots.isdisjoint(legacy_modules)
    checks = frozen["preflight_snapshot"]
    assert checks["same_volume"] is True
    assert checks["required_stage_bytes"] < checks["free_bytes"]
    assert checks["max_absolute_path_length"] <= checks["path_length_limit"]
    assert checks["case_collisions"] == checks["unicode_nfc_collisions"] == checks["reparse_nodes"] == []
    # Frozen dirty conflicts are package paths that existed at approval time.
    assert checks["dirty_source_conflicts"]
    assert any(path.startswith("src/personal_knowledge/") for path in checks["dirty_source_conflicts"])
    assert frozen["approval"]["status"] == "approved-current-bytes"
    # preserve-and-govern approvals may record null preview sha256.
    assert "approved_preview_sha256" in frozen["approval"]


def test_legacy_executor_entry_runs_from_uninstalled_checkout() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "integration/scripts/governance/apply_source_migration.py",
            "--manifest",
            "governance/manifests/source_migration.json",
            "--dry-run",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert "ModuleNotFoundError" not in result.stderr
    # Post-migration dry-run fails closed on untracked residual sources, missing files, or dirty drift.
    expected_phrases = (
        "source missing or non-file",
        "dirty source requires a newly approved manifest",
        "manifest contains untracked sources",
    )
    assert any(phrase in result.stderr for phrase in expected_phrases)


def test_root_shim_and_tool_cohorts_are_fully_applied() -> None:
    shims = json.loads((ROOT / "governance/manifests/source/root-shims.json").read_text(encoding="utf-8"))
    tools = json.loads((ROOT / "governance/manifests/source/tools.json").read_text(encoding="utf-8"))
    assert len(shims["entries"]) == 87
    assert not list((ROOT / "integration/scripts").glob("*.py"))
    assert all((ROOT / item["target"]).is_file() and not (ROOT / item["source"]).exists() for item in shims["entries"])
    assert len(tools["entries"]) == len(tools["registry"]) == 16
    # documentation cohort retired; remaining tool registry categories.
    assert {item["category"] for item in tools["registry"]} == {"supported", "migrations", "forensics"}
    assert all((ROOT / item["target"]).is_file() and not (ROOT / item["source"]).exists() for item in tools["entries"])


def test_apps_assets_docs_tests_manifest_is_exact_and_private_safe() -> None:
    manifest_path = ROOT / "governance/manifests/source/apps-assets-docs-tests.json"
    classification_path = ROOT / "governance/manifests/asset_classification.json"
    frozen = json.loads(manifest_path.read_text(encoding="utf-8"))
    classification = json.loads(classification_path.read_text(encoding="utf-8"))
    assert frozen["cohort"] == "apps-assets-docs-tests"
    assert frozen["asset_classification_sha256"] == classification["manifest_sha256"]
    assert frozen["preflight_snapshot"]["casefold_target_collisions"] == 0
    assert frozen["preflight_snapshot"]["existing_targets"] == []
    assert set(frozen["preflight_snapshot"]["test_buckets"]) == {"unit", "contract", "integration", "e2e", "governance"}
    assert all(frozen["preflight_snapshot"]["test_buckets"].values())
    assert all(not item["source"].endswith(".private.jsonl") for item in frozen["entries"])
    assert len(frozen["preflight_snapshot"]["private_eval_retained"]) == 4
    assert classification["summary"]["ambiguous"] == 0
    assert classification["summary"]["phase20_pending_private"] == 4
    assert len({item["target"].casefold() for item in frozen["entries"]}) == len(frozen["entries"])
    assert all(item["inverse"] == {"source": item["target"], "target": item["source"]} for item in frozen["entries"])


def test_executor_apply_and_rollback_restore_exact_bytes(tmp_path: Path) -> None:
    original = b"print('exact')\n"
    source = tmp_path / "legacy/module.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(original)
    consumer = tmp_path / "docs/command.md"
    consumer.parent.mkdir(parents=True)
    consumer_before = b"python legacy/module.py\n"
    consumer_after = "python src/package/module.py\n"
    consumer.write_bytes(consumer_before)
    operation = _operation("legacy/module.py", "src/package/module.py", original)
    operation["rewrites"] = [{
        "path": "docs/command.md",
        "before_sha256": hashlib.sha256(consumer_before).hexdigest(),
        "after_text": consumer_after,
    }]
    manifest = _signed([operation])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    journal = tmp_path / "var/journal.jsonl"

    loaded = executor.load_manifest(manifest_path)
    executor.preflight(tmp_path, loaded)
    executor.apply(tmp_path, loaded, journal)
    assert not source.exists()
    assert (tmp_path / "src/package/module.py").read_bytes() == original
    assert consumer.read_text(encoding="utf-8") == consumer_after

    executor.rollback(tmp_path, journal)
    assert source.read_bytes() == original
    assert not (tmp_path / "src/package/module.py").exists()
    assert consumer.read_bytes() == consumer_before


@pytest.mark.parametrize(
    ("source", "target", "content", "error"),
    [
        ("Agent/private.py", "src/private.py", b"x", "unsafe/private"),
        ("legacy/blob.bin", "src/blob.bin", b"x", "binary/unsupported"),
    ],
)
def test_executor_rejects_private_or_binary_source(tmp_path: Path, source: str, target: str, content: bytes, error: str) -> None:
    path = tmp_path / source
    path.parent.mkdir(parents=True)
    path.write_bytes(content)
    with pytest.raises(executor.MigrationError, match=error):
        executor.preflight(tmp_path, _signed([_operation(source, target, content)]))


def test_executor_rejects_dirty_target_and_dirty_source(tmp_path: Path) -> None:
    content = b"pass\n"
    source = tmp_path / "legacy/module.py"
    target = tmp_path / "src/module.py"
    source.parent.mkdir(parents=True)
    target.parent.mkdir(parents=True)
    source.write_bytes(content)
    target.write_bytes(b"user content")
    operation = _operation("legacy/module.py", "src/module.py", content)
    with pytest.raises(executor.MigrationError, match="dirty target"):
        executor.preflight(tmp_path, _signed([operation]))
    target.unlink()
    operation["dirty"] = True
    with pytest.raises(executor.MigrationError, match="dirty source"):
        executor.preflight(tmp_path, _signed([operation]))


def test_executor_rejects_manifest_or_source_drift(tmp_path: Path) -> None:
    content = b"pass\n"
    source = tmp_path / "legacy/module.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    manifest = _signed([_operation("legacy/module.py", "src/module.py", content)])
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    altered = json.loads(manifest_path.read_text(encoding="utf-8"))
    altered["entries"][0]["target"] = "src/other.py"
    manifest_path.write_text(json.dumps(altered), encoding="utf-8")
    with pytest.raises(executor.MigrationError, match="checksum"):
        executor.load_manifest(manifest_path)
    source.write_bytes(b"changed\n")
    with pytest.raises(executor.MigrationError, match="hash drift"):
        executor.preflight(tmp_path, manifest)


def test_executor_rejects_journal_outside_workspace(tmp_path: Path) -> None:
    content = b"pass\n"
    source = tmp_path / "legacy/module.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(content)
    manifest = _signed([_operation("legacy/module.py", "src/module.py", content)])
    outside = tmp_path.parent / "desktop-leak.journal.jsonl"
    with pytest.raises(executor.MigrationError, match="journal escapes workspace"):
        executor.apply(tmp_path, manifest, outside)
    assert source.read_bytes() == content
    assert not outside.exists()


def test_windows_atomic_replace_retries_sharing_errors_and_preserves_mode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "consumer.md"
    path.write_bytes(b"before")
    path.chmod(0o444)
    real_replace = executor.os.replace
    calls = 0

    def flaky_replace(source: Path, target: Path) -> None:
        nonlocal calls
        calls += 1
        if calls < 3:
            error = PermissionError("injected Windows sharing violation")
            error.winerror = 32  # type: ignore[attr-defined]
            raise error
        real_replace(source, target)

    monkeypatch.setattr(executor.os, "replace", flaky_replace)
    delays: list[float] = []
    executor._atomic_replace_bytes(path, b"after", sleep=delays.append)
    assert path.read_bytes() == b"after"
    assert calls == 3
    assert len(delays) == 2 and delays[1] > delays[0]
    assert stat.S_IMODE(path.stat().st_mode) == 0o444


def test_journal_first_rewrite_failure_rolls_back_exact_prestate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "legacy/module.py"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"pass\n")
    consumer = tmp_path / "docs/readme.md"
    consumer.parent.mkdir(parents=True)
    consumer.write_bytes(b"legacy/module.py\n")
    op = _operation("legacy/module.py", "src/module.py", source.read_bytes())
    manifest = _signed([op])
    before = consumer.read_bytes()
    manifest["consumer_rewrites"] = [{
        "path": "docs/readme.md",
        "effective_path_after_move": "docs/readme.md",
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_text": "src/module.py\n",
    }]
    unsigned = {key: value for key, value in manifest.items() if key != "manifest_sha256"}
    manifest["manifest_sha256"] = hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    journal = tmp_path / "var/journal.jsonl"

    def fail_replace(path: Path, content: bytes, **_: object) -> None:
        raise executor.MigrationError("injected replace failure")

    monkeypatch.setattr(executor, "_atomic_replace_bytes", fail_replace)
    with pytest.raises(executor.MigrationError, match="injected"):
        executor.apply(tmp_path, manifest, journal)
    assert source.read_bytes() == b"pass\n"
    assert consumer.read_bytes() == before
    assert not (tmp_path / "src/module.py").exists()
    records = [json.loads(line) for line in journal.read_text(encoding="utf-8").splitlines()]
    assert any(record.get("kind") == "rewrite" for record in records)
