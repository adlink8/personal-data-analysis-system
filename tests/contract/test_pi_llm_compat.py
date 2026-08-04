from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.core.llm import _PiCompletionClient
from personal_knowledge.intelligence.analysis.providers import ProviderResult, ProviderTelemetry
from personal_knowledge.intelligence.analysis.schema import checksum


def test_openai_compat_facade_uses_pi_provider_receipt():
    client = _PiCompletionClient(purpose="generic_generation")
    client._provider.generate = lambda request: ProviderResult(
        response_payload={"text": "ok"},
        response_checksum=checksum({"text": "ok"}),
        telemetry=ProviderTelemetry(
            provider="replay", model="replay-v1", input_tokens=1,
            output_tokens=1, cost_amount=0, cost_currency="CNY",
            latency_ms=0, status="completed",
        ),
    )
    response = client.chat.completions.create(
        model="ignored-by-pi-route",
        messages=[{"role": "user", "content": "say ok"}],
        temperature=0,
        max_tokens=10,
    )
    assert response.choices[0].message.content == "ok"
    assert response.usage.prompt_tokens == 1
