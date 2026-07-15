from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "integration" / "scripts" / "governance" / "check_path_policy.py"
RUNTIME = ROOT / "src" / "personal_knowledge" / "core" / "runtime_config.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def test_all_machine_paths_are_classified_and_production_is_clean() -> None:
    checker = _load(CHECKER, "governance_path_checker")
    hits = checker.scan()
    assert hits
    assert all(hit["category"] for hit in hits)
    assert [h for h in hits if h["category"] == "production_source"] == []


def test_path_baseline_is_a_machine_readable_contract() -> None:
    data = json.loads((ROOT / "governance" / "baselines" / "path_hits.yaml").read_text(encoding="utf-8"))
    assert data["categories"]["production_source"]["allowed"] == 0
    assert all(value.get("policy_id") for key, value in data["categories"].items() if key != "production_source")


def test_runtime_config_honors_environment_without_machine_defaults(monkeypatch) -> None:
    runtime = _load(RUNTIME, "portable_runtime_config")
    monkeypatch.setenv("PERSONAL_DATA_EMBED_MODEL_PATH", str(ROOT / "model-fixture"))
    monkeypatch.setenv("PERSONAL_DATA_GCLOUD", "portable-gcloud")
    monkeypatch.setenv("PERSONAL_DATA_GCP_PROJECT", "test-project")
    assert runtime.embedding_model_path() == (ROOT / "model-fixture").resolve()
    assert runtime.vertex_config().gcloud == "portable-gcloud"
    assert runtime.vertex_config().project == "test-project"


def test_runtime_config_missing_embedding_has_actionable_error(monkeypatch) -> None:
    runtime = _load(RUNTIME, "portable_runtime_config_missing")
    monkeypatch.delenv("PERSONAL_DATA_EMBED_MODEL_PATH", raising=False)
    monkeypatch.delenv("SENTENCE_TRANSFORMERS_HOME", raising=False)
    monkeypatch.setattr(runtime, "_candidate_embedding_paths", lambda: [])
    try:
        runtime.embedding_model_path()
    except RuntimeError as exc:
        assert "PERSONAL_DATA_EMBED_MODEL_PATH" in str(exc)
    else:
        raise AssertionError("missing model configuration must fail closed")
