"""Dependency-injected provider boundaries; no provider is live by default."""
from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any, Callable, Mapping, Protocol

from .schema import checksum


class ProviderError(RuntimeError):
    def __init__(self, code: str, detail: str = "", *, retryable: bool = False) -> None:
        self.code = code
        self.detail = detail
        self.retryable = retryable
        super().__init__(f"{code}: {detail}" if detail else code)


class ProviderTimeout(ProviderError):
    def __init__(self, detail: str = "") -> None:
        super().__init__("provider_timeout", detail, retryable=True)


@dataclass(frozen=True)
class ProviderRequest:
    prompt: str
    request_checksum: str
    temperature: float
    max_output_tokens: int
    timeout_seconds: float

    def __post_init__(self) -> None:
        if not self.prompt or len(self.request_checksum) != 64:
            raise ProviderError("provider_request_invalid")
        if not 0 <= self.temperature <= .3 or not 1 <= self.max_output_tokens <= 4096:
            raise ProviderError("provider_budget_invalid")
        if not 0 < self.timeout_seconds <= 120:
            raise ProviderError("provider_timeout_invalid")


@dataclass(frozen=True)
class ProviderTelemetry:
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    cost_amount: float
    cost_currency: str
    latency_ms: int
    status: str

    def __post_init__(self) -> None:
        if any(not str(getattr(self, field)).strip() for field in ("provider", "model", "cost_currency", "status")):
            raise ProviderError("provider_telemetry_invalid")
        if min(self.input_tokens, self.output_tokens, self.latency_ms) < 0 or self.cost_amount < 0:
            raise ProviderError("provider_telemetry_invalid")


@dataclass(frozen=True)
class ProviderResult:
    response_payload: Mapping[str, Any]
    response_checksum: str
    telemetry: ProviderTelemetry

    def __post_init__(self) -> None:
        if checksum(self.response_payload) != self.response_checksum:
            raise ProviderError("provider_response_checksum_mismatch")


class AnalysisProvider(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResult: ...


class ReplayProvider:
    """Deterministic fixture/replay provider using only caller-supplied payloads."""

    def __init__(
        self,
        responses: Mapping[str, Any] | list[Mapping[str, Any] | Exception],
        *,
        model: str = "replay-v1",
        input_tokens: int = 1,
        output_tokens: int = 1,
    ) -> None:
        self._responses = list(responses) if isinstance(responses, list) else [responses]
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.calls = 0

    def generate(self, request: ProviderRequest) -> ProviderResult:
        index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        if not self._responses:
            raise ProviderError("replay_response_missing")
        selected = self._responses[index]
        if isinstance(selected, Exception):
            raise selected
        payload = dict(selected)
        return ProviderResult(
            response_payload=payload, response_checksum=checksum(payload),
            telemetry=ProviderTelemetry(
                provider="replay", model=self.model, input_tokens=self.input_tokens,
                output_tokens=self.output_tokens, cost_amount=0.0, cost_currency="USD",
                latency_ms=0, status="completed",
            ),
        )


Transport = Callable[[Mapping[str, Any], float], Mapping[str, Any]]


class OpenAICompatibleProvider:
    """Authorized boundary around an injected transport; contains no HTTP client or secret."""

    def __init__(
        self,
        *,
        model: str,
        transport: Transport | None = None,
        enabled: bool = False,
        credential_present: bool = False,
        provider_name: str = "openai-compatible",
    ) -> None:
        self.model = model
        self.transport = transport
        self.enabled = enabled
        self.credential_present = credential_present
        self.provider_name = provider_name

    def generate(self, request: ProviderRequest) -> ProviderResult:
        if not self.enabled:
            raise ProviderError("provider_not_authorized")
        if not self.credential_present:
            raise ProviderError("provider_credential_missing")
        if self.transport is None:
            raise ProviderError("provider_transport_missing")
        body = {
            "model": self.model,
            "messages": [{"role": "user", "content": request.prompt}],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
            "response_format": {"type": "json_object"},
        }
        started = time.monotonic()
        try:
            raw = self.transport(body, request.timeout_seconds)
        except TimeoutError as exc:
            raise ProviderTimeout() from exc
        except ProviderError:
            raise
        except Exception as exc:
            raise ProviderError("provider_transport_error", type(exc).__name__, retryable=True) from exc
        latency = int((time.monotonic() - started) * 1000)
        try:
            content = raw["choices"][0]["message"]["content"]
            payload = json.loads(content) if isinstance(content, str) else dict(content)
            usage = raw.get("usage") or {}
            input_tokens = int(usage.get("prompt_tokens", 0))
            output_tokens = int(usage.get("completion_tokens", 0))
            cost = float(raw.get("cost_amount", 0.0))
        except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProviderError("provider_response_invalid") from exc
        return ProviderResult(
            response_payload=payload, response_checksum=checksum(payload),
            telemetry=ProviderTelemetry(
                provider=self.provider_name, model=str(raw.get("model") or self.model),
                input_tokens=input_tokens, output_tokens=output_tokens,
                cost_amount=cost, cost_currency=str(raw.get("cost_currency") or "USD"),
                latency_ms=latency, status="completed",
            ),
        )


__all__ = [
    "AnalysisProvider", "OpenAICompatibleProvider", "ProviderError", "ProviderRequest",
    "ProviderResult", "ProviderTelemetry", "ProviderTimeout", "ReplayProvider",
]

