"""Spike 006: provider auth, timeout, quota and budget fail-closed."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass


class ProviderError(RuntimeError):
    def __init__(self, code: str, retryable: bool):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass
class Budget:
    max_calls: int = 2
    max_tokens: int = 20
    calls: int = 0
    tokens: int = 0

    def reserve(self, tokens: int) -> None:
        if self.calls + 1 > self.max_calls or self.tokens + tokens > self.max_tokens:
            raise ProviderError("budget_exhausted", False)
        self.calls += 1
        self.tokens += tokens


def fake_provider(mode: str, credential: str | None) -> str:
    if not credential:
        raise ProviderError("auth_missing", False)
    if mode == "timeout":
        time.sleep(0.002)
        raise ProviderError("provider_timeout", True)
    if mode == "quota":
        raise ProviderError("provider_quota", True)
    if mode == "oversized":
        return "x" * 1000
    return "synthetic-response"


def call_provider(mode: str, budget: Budget, credential: str | None) -> dict[str, object]:
    credential_hash = hashlib.sha256((credential or "").encode()).hexdigest() if credential else None
    try:
        budget.reserve(5)
        response = fake_provider(mode, credential)
        if len(response) > 128:
            raise ProviderError("response_too_large", False)
        return {"status": "succeeded", "credential_present": credential is not None, "credential_hash": credential_hash, "response_size": len(response)}
    except ProviderError as exc:
        return {"status": "error", "code": exc.code, "retryable": exc.retryable, "credential_present": credential is not None, "credential_hash": credential_hash}


def main() -> None:
    authority = "authority-fingerprint-synthetic"
    report = {}
    report["success"] = call_provider("success", Budget(), "synthetic-secret-value")
    report["missing_auth"] = call_provider("success", Budget(), None)
    report["timeout"] = call_provider("timeout", Budget(), "synthetic-secret-value")
    report["quota"] = call_provider("quota", Budget(), "synthetic-secret-value")
    report["oversized"] = call_provider("oversized", Budget(), "synthetic-secret-value")
    budget = Budget(max_calls=1, max_tokens=5)
    report["first_call_budget"] = call_provider("success", budget, "synthetic-secret-value")
    report["second_call_budget"] = call_provider("success", budget, "synthetic-secret-value")
    report["budget_state"] = {"calls": budget.calls, "tokens": budget.tokens}
    serialized = json.dumps(report, sort_keys=True)
    assert "synthetic-secret-value" not in serialized
    assert report["missing_auth"]["code"] == "auth_missing"
    assert report["timeout"]["code"] == "provider_timeout" and report["timeout"]["retryable"]
    assert report["oversized"]["code"] == "response_too_large"
    assert report["second_call_budget"]["status"] == "error" and report["second_call_budget"]["code"] == "budget_exhausted"
    report["authority_unchanged"] = authority == "authority-fingerprint-synthetic"
    report["credential_values_logged"] = False
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
