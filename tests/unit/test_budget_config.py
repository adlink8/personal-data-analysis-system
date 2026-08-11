from __future__ import annotations

import json

from personal_knowledge.core.runtime_config import (
    DEFAULT_BUDGET_CONFIG_PATH,
    analysis_max_attempts,
    analysis_max_output_tokens,
    analysis_temperature_max,
    provider_max_output_tokens,
    provider_max_temperature,
    provider_timeout_seconds,
)


def test_budget_defaults_stay_current_when_unconfigured() -> None:
    assert provider_max_temperature() == 0.3
    assert provider_max_output_tokens() == 4096
    assert provider_timeout_seconds() == 120
    assert analysis_max_attempts() == 2
    assert analysis_temperature_max() == 0.3
    assert analysis_max_output_tokens() == 4096


def test_budget_config_file_defaults_match_builtin_defaults() -> None:
    value = json.loads(DEFAULT_BUDGET_CONFIG_PATH.read_text(encoding="utf-8"))
    assert value["schema"] == "pi-budget-config-v1"
    assert value["provider"]["max_temperature"] == 0.3
    assert value["provider"]["max_output_tokens"] == 4096
    assert value["provider"]["timeout_seconds"] == 120
    assert value["analysis"]["max_attempts"] == 2
    assert value["analysis"]["temperature_max"] == 0.3
    assert value["analysis"]["max_output_tokens"] == 4096


def test_budget_env_var_overrides_everything(monkeypatch) -> None:
    monkeypatch.setenv("PI_PROVIDER_MAX_TEMPERATURE", "0.6")
    monkeypatch.setenv("PI_PROVIDER_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("PI_PROVIDER_TIMEOUT_SECONDS", "300")
    monkeypatch.setenv("PI_ANALYSIS_MAX_ATTEMPTS", "3")
    assert provider_max_temperature() == 0.6
    assert provider_max_output_tokens() == 8192
    assert provider_timeout_seconds() == 300
    assert analysis_max_attempts() == 3


def test_budget_config_file_is_fallback_when_env_unset(tmp_path, monkeypatch) -> None:
    budget = {
        "schema": "pi-budget-config-v1",
        "provider": {"max_temperature": 0.7, "max_output_tokens": 512, "timeout_seconds": 240},
        "analysis": {"max_attempts": 3, "temperature_max": 0.4, "max_output_tokens": 2048},
    }
    path = tmp_path / "pi-budget.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    monkeypatch.setenv("PI_BUDGET_CONFIG", str(path))
    assert provider_max_temperature() == 0.7
    assert provider_max_output_tokens() == 512
    assert provider_timeout_seconds() == 240
    assert analysis_max_attempts() == 3
    assert analysis_temperature_max() == 0.4
    assert analysis_max_output_tokens() == 2048


def test_budget_env_beats_config_file(tmp_path, monkeypatch) -> None:
    budget = {"schema": "pi-budget-config-v1", "provider": {"max_temperature": 0.7}}
    path = tmp_path / "pi-budget.json"
    path.write_text(json.dumps(budget), encoding="utf-8")
    monkeypatch.setenv("PI_BUDGET_CONFIG", str(path))
    monkeypatch.setenv("PI_PROVIDER_MAX_TEMPERATURE", "0.5")
    assert provider_max_temperature() == 0.5


def test_budget_config_fail_safe_on_missing_or_malformed_file(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "missing.json"
    monkeypatch.setenv("PI_BUDGET_CONFIG", str(missing))
    assert provider_max_temperature() == 0.3
    assert provider_max_output_tokens() == 4096
    assert analysis_max_attempts() == 2

    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    monkeypatch.setenv("PI_BUDGET_CONFIG", str(malformed))
    assert provider_max_temperature() == 0.3
    assert analysis_max_attempts() == 2

    wrong_shape = tmp_path / "wrong-shape.json"
    wrong_shape.write_text("[1, 2]", encoding="utf-8")
    monkeypatch.setenv("PI_BUDGET_CONFIG", str(wrong_shape))
    assert provider_max_temperature() == 0.3


def test_budget_env_rejects_invalid_values_and_falls_back(monkeypatch) -> None:
    monkeypatch.setenv("PI_PROVIDER_MAX_TEMPERATURE", "not-a-number")
    monkeypatch.setenv("PI_ANALYSIS_MAX_ATTEMPTS", "-1")
    assert provider_max_temperature() == 0.3
    assert analysis_max_attempts() == 2
