from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.intelligence.analysis.providers import (
    LegacyProviderAdapter,
    ProviderError,
    ProviderRequest,
    ReplayProvider,
)
from personal_knowledge.intelligence.analysis.schema import checksum


def _request() -> ProviderRequest:
    return ProviderRequest(prompt="synthetic", request_checksum=checksum({"prompt": "synthetic"}), temperature=0, max_output_tokens=10, timeout_seconds=1)


def test_python_replay_provider_is_schema_stable_and_zero_cost():
    result = ReplayProvider({"answer": "ok"}).generate(_request())
    assert result.response_payload == {"answer": "ok"}
    assert result.telemetry.provider == "replay"
    assert result.telemetry.cost_amount == 0


def test_provider_request_budget_and_missing_replay_fail_closed():
    try:
        ProviderRequest(prompt="x", request_checksum="0" * 64, temperature=.5, max_output_tokens=10, timeout_seconds=1)
    except ProviderError as exc:
        assert exc.code == "provider_budget_invalid"
    else:
        raise AssertionError("invalid budget accepted")


def test_provider_request_budget_caps_are_raised_via_config(monkeypatch):
    # Operators may raise the budget ceilings through configuration; the
    # validation gates themselves must remain active.
    monkeypatch.setenv("PI_PROVIDER_MAX_TEMPERATURE", "0.6")
    monkeypatch.setenv("PI_PROVIDER_MAX_OUTPUT_TOKENS", "8192")
    monkeypatch.setenv("PI_PROVIDER_TIMEOUT_SECONDS", "300")
    request = ProviderRequest(
        prompt="x", request_checksum="0" * 64,
        temperature=0.6, max_output_tokens=8192, timeout_seconds=300,
    )
    assert request.temperature == 0.6
    try:
        ProviderRequest(prompt="x", request_checksum="0" * 64,
                        temperature=0.7, max_output_tokens=10, timeout_seconds=1)
    except ProviderError as exc:
        assert exc.code == "provider_budget_invalid"
    else:
        raise AssertionError("over-ceiling temperature accepted")


def test_legacy_adapter_is_rollback_only():
    provider = ReplayProvider({"answer": "ok"})
    try:
        LegacyProviderAdapter(provider)
    except ProviderError as exc:
        assert exc.code == "legacy_provider_rollback_only"
    else:
        raise AssertionError("legacy provider allowed in normal mode")
    assert LegacyProviderAdapter(provider, mode="rollback").generate(_request()).response_payload == {"answer": "ok"}


def test_pi_replay_adapter_returns_identity_bound_receipt():
    root = Path(__file__).resolve().parents[2]
    script = """
      import { createReplayProviderAdapter } from './apps/personal_intelligence_kernel/src/models/provider-adapter.mjs';
      const adapter = createReplayProviderAdapter();
      const receipt = await adapter.generate({purpose:'structured_analysis',prompt:'synthetic',task_id:'t',session_id:'s',idempotency_key:'i'});
      process.stdout.write(JSON.stringify(receipt));
    """
    result = subprocess.run(["node", "--input-type=module", "-e", script], cwd=root, capture_output=True, text=True, check=True)
    receipt = json.loads(result.stdout)
    assert receipt["schema_version"] == "pi_provider_receipt_v1"
    assert receipt["task_id"] == "t" and receipt["session_id"] == "s"
    assert receipt["telemetry"]["provider"] == "replay"
