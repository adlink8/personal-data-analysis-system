"""Portable runtime configuration and dependency discovery.

Machine-specific values must come from environment variables or executable
discovery.  Importing this module never probes private data or mutates state.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple


def _env_path(name: str) -> Path | None:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser().resolve() if value else None


class VertexConfig(NamedTuple):
    project: str
    location: str
    model: str
    gcloud: str
    sdk_root: Path | None = None


def vertex_config() -> VertexConfig:
    executable = os.environ.get("PERSONAL_DATA_GCLOUD", "").strip() or shutil.which("gcloud")
    # Delay the actionable dependency error until token acquisition so modules
    # remain importable for dry runs, schema checks and unit tests.
    executable = executable or "gcloud"
    return VertexConfig(
        project=os.environ.get("PERSONAL_DATA_GCP_PROJECT", "project-c5cbd608-1b00-454e-80f"),
        location=os.environ.get("PERSONAL_DATA_VERTEX_LOCATION", "us-central1"),
        model=os.environ.get("PERSONAL_DATA_VERTEX_MODEL", "gemini-3.5-flash"),
        gcloud=executable,
        sdk_root=_env_path("CLOUDSDK_ROOT_DIR"),
    )


def gcloud_access_token(config: VertexConfig | None = None) -> str:
    config = config or vertex_config()
    command = [config.gcloud, "auth", "print-access-token"]
    if Path(config.gcloud).suffix.lower() == ".py":
        command.insert(0, sys.executable)
    env = dict(os.environ)
    env["CLOUDSDK_CORE_DISABLE_PROMPTS"] = "1"
    if config.sdk_root:
        env["CLOUDSDK_ROOT_DIR"] = str(config.sdk_root)
    try:
        result = subprocess.run(command, capture_output=True, text=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"Unable to run gcloud ({config.gcloud}): {exc}") from exc
    if result.returncode != 0:
        detail = result.stderr.strip() or "gcloud is not authenticated"
        raise RuntimeError(f"Unable to obtain Vertex AI access token: {detail}")
    return result.stdout.strip()


def _candidate_embedding_paths() -> list[Path]:
    """Return conventional local model locations without binding a drive/user."""
    name = "bge-small-zh-v1.5"
    candidates = [
        Path.home() / "models" / name,
        Path.home() / ".cache" / "modelscope" / "hub" / "models" / "BAAI" / name,
        Path.home() / ".cache" / "huggingface" / "hub" / f"models--BAAI--{name}",
    ]
    if os.name == "nt":
        # Derive available volume roots; no machine-specific drive is encoded.
        for codepoint in range(ord("A"), ord("Z") + 1):
            root = Path(f"{chr(codepoint)}:/")
            if root.exists():
                candidates.append(root / "models" / name)
    return candidates


def embedding_model_path() -> Path:
    configured = _env_path("PERSONAL_DATA_EMBED_MODEL_PATH")
    if configured:
        return configured
    cache = _env_path("SENTENCE_TRANSFORMERS_HOME")
    if cache:
        candidate = cache / "bge-small-zh-v1.5"
        if candidate.exists():
            return candidate
    for candidate in _candidate_embedding_paths():
        if candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError(
        "Local embedding model not configured. Set PERSONAL_DATA_EMBED_MODEL_PATH "
        "to the bge-small-zh-v1.5 directory."
    )


def semantic_api_url() -> str:
    return os.environ.get("PERSONAL_DATA_SEMANTIC_API", "http://127.0.0.1:8000/search/semantic")
