import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

import personal_knowledge.services.api_server as api_server
from personal_knowledge.intelligence.proactive.schema import CANONICAL_DOMAINS
from personal_knowledge.intelligence.service import IntelligenceService
from personal_knowledge.services.api_server import ui_rest_contract
from personal_knowledge.services.decision_intelligence_reads import (
    DecisionIntelligenceReadService,
)
from personal_knowledge.services.ui_projection import (
    INTERFACE_SCHEMA_VERSION,
    CockpitProjectionService,
)

EIGHT_DOMAINS = set(CANONICAL_DOMAINS)
ASSERTION_KIND_KEYS = {"goal", "constraint", "observation", "state"}
PROVENANCE_KEYS = {"fact", "observation", "inference"}
LIFECYCLE_KEYS = {"current", "stale", "conflict", "resolved", "expired"}
PERSONAL_STATE_DATA_KEYS = {
    "snapshot_id", "as_of", "total_available", "history_total_available",
    "domains", "lifecycle_counts", "recent_changes",
}
ASSERTION_ITEM_KEYS = {
    "key", "provenance_class", "status", "confidence",
    "current_assertion_id", "evidence_count",
}
CHANGE_ITEM_KEYS = {
    "record_id", "record_type", "status", "domain", "subject", "effective_at",
}
EXTERNAL_DATA_KEYS = {"snapshot", "sources", "facts", "delta", "counts"}
SNAPSHOT_KEYS = {"snapshot_id", "snapshot_hash", "activated_at"}
SOURCE_ITEM_KEYS = {
    "source_id", "authority_role", "source_type", "topic", "region", "endpoint",
}
FACT_ITEM_KEYS = {
    "fact_id", "subject", "predicate", "region", "valid_from", "valid_to",
    "source_quality", "fact_confidence", "lifecycle", "conflict",
}
DELTA_KEYS = {"new", "updated", "expiring", "conflicts"}


def test_personal_state_envelope_shape():
    result = CockpitProjectionService().invoke("personal_state.get")
    assert result["schema_version"] == INTERFACE_SCHEMA_VERSION
    assert result["schema_version"] == "decision_cockpit_projection_v1"
    assert result["ok"] is True
    assert result["operation"] == "personal_state.get"
    assert set(result["snapshot_bindings"]) == {"personal", "external", "serving"}
    assert isinstance(result["limitations"], list)
    assert set(result["authorities"]) == {"state", "changes"}
    assert set(result["authorities"].values()) <= {"ok", "empty", "error"}
    assert result["generated_at"]
    assert set(result["data"]) == PERSONAL_STATE_DATA_KEYS


def test_personal_state_domains_shape():
    data = CockpitProjectionService().invoke("personal_state.get")["data"]
    # 八个领域键恒在且恰好八个(无数据时全零 + 空数组)
    assert set(data["domains"]) == EIGHT_DOMAINS
    assert len(data["domains"]) == 8
    for bucket in data["domains"].values():
        assert set(bucket) == {"total", "by_kind", "by_provenance", "conflicts", "assertions"}
        assert set(bucket["by_kind"]) == ASSERTION_KIND_KEYS
        assert set(bucket["by_provenance"]) == PROVENANCE_KEYS
        assert isinstance(bucket["conflicts"], int)
        assert len(bucket["assertions"]) <= 20
        for item in bucket["assertions"]:
            assert set(item) == ASSERTION_ITEM_KEYS
            assert item["provenance_class"] in PROVENANCE_KEYS
            assert set(item["key"]) == {
                "assertion_kind", "subject", "domain", "scope", "predicate",
            }
            assert isinstance(item["evidence_count"], int)
    assert set(data["lifecycle_counts"]) == LIFECYCLE_KEYS
    for item in data["recent_changes"]:
        assert set(item) == CHANGE_ITEM_KEYS


