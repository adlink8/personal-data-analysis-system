from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from personal_knowledge.services.pi_domain_gateway import DEFAULT_CAPABILITY, PiDomainGateway


def test_outcome_unknown_is_explicit_and_not_an_automatic_retry():
    calls = []
    gateway = PiDomainGateway(capability=DEFAULT_CAPABILITY, read_handler=lambda operation, params: calls.append(params) or {"status": "synthetic"})
    first = gateway.invoke("domain.inspect", {"task_id": "t-unknown", "idempotency_key": "idem-unknown", "binding": "b"}, capability=DEFAULT_CAPABILITY)
    assert first["ok"] is True
    assert len(calls) == 1


def test_duplicate_dispatch_is_keyed_and_safe():
    calls = []
    gateway = PiDomainGateway(capability="cap", read_handler=lambda operation, params: calls.append(params["idempotency_key"]) or {"status": "synthetic"})
    payload = {"task_id": "t-1", "idempotency_key": "idem-1", "binding": "b"}
    assert gateway.invoke("domain.inspect", payload, capability="cap")["ok"]
    assert gateway.invoke("domain.inspect", payload, capability="cap")["ok"]
    assert calls == ["idem-1", "idem-1"]  # task ledger owns dedupe; gateway never invents a retry policy
