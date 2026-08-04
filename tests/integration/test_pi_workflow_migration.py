from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.intelligence.analysis.providers import ReplayProvider, ProviderRequest
from personal_knowledge.intelligence.analysis.schema import checksum


def test_replay_parity_is_schema_and_checksum_stable():
    request = ProviderRequest(prompt="same", request_checksum=checksum({"prompt": "same"}), temperature=0, max_output_tokens=10, timeout_seconds=1)
    left = ReplayProvider({"answer": "ok"}).generate(request)
    right = ReplayProvider({"answer": "ok"}).generate(request)
    assert left.response_checksum == right.response_checksum
    assert left.telemetry.provider == right.telemetry.provider == "replay"
    assert left.telemetry.status == right.telemetry.status == "completed"


def test_one_controller_policy_is_explicit():
    policy = (Path(__file__).resolve().parents[2] / "governance/manifests/ai/pi-ai-entrypoints.json").read_text(encoding="utf-8")
    assert '"normal_mode_controller": "pi_kernel"' in policy
    assert '"comparison_harness": "explicit_only"' in policy