def test_personal_state_changes_failure_isolated(monkeypatch):
    original = IntelligenceService.invoke

    def guarded(self, operation, **params):
        if operation == "changes.recent":
            raise RuntimeError("boom")
        return original(self, operation, **params)

    monkeypatch.setattr(IntelligenceService, "invoke", guarded)
    result = CockpitProjectionService().invoke("personal_state.get")
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["authorities"]["changes"] == "error"
    assert any("changes" in item for item in result["limitations"])
    # changes 故障降级为空数组,state 节不受影响
    assert result["data"]["recent_changes"] == []
    assert result["authorities"]["state"] in {"ok", "empty"}
    assert set(result["data"]["domains"]) == EIGHT_DOMAINS


def test_external_delta_envelope_shape():
    result = CockpitProjectionService().invoke("external_delta.get")
    assert result["schema_version"] == INTERFACE_SCHEMA_VERSION
    assert result["ok"] is True
    assert result["operation"] == "external_delta.get"
    assert set(result["snapshot_bindings"]) == {"personal", "external", "serving"}
    assert set(result["authorities"]) == {"external"}
    assert set(result["authorities"].values()) <= {"ok", "empty", "error"}
    data = result["data"]
    if data is None:
        return  # authority 故障时 data 允许为 None(由 authorities/limitations 表达)
    assert set(data) == EXTERNAL_DATA_KEYS
    assert set(data["counts"]) == {"sources", "facts", "conflicts"}
    assert set(data["delta"]) == DELTA_KEYS
    for bucket in data["delta"].values():
        assert isinstance(bucket, list)
    assert set(data["snapshot"]) == SNAPSHOT_KEYS
    assert result["snapshot_bindings"]["external"] == data["snapshot"]["snapshot_id"]
    for source in data["sources"]:
        assert set(source) == SOURCE_ITEM_KEYS
    for fact in data["facts"]:
        assert set(fact) == FACT_ITEM_KEYS
        assert fact["conflict"] == (fact["lifecycle"] == "conflict")
    assert data["counts"]["sources"] == len(data["sources"])
    assert data["counts"]["facts"] == len(data["facts"])
    assert data["counts"]["conflicts"] == len(data["delta"]["conflicts"])


def test_external_delta_failure_isolated(monkeypatch):
    def boom(self, operation, **params):
        raise RuntimeError("boom")

    monkeypatch.setattr(DecisionIntelligenceReadService, "invoke", boom)
    result = CockpitProjectionService().invoke("external_delta.get")
    assert result["ok"] is True
    assert result["partial"] is True
    assert result["authorities"]["external"] == "error"
    assert any("external" in item for item in result["limitations"])
    assert result["data"] is None
    assert result["snapshot_bindings"]["external"] is None


def test_rest_adapter_parity_new_operations():
    service = CockpitProjectionService()
    for operation in ("personal_state.get", "external_delta.get"):
        rest = ui_rest_contract(operation, {}, service=service)
        direct = service.invoke(operation)
        # generated_at 按调用生成(含 freshness 内的同源副本),pop 掉再比较其余字段
        for envelope in (rest, direct):
            envelope.pop("generated_at")
            envelope["freshness"].pop("generated_at")
        assert rest == direct


def test_ui_routes_serve_new_endpoints():
    server = ThreadingHTTPServer(("127.0.0.1", 0), api_server.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    # 本机请求不走任何 HTTP_PROXY 环境变量
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        port = server.server_address[1]
        for path, operation in (
            ("/ui/personal-state", "personal_state.get"),
            ("/ui/external/delta", "external_delta.get"),
        ):
            with opener.open(f"http://127.0.0.1:{port}{path}") as resp:
                body = json.loads(resp.read())
            assert resp.status == 200
            assert body["ok"] is True
            assert body["operation"] == operation
            assert body["schema_version"] == INTERFACE_SCHEMA_VERSION
    finally:
        server.shutdown()
        server.server_close()
